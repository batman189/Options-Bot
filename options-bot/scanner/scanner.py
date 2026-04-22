"""Symbol scanner — surfaces symbols with developing setups.
Runs every 60 seconds. Outputs ranked list of scored setups.
Read-only: no positions, no orders, no state changes.

Evaluates 5 setup types per symbol per cycle (Prompt 31 / O11
updated the count -- earlier docstrings said 4):
    momentum, mean_reversion, compression_breakout, catalyst,
    macro_trend.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from scanner.setups import (
    score_momentum, score_mean_reversion,
    score_compression_breakout, score_catalyst,
    score_macro_trend, SetupScore,
)
from scanner.sentiment import get_sentiment
from market.context import MarketContext, MarketSnapshot

logger = logging.getLogger("options-bot.scanner")


@dataclass
class ScanResult:
    """One symbol's scan output for a single cycle."""
    symbol: str
    setups: list[SetupScore] = field(default_factory=list)
    best_score: float = 0.0
    best_setup: str = ""


class Scanner:
    """Watches a configurable symbol list, evaluates 5 setup types each cycle.

    Setup types: momentum, mean_reversion, compression_breakout,
    catalyst, macro_trend. Prompt 31 (O11) updated the count from 4.
    """

    def __init__(self, symbols: list[str], data_client=None, context: MarketContext = None):
        self._symbols = symbols
        self._client = data_client
        self._context = context
        self._interval = 60  # seconds between scans
        self._last_scan_time: float = 0.0
        self._last_results: list[ScanResult] = []

    def scan(self, force: bool = False) -> list[ScanResult]:
        """Run one scan cycle. Cached for 60s unless force=True.

        Returns list of ScanResult sorted by best_score descending.
        """
        now = time.time()
        if not force and self._last_results and (now - self._last_scan_time) < self._interval:
            return self._last_results

        if self._client is None:
            from data.unified_client import UnifiedDataClient
            self._client = UnifiedDataClient()
        if self._context is None:
            self._context = MarketContext(data_client=self._client)

        market = self._context.get_snapshot()
        results = []

        for symbol in self._symbols:
            result = self._scan_symbol(symbol, market)
            results.append(result)

        # Sort by best score descending
        results.sort(key=lambda r: r.best_score, reverse=True)
        self._last_results = results
        self._last_scan_time = now

        # Log summary
        active = [r for r in results if r.best_score > 0]
        if active:
            for r in active:
                logger.info(
                    f"Scanner: {r.symbol} {r.best_setup}={r.best_score:.3f} "
                    f"| regime={market.regime.value}"
                )
        else:
            logger.info(f"Scanner: no active setups across {len(self._symbols)} symbols")

        return results

    def _scan_symbol(self, symbol: str, market: MarketSnapshot) -> ScanResult:
        """Evaluate all 5 setup types for one symbol."""
        try:
            bars = self._client.get_stock_bars(symbol, "1Min", 60)
        except Exception as e:
            logger.warning(f"Scanner: bars unavailable for {symbol}: {e}")
            return ScanResult(symbol=symbol)

        if len(bars) < 20:
            return ScanResult(symbol=symbol)

        setups = []

        # 1. Momentum
        try:
            setups.append(score_momentum(bars, symbol))
        except Exception as e:
            logger.warning(f"Scanner: momentum failed for {symbol}: {e}")

        # 2. Mean Reversion
        try:
            setups.append(score_mean_reversion(bars, symbol))
        except Exception as e:
            logger.warning(f"Scanner: mean_reversion failed for {symbol}: {e}")

        # 3. Compression Breakout
        try:
            setups.append(score_compression_breakout(bars, symbol))
        except Exception as e:
            logger.warning(f"Scanner: compression failed for {symbol}: {e}")

        # 4. Catalyst (requires sentiment + options volume)
        try:
            sentiment = get_sentiment(symbol)
            # Underlying price from the most recent 1-minute bar. Matches
            # the pattern selector._get_underlying_price uses. Required
            # by _get_options_vol_oi_ratio's near-ATM filter (Prompt 24).
            underlying_price = float(bars.iloc[-1]["close"])
            vol_oi_ratio = self._get_options_vol_oi_ratio(symbol, underlying_price)
            setups.append(score_catalyst(bars, symbol, sentiment.score, vol_oi_ratio))
        except Exception as e:
            logger.warning(f"Scanner: catalyst failed for {symbol}: {e}")

        # 5. Macro trend (15-minute bars — catches gap-and-run days)
        try:
            bars_15min = self._client.get_stock_bars(symbol, "15Min", 16)
            setups.append(score_macro_trend(bars_15min, symbol))
        except Exception as e:
            logger.warning(f"Scanner: macro_trend failed for {symbol}: {e}")

        # Find best
        result = ScanResult(symbol=symbol, setups=setups)
        if setups:
            best = max(setups, key=lambda s: s.score)
            result.best_score = best.score
            result.best_setup = best.setup_type
        return result

    def _get_options_vol_oi_ratio(
        self, symbol: str, underlying_price: float,
    ) -> Optional[float]:
        """Compute options volume / OI ratio for unusual activity detection.

        Returns the max vol/OI ratio across near-ATM strikes.

        "Near-ATM" = strikes within CATALYST_NEAR_ATM_PCT of the
        underlying price (currently 1.5% on either side, tunable in
        scanner/setups.py). Strikes beyond this band are excluded —
        wings with vol/OI > threshold are typically retail activity
        on low-absolute-volume strikes, not the institutional flow
        this gate is meant to detect. Pre-Prompt-24 this loop walked
        the entire chain, letting a deep-OTM strike with OI=150 and
        vol=90 (ratio=0.60) pass the 0.50 catalyst threshold.

        Only strikes with OI > 100 and vol > 0 are considered (same
        liquidity floor as before — this change narrows the strike
        set, not the liquidity threshold).

        Returns 0.0 when no near-ATM strikes meet the liquidity
        threshold, distinguishable from "flow detected at ratio 0"
        which is mathematically impossible (vol/OI with OI > 100
        and vol > 0 is always > 0). Returns None on data-fetch
        failure — different signal (gate cannot evaluate vs gate
        evaluated and found nothing).

        Uses ThetaData for OI (yesterday's EOD) and today's volume.
        Uses the nearest valid expiration for the symbol.
        """
        try:
            from scanner.setups import CATALYST_NEAR_ATM_PCT
            expiration = self._client.get_nearest_expiration(symbol)
            chain = self._client.get_options_chain(symbol, expiration)
            if not chain:
                return None

            # Near-ATM band (Prompt 24). Compute once; filter first,
            # then take the max vol/OI of what remains.
            price_window = underlying_price * (CATALYST_NEAR_ATM_PCT / 100.0)
            atm_low = underlying_price - price_window
            atm_high = underlying_price + price_window

            near_atm_contracts = [
                c for c in chain
                if atm_low <= c.get("strike", 0) <= atm_high
                and c.get("open_interest", 0) > 100
                and c.get("volume", 0) > 0
            ]

            if not near_atm_contracts:
                # No near-ATM strikes cleared the liquidity floor.
                # Explicit 0.0 (not None) — gate evaluated and found
                # nothing, as opposed to "couldn't evaluate".
                return 0.0

            return max(
                c["volume"] / c["open_interest"]
                for c in near_atm_contracts
            )
        except Exception as e:
            logger.warning(f"Options vol/OI failed for {symbol}: {e}")
            return None

    def get_active_setups(self, min_score: float = 0.3) -> list[tuple[str, SetupScore]]:
        """Return only setups above a score threshold. Convenience method."""
        results = self.scan()
        active = []
        for r in results:
            for s in r.setups:
                if s.score >= min_score:
                    active.append((r.symbol, s))
        active.sort(key=lambda x: x[1].score, reverse=True)
        return active

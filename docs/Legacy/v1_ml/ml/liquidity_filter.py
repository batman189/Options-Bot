"""
Liquidity gate for options contracts.

Rejects contracts that are too illiquid to trade at acceptable cost.
Runs AFTER scan_chain_for_best_ev() selects a candidate — checks OI and
volume for the specific selected contract via Alpaca options snapshot API.

Thresholds configured in config.py:
  MIN_OPEN_INTEREST  (default 100)
  MIN_OPTION_VOLUME  (default 50)
"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("options-bot.ml.liquidity_filter")


@dataclass
class LiquidityResult:
    passed: bool
    open_interest: Optional[int]
    daily_volume: Optional[int]
    bid_ask_spread_pct: Optional[float]
    reject_reason: Optional[str]


def check_liquidity(
    open_interest: Optional[int],
    daily_volume: Optional[int],
    bid_price: Optional[float],
    ask_price: Optional[float],
    min_oi: int,
    min_volume: int,
    max_spread_pct: float,
    symbol: str = "",
) -> LiquidityResult:
    """
    Check whether an options contract is liquid enough to trade.

    Args:
        open_interest:  Current OI for the strike/expiry (None = unavailable)
        daily_volume:   Today's volume for the strike/expiry (None = unavailable)
        bid_price:      Current bid
        ask_price:      Current ask
        min_oi:         Minimum acceptable OI (from config)
        min_volume:     Minimum acceptable daily volume (from config)
        max_spread_pct: Maximum acceptable (ask-bid)/mid (from config)
        symbol:         Ticker for logging

    Returns:
        LiquidityResult
    """
    logger.info(
        "check_liquidity | symbol=%s oi=%s vol=%s bid=%s ask=%s",
        symbol, open_interest, daily_volume, bid_price, ask_price,
    )

    try:
        # Open Interest check
        if open_interest is not None and open_interest < min_oi:
            reason = f"open_interest={open_interest} < min={min_oi}"
            logger.info("Liquidity REJECT [%s]: %s", symbol, reason)
            return LiquidityResult(
                passed=False,
                open_interest=open_interest,
                daily_volume=daily_volume,
                bid_ask_spread_pct=None,
                reject_reason=reason,
            )

        # Daily Volume check
        if daily_volume is not None and daily_volume < min_volume:
            reason = f"daily_volume={daily_volume} < min={min_volume}"
            logger.info("Liquidity REJECT [%s]: %s", symbol, reason)
            return LiquidityResult(
                passed=False,
                open_interest=open_interest,
                daily_volume=daily_volume,
                bid_ask_spread_pct=None,
                reject_reason=reason,
            )

        # Bid-Ask Spread check
        spread_pct = None
        if bid_price is not None and ask_price is not None:
            mid = (bid_price + ask_price) / 2.0
            if mid > 0:
                spread_pct = (ask_price - bid_price) / mid
                if spread_pct > max_spread_pct:
                    reason = (
                        f"spread_pct={spread_pct:.3f} ({spread_pct*100:.1f}%) "
                        f"> max={max_spread_pct*100:.1f}%"
                    )
                    logger.info("Liquidity REJECT [%s]: %s", symbol, reason)
                    return LiquidityResult(
                        passed=False,
                        open_interest=open_interest,
                        daily_volume=daily_volume,
                        bid_ask_spread_pct=spread_pct,
                        reject_reason=reason,
                    )

        logger.info(
            "Liquidity PASS [%s] | oi=%s vol=%s spread_pct=%s",
            symbol, open_interest, daily_volume, spread_pct,
        )
        return LiquidityResult(
            passed=True,
            open_interest=open_interest,
            daily_volume=daily_volume,
            bid_ask_spread_pct=spread_pct,
            reject_reason=None,
        )

    except Exception:
        logger.error("check_liquidity failed for %s", symbol, exc_info=True)
        # Fail safe: reject if liquidity cannot be determined
        return LiquidityResult(
            passed=False,
            open_interest=open_interest,
            daily_volume=daily_volume,
            bid_ask_spread_pct=None,
            reject_reason="Liquidity check error — trade rejected for safety",
        )


def fetch_option_snapshot(
    symbol: str,
    expiration: str,
    strike: float,
    right: str,
    api_key: str,
    api_secret: str,
    paper: bool = True,
) -> dict:
    """
    Fetch OI and volume for a specific option contract via Alpaca options snapshot.

    Returns dict with keys: open_interest, volume, bid, ask
    All values may be None if the API call fails.
    """
    logger.info(
        "fetch_option_snapshot | %s %s %s exp=%s",
        symbol, strike, right, expiration,
    )

    try:
        from alpaca.data.requests import OptionSnapshotRequest, OptionBarsRequest
        from alpaca.data.historical.option import OptionHistoricalDataClient
        from alpaca.data.timeframe import TimeFrame
        from datetime import datetime, timedelta, timezone

        client = OptionHistoricalDataClient(api_key, api_secret)

        # Build the OCC option symbol
        # Format: TSLA250321C00250000 (symbol, date YYMMDD, C/P, strike * 1000 padded to 8)
        exp_str = expiration.replace("-", "")
        if len(exp_str) == 8:
            # YYYYMMDD -> YYMMDD
            exp_str = exp_str[2:]
        right_char = "C" if right.upper() in ("CALL", "C") else "P"
        strike_int = int(strike * 1000)
        occ_symbol = f"{symbol}{exp_str}{right_char}{strike_int:08d}"

        result = {
            "open_interest": None,
            "volume": None,
            "bid": None,
            "ask": None,
        }

        # 1) Snapshot for bid/ask quotes
        try:
            request = OptionSnapshotRequest(symbol_or_symbols=[occ_symbol])
            snapshots = client.get_option_snapshot(request)
            if occ_symbol in snapshots:
                snap = snapshots[occ_symbol]
                result["bid"] = snap.latest_quote.bid_price if snap.latest_quote else None
                result["ask"] = snap.latest_quote.ask_price if snap.latest_quote else None
        except Exception:
            logger.warning("Snapshot call failed for %s", occ_symbol, exc_info=True)

        # 2) Daily bar for actual daily volume and open_interest
        try:
            now_utc = datetime.now(timezone.utc)
            bar_request = OptionBarsRequest(
                symbol_or_symbols=[occ_symbol],
                timeframe=TimeFrame.Day,
                start=now_utc - timedelta(days=1),
            )
            bars = client.get_option_bars(bar_request)
            if occ_symbol in bars and len(bars[occ_symbol]) > 0:
                # Use the most recent daily bar
                daily_bar = bars[occ_symbol][-1]
                result["volume"] = getattr(daily_bar, "volume", None)
                # open_interest may be on the bar in some Alpaca versions
                oi = getattr(daily_bar, "open_interest", None)
                if oi is not None:
                    result["open_interest"] = oi
        except Exception:
            logger.warning("Daily bar call failed for %s", occ_symbol, exc_info=True)

        logger.info("fetch_option_snapshot result: %s", result)
        return result

    except ImportError:
        logger.warning("alpaca-py options data not available — skipping snapshot")
        return {"open_interest": None, "volume": None, "bid": None, "ask": None}
    except Exception:
        logger.error("fetch_option_snapshot failed", exc_info=True)
        return {"open_interest": None, "volume": None, "bid": None, "ask": None}

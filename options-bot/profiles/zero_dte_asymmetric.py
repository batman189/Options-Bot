"""Phase 1a 0DTE asymmetric preset — see ARCHITECTURE.md §4.2.

Patient, asymmetric, low-position-count strategy on SPY/QQQ. Buys cheap
OTM 0DTE calls or puts only when one of the catalyst paths is active and
all four technical-confirmation gates align with that direction.

Entry path (per §4.2, post Prompt C1's ORB deferral):

    1. Time gate           9:35-13:30 ET (also enforced by is_active_now)
    2. Underlying price    most recent 1-min close
    3. Direction           from scanner_output.direction (bullish / bearish)
    4. Cooldowns           max 2 entries/day; 60-min same-direction
    5. Catalyst gate       3-of-3 paths (scheduled HIGH event ≤ 4h /
                           Mag-7 post-earnings ≤ 60m / VIX +15% in 60m)
    6. Technical confirm   prior-day-range break + 5m EMA(20) + VWAP
                           + 3 directional 1-min bars

`select_contract` and `evaluate_exit` are stubbed:
  - `select_contract` lands in Prompt C4c.
  - `evaluate_exit` is deferred to Phase 2 (signal-only-mode through
    Phase 1b; no positions are opened).

Dependency injection: macro_fetcher, vix_spike_fetcher, bars_fetcher, and
now_fetcher are passed at construction so tests can stub them. Production
wire-in supplies macro.reader.get_active_events,
scoring.vix_spike.vix_spike_pct, data.unified_client.get_stock_bars, and
the system clock. This module deliberately does not import those callables
by name — the orchestrator owns the wire-in so the seam stays clean.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from market.context import MarketSnapshot
from profiles.base_preset import (
    BasePreset,
    ContractSelection,
    EntryDecision,
    ExitDecision,
    OptionChain,
    Position,
    ProfileState,
)
from profiles.profile_config import ProfileConfig
from scanner.indicators import ema, session_vwap
from scanner.setups import SetupScore

logger = logging.getLogger("options-bot.profiles.0dte_asymmetric")

ET = ZoneInfo("America/New_York")


class ZeroDteAsymmetricPreset(BasePreset):
    """Phase 1a 0DTE asymmetric preset — see ARCHITECTURE.md §4.2.

    The preset accepts every scanner setup type because the 0DTE
    entry path runs its own catalyst gate; the scanner setup is used
    only for its `direction` field to determine call vs. put. The
    setup's score and type are not enforced at entry — §4.2 has no
    score floor or setup-type filter.
    """

    name = "0dte_asymmetric"
    accepted_setup_types = frozenset({
        "momentum",
        "mean_reversion",
        "compression_breakout",
        "catalyst",
        "macro_trend",
    })

    # Time gate (ET, inclusive on both ends)
    ENTRY_WINDOW_START = time(9, 35)
    ENTRY_WINDOW_END = time(13, 30)

    # Catalyst gate
    MACRO_LOOKAHEAD_MINUTES = 240          # 4 hours
    MAG_7_POST_EARNINGS_MINUTES = 60       # within 60 min of market open
    VIX_SPIKE_THRESHOLD_PCT = 15.0
    MAG_7_SYMBOLS = frozenset({
        "TSLA", "NVDA", "AAPL", "MSFT", "META", "AMZN", "GOOG",
    })
    MARKET_OPEN_ET = time(9, 30)

    # Technical confirmation
    EMA_WINDOW = 20
    EMA_TIMEFRAME = "5Min"
    EMA_BAR_COUNT = 60                     # 5h of 5-min bars; ample headroom
    VWAP_TIMEFRAME = "1Min"
    VWAP_BAR_COUNT = 240                   # session bars (4h cap)
    DIRECTIONAL_BARS_REQUIRED = 3
    DIRECTIONAL_TIMEFRAME = "1Min"
    DIRECTIONAL_BAR_COUNT = 5              # 3 + headroom
    DAILY_TIMEFRAME = "1Day"
    DAILY_BAR_COUNT = 2                    # prior day + today partial

    # Cooldowns
    MAX_ENTRIES_PER_DAY = 2
    SAME_DIRECTION_COOLDOWN_MINUTES = 60

    def __init__(
        self,
        config: ProfileConfig,
        macro_fetcher=None,
        vix_spike_fetcher=None,
        bars_fetcher=None,
        now_fetcher=None,
    ):
        """All four fetchers are dependency-injected callables.

        macro_fetcher signature:
            (symbol: str, lookahead_minutes: int) -> list
            Each item must expose impact_level: str ("HIGH" / "MEDIUM" /
            "LOW") and event_type: str. Production wire-in passes
            macro.reader.get_active_events.

        vix_spike_fetcher signature:
            (now: Optional[datetime] = None) -> Optional[float]
            Returns signed % change over last 60 min. None means data
            unavailable — treated as "no spike catalyst" (fail-safe).
            Production wire-in passes scoring.vix_spike.vix_spike_pct.

        bars_fetcher signature:
            (symbol: str, timeframe: str, count: int) -> pandas.DataFrame
            Must return a DataFrame with at least 'close' (and 'high',
            'low', 'volume' for VWAP). Production wire-in passes
            data.unified_client.UnifiedDataClient.get_stock_bars.

        now_fetcher signature:
            () -> datetime
            Must return a tz-aware datetime. Defaults to
            datetime.now(timezone.utc) when not supplied. Used for
            deterministic time-gate testing.
        """
        super().__init__(config)
        self._macro_fetcher = macro_fetcher
        self._vix_spike_fetcher = vix_spike_fetcher
        self._bars_fetcher = bars_fetcher
        self._now_fetcher = now_fetcher

    # ─────────────────────────────────────────────────────────────
    # Time helpers
    # ─────────────────────────────────────────────────────────────

    def _now_utc(self) -> datetime:
        if self._now_fetcher is None:
            return datetime.now(timezone.utc)
        n = self._now_fetcher()
        if n.tzinfo is None:
            raise ValueError("now_fetcher must return tz-aware datetime")
        return n

    def _now_et(self) -> datetime:
        return self._now_utc().astimezone(ET)

    def is_active_now(self, market: MarketSnapshot) -> bool:
        """Return True only between 9:35 and 13:30 ET (inclusive on both
        ends). Checked against the injected now_fetcher (or wall clock
        if unset). The MarketSnapshot's time_of_day classification is
        not consulted — §4.2's window is finer-grained than its enums.
        """
        now_t = self._now_et().time()
        return self.ENTRY_WINDOW_START <= now_t <= self.ENTRY_WINDOW_END

    # ─────────────────────────────────────────────────────────────
    # Entry helpers
    # ─────────────────────────────────────────────────────────────

    def _check_cooldowns(
        self,
        symbol: str,
        direction: str,
        state: ProfileState,
    ) -> Optional[str]:
        """Return a reject-reason string if a cooldown blocks entry,
        or None if both cooldowns clear.

        Cooldown 1: max 2 entries today (across all symbols/directions).
        Cooldown 2: 60 minutes between same-direction entries on the
                    same symbol.
        """
        now_et = self._now_et()
        today_et = now_et.date()

        # Per-day cap. See PHASE_1A_FOLLOWUPS.md ("0DTE max-entries-today
        # undercount risk") — the dict only retains the latest entry per
        # (symbol, direction) key, so this counts distinct keys hit today,
        # not raw entries. Acceptable for Phase 1a; orchestrator wire-in
        # tightens it before live trading.
        entries_today = sum(
            1 for ts in state.recent_entries_by_symbol_direction.values()
            if ts.astimezone(ET).date() == today_et
        )
        if entries_today >= self.MAX_ENTRIES_PER_DAY:
            return (
                f"max entries today reached ({entries_today}/"
                f"{self.MAX_ENTRIES_PER_DAY})"
            )

        # Per-symbol-direction cooldown
        key = f"{symbol}:{direction}"
        last = state.recent_entries_by_symbol_direction.get(key)
        if last is not None:
            elapsed = (self._now_utc() - last).total_seconds() / 60.0
            if elapsed < self.SAME_DIRECTION_COOLDOWN_MINUTES:
                return (
                    f"same-direction cooldown active "
                    f"({elapsed:.1f}min < "
                    f"{self.SAME_DIRECTION_COOLDOWN_MINUTES}min) for {key}"
                )
        return None

    def _detect_direction(self, scanner_output: SetupScore) -> Optional[str]:
        """Return 'bullish' or 'bearish' from the scanner output, or None
        if direction is missing/neutral.
        """
        d = scanner_output.direction
        if d in ("bullish", "bearish"):
            return d
        return None

    def _check_catalyst(self, symbol: str) -> Optional[str]:
        """Return a one-line description of which catalyst path fired,
        or None if no catalyst is active.

        OR-of-three; first match wins (cheapest-to-evaluate first):
            (a) Scheduled HIGH-impact event within 4h
            (b) Mag-7 post-earnings within 60min of market open
            (c) VIX +15% in last 60 minutes
        """
        # (a) Scheduled HIGH-impact event
        if self._macro_fetcher is not None:
            try:
                events = self._macro_fetcher(
                    symbol, self.MACRO_LOOKAHEAD_MINUTES,
                )
            except Exception as e:
                logger.warning(
                    "macro_fetcher raised — treating as no event: %s", e,
                )
                events = []
            for e in events:
                if getattr(e, "impact_level", None) == "HIGH":
                    et_type = getattr(e, "event_type", "?")
                    return f"scheduled HIGH event ({et_type})"

        # (b) Mag-7 post-earnings within 60 minutes of market open
        if symbol in self.MAG_7_SYMBOLS and self._macro_fetcher is not None:
            now_et = self._now_et()
            minutes_since_open = (
                (now_et.hour - self.MARKET_OPEN_ET.hour) * 60
                + (now_et.minute - self.MARKET_OPEN_ET.minute)
            )
            if 0 <= minutes_since_open <= self.MAG_7_POST_EARNINGS_MINUTES:
                # Use a long-enough lookback to catch yesterday-after-hours
                # earnings (today is the post-earnings session). 24h covers
                # both pre-market and prior-evening earnings releases.
                try:
                    events = self._macro_fetcher(symbol, 24 * 60)
                except Exception as e:
                    logger.warning(
                        "macro_fetcher raised for Mag-7 path: %s", e,
                    )
                    events = []
                for e in events:
                    if (
                        getattr(e, "impact_level", None) == "HIGH"
                        and getattr(e, "event_type", "") == "EARNINGS"
                    ):
                        return (
                            f"Mag-7 post-earnings ({symbol}, "
                            f"{minutes_since_open}min since open)"
                        )

        # (c) VIX spike
        if self._vix_spike_fetcher is not None:
            try:
                spike_pct = self._vix_spike_fetcher()
            except Exception as e:
                logger.warning(
                    "vix_spike_fetcher raised — treating as no spike: %s", e,
                )
                spike_pct = None
            if (
                spike_pct is not None
                and spike_pct >= self.VIX_SPIKE_THRESHOLD_PCT
            ):
                return f"VIX +{spike_pct:.1f}% in 60min"

        return None

    def _check_technical_confirmation(
        self,
        symbol: str,
        direction: str,
        underlying_price: float,
    ) -> Optional[str]:
        """Return a reject-reason string if any of the four technical-
        confirmation gates fail, or None if all pass.

        Gates (all four must align with `direction`):
            1. Prior-day range break
                 calls: price > prior_day_high
                 puts:  price < prior_day_low
            2. 5-min EMA(20) supports direction
                 calls: price > EMA(20)
                 puts:  price < EMA(20)
            3. Session VWAP supports direction
                 calls: price > VWAP
                 puts:  price < VWAP
            4. Last 3 1-min bars all closed in direction
                 calls: each bar's close > its open (3 consecutive ups)
                 puts:  each bar's close < its open (3 consecutive downs)
        """
        if self._bars_fetcher is None:
            return "technical confirmation unavailable: no bars_fetcher"

        # (1) Prior-day range break
        try:
            daily = self._bars_fetcher(
                symbol, self.DAILY_TIMEFRAME, self.DAILY_BAR_COUNT,
            )
        except Exception as e:
            logger.warning("daily bars fetch failed for %s: %s", symbol, e)
            return "prior-day range unavailable"
        if daily is None or len(daily) < 2:
            return "prior-day range unavailable"
        prior = daily.iloc[-2]
        prior_high = float(prior["high"])
        prior_low = float(prior["low"])
        if direction == "bullish":
            if not (underlying_price > prior_high):
                return (
                    f"prior-day high not broken "
                    f"(price={underlying_price:.2f} <= "
                    f"high={prior_high:.2f})"
                )
        else:
            if not (underlying_price < prior_low):
                return (
                    f"prior-day low not broken "
                    f"(price={underlying_price:.2f} >= "
                    f"low={prior_low:.2f})"
                )

        # (2) 5-min EMA(20)
        try:
            ema_bars = self._bars_fetcher(
                symbol, self.EMA_TIMEFRAME, self.EMA_BAR_COUNT,
            )
        except Exception as e:
            logger.warning("5min bars fetch failed for %s: %s", symbol, e)
            return "EMA unavailable"
        ema_value = ema(ema_bars, window=self.EMA_WINDOW)
        if ema_value is None:
            return "EMA unavailable"
        if direction == "bullish":
            if not (underlying_price > ema_value):
                return (
                    f"price below 5m EMA(20) "
                    f"({underlying_price:.2f} <= {ema_value:.2f})"
                )
        else:
            if not (underlying_price < ema_value):
                return (
                    f"price above 5m EMA(20) "
                    f"({underlying_price:.2f} >= {ema_value:.2f})"
                )

        # (3) Session VWAP
        try:
            vwap_bars = self._bars_fetcher(
                symbol, self.VWAP_TIMEFRAME, self.VWAP_BAR_COUNT,
            )
        except Exception as e:
            logger.warning("VWAP bars fetch failed for %s: %s", symbol, e)
            return "VWAP unavailable"
        vwap_value = session_vwap(vwap_bars)
        if vwap_value is None:
            return "VWAP unavailable"
        if direction == "bullish":
            if not (underlying_price > vwap_value):
                return (
                    f"price below session VWAP "
                    f"({underlying_price:.2f} <= {vwap_value:.2f})"
                )
        else:
            if not (underlying_price < vwap_value):
                return (
                    f"price above session VWAP "
                    f"({underlying_price:.2f} >= {vwap_value:.2f})"
                )

        # (4) Last 3 1-min bars
        try:
            recent_bars = self._bars_fetcher(
                symbol,
                self.DIRECTIONAL_TIMEFRAME,
                self.DIRECTIONAL_BAR_COUNT,
            )
        except Exception as e:
            logger.warning(
                "directional bars fetch failed for %s: %s", symbol, e,
            )
            return "directional bars unavailable"
        if recent_bars is None or len(recent_bars) < self.DIRECTIONAL_BARS_REQUIRED:
            return "directional bars unavailable"
        last_n = recent_bars.tail(self.DIRECTIONAL_BARS_REQUIRED)
        if direction == "bullish":
            all_aligned = all(
                row["close"] > row["open"] for _, row in last_n.iterrows()
            )
            if not all_aligned:
                return (
                    f"last {self.DIRECTIONAL_BARS_REQUIRED} 1-min bars "
                    "not all up"
                )
        else:
            all_aligned = all(
                row["close"] < row["open"] for _, row in last_n.iterrows()
            )
            if not all_aligned:
                return (
                    f"last {self.DIRECTIONAL_BARS_REQUIRED} 1-min bars "
                    "not all down"
                )

        return None

    def _underlying_price(self, symbol: str) -> Optional[float]:
        """Latest 1-min close for `symbol`. Returns None on any failure."""
        if self._bars_fetcher is None:
            return None
        try:
            bars = self._bars_fetcher(symbol, "1Min", 1)
        except Exception as e:
            logger.warning(
                "underlying price fetch failed for %s: %s", symbol, e,
            )
            return None
        if bars is None or len(bars) == 0:
            return None
        try:
            return float(bars.iloc[-1]["close"])
        except Exception as e:
            logger.warning(
                "underlying price parse failed for %s: %s", symbol, e,
            )
            return None

    # ─────────────────────────────────────────────────────────────
    # BasePreset overrides
    # ─────────────────────────────────────────────────────────────

    def evaluate_entry(
        self,
        symbol: str,
        scanner_output: SetupScore,
        market: MarketSnapshot,
        state: ProfileState,
    ) -> EntryDecision:
        """AND-gate evaluation per ARCHITECTURE.md §4.2.

        Order:
            (a) time-of-day window
            (b) underlying price available
            (c) directional setup
            (d) cooldowns
            (e) catalyst gate (3-of-3 OR)
            (f) technical confirmation (4-of-4 AND)

        Returns EntryDecision(should_enter=False, reason=...) on the
        first failed gate.
        """
        # (a) Time gate (defensive — orchestrator should also gate)
        now_t = self._now_et().time()
        if not (
            self.ENTRY_WINDOW_START <= now_t <= self.ENTRY_WINDOW_END
        ):
            return EntryDecision(
                should_enter=False,
                reason=(
                    f"outside entry window "
                    f"{self.ENTRY_WINDOW_START.strftime('%H:%M')}-"
                    f"{self.ENTRY_WINDOW_END.strftime('%H:%M')} ET "
                    f"(now={now_t.strftime('%H:%M:%S')})"
                ),
                direction=scanner_output.direction,
            )

        # (b) Underlying price
        price = self._underlying_price(symbol)
        if price is None or price <= 0:
            return EntryDecision(
                should_enter=False,
                reason="underlying price unavailable",
                direction=scanner_output.direction,
            )

        # (c) Direction
        direction = self._detect_direction(scanner_output)
        if direction is None:
            return EntryDecision(
                should_enter=False,
                reason=(
                    f"non-directional setup "
                    f"(direction={scanner_output.direction!r})"
                ),
                direction=scanner_output.direction,
            )

        # (d) Cooldowns
        cooldown_reason = self._check_cooldowns(symbol, direction, state)
        if cooldown_reason is not None:
            return EntryDecision(
                should_enter=False,
                reason=cooldown_reason,
                direction=direction,
            )

        # (e) Catalyst gate
        catalyst = self._check_catalyst(symbol)
        if catalyst is None:
            return EntryDecision(
                should_enter=False,
                reason="no catalyst path active",
                direction=direction,
            )

        # (f) Technical confirmation
        tech_reason = self._check_technical_confirmation(
            symbol, direction, price,
        )
        if tech_reason is not None:
            return EntryDecision(
                should_enter=False,
                reason=tech_reason,
                direction=direction,
            )

        # (g) All gates passed
        return EntryDecision(
            should_enter=True,
            reason=(
                f"0dte_asymmetric entry: catalyst={catalyst}; "
                f"price={price:.2f}; dir={direction}"
            ),
            direction=direction,
        )

    def select_contract(
        self,
        symbol: str,
        direction: str,
        chain: OptionChain,
    ) -> Optional[ContractSelection]:
        """Stubbed — implemented in Prompt C4c."""
        raise NotImplementedError(
            "0dte_asymmetric.select_contract is added in Prompt C4c"
        )

    def evaluate_exit(
        self,
        position: Position,
        current_quote: float,
        market: MarketSnapshot,
        setups: list[SetupScore],
        state: ProfileState,
    ) -> ExitDecision:
        """Stubbed — deferred to Phase 2 per ARCHITECTURE.md §4.2.

        The 0DTE asymmetric preset runs in signal-only mode through
        Phase 1b; exit logic from §4.2 lands when execution wires in
        (after the FINRA PDT rule lifts on 2026-06-04).
        """
        raise NotImplementedError(
            "0dte_asymmetric.evaluate_exit is deferred to Phase 2 "
            "(signal-only mode through Phase 1b; see ARCHITECTURE.md §4.2)"
        )

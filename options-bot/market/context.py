"""Market context engine — regime + time-of-day classification, updated every 5 min."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from market.signals import (
    compute_directional_move, compute_range,
    count_reversals, compute_volume_ratio, fetch_vix_open,
)

logger = logging.getLogger("options-bot.market.context")


class Regime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    CHOPPY = "CHOPPY"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


class TimeOfDay(str, Enum):
    OPEN = "OPEN"                # 9:30-10:15
    MID_MORNING = "MID_MORNING"  # 10:15-11:30
    MIDDAY = "MIDDAY"            # 11:30-14:00
    POWER_HOUR = "POWER_HOUR"    # 14:00-15:30
    CLOSE = "CLOSE"              # 15:30-16:00
    OUTSIDE = "OUTSIDE"          # Before/after market hours


@dataclass
class MarketSnapshot:
    """Full context with all input values for logging."""
    regime: Regime
    time_of_day: TimeOfDay
    timestamp: str
    spy_30min_move_pct: float = 0.0
    spy_60min_range_pct: float = 0.0
    spy_30min_reversals: int = 0
    spy_volume_ratio: float = 0.0
    vix_level: float = 0.0
    vix_intraday_change_pct: float = 0.0
    regime_reason: str = ""

TRENDING_MOVE_PCT = 0.25      # SPY 30m move for TRENDING (was 0.4 — missed grind-up days)
CHOPPY_RANGE_PCT = 0.3        # SPY 60m range for CHOPPY
CHOPPY_REVERSALS = 3          # Direction changes for CHOPPY
HIGH_VOL_VIX = 25             # VIX level for HIGH_VOLATILITY
HIGH_VOL_SPY_MOVE_PCT = 1.5   # SPY 30m move for HIGH_VOLATILITY
HIGH_VOL_VIX_SPIKE_PCT = 20   # VIX intraday % for HIGH_VOLATILITY
TRENDING_VOLUME_MIN = 1.0     # Vol ratio for TRENDING


class MarketContext:
    """Computes and caches market regime classification."""

    def __init__(self, data_client=None):
        self._client = data_client
        self._last_snapshot: Optional[MarketSnapshot] = None
        self._last_update: float = 0.0
        self._update_interval: float = 300.0  # 5 minutes
        self._vix_open: Optional[float] = None

    def update(self, force: bool = False) -> MarketSnapshot:
        """Recompute market context. Cached 5 min unless force=True."""
        now = time.time()
        if not force and self._last_snapshot and (now - self._last_update) < self._update_interval:
            return self._last_snapshot

        if self._client is None:
            from data.unified_client import UnifiedDataClient
            self._client = UnifiedDataClient()

        spy_bars = self._client.get_stock_bars("SPY", "1Min", 60)
        vix = self._client.get_vix()

        # Compute input signals
        spy_30m_move = compute_directional_move(spy_bars, 30)
        spy_60m_range = compute_range(spy_bars, 60)
        spy_30m_rev = count_reversals(spy_bars, 30)
        spy_vol_ratio = compute_volume_ratio(spy_bars)
        vix_change = self._vix_intraday_change(vix)

        # ============================================================
        # REGIME EVALUATION — STRICT PRIORITY ORDER
        #
        # Priority 1: HIGH_VOLATILITY (evaluated first, wins always)
        # Priority 2: CHOPPY (evaluated second)
        # Priority 3: TRENDING_UP / TRENDING_DOWN (evaluated third)
        # Priority 4: CHOPPY (default — when in doubt, market is choppy)
        #
        # This order is intentional. Conditions can overlap.
        # HIGH_VOLATILITY always wins because risk rules change.
        # ============================================================

        regime = Regime.CHOPPY
        reason = "default (no conditions met)"

        # --- Priority 1: HIGH_VOLATILITY ---
        if vix >= HIGH_VOL_VIX:
            regime = Regime.HIGH_VOLATILITY
            reason = f"VIX={vix:.1f} >= {HIGH_VOL_VIX}"
        elif abs(spy_30m_move) >= HIGH_VOL_SPY_MOVE_PCT:
            regime = Regime.HIGH_VOLATILITY
            reason = f"SPY 30m move={spy_30m_move:+.2f}% >= {HIGH_VOL_SPY_MOVE_PCT}%"
        elif vix_change >= HIGH_VOL_VIX_SPIKE_PCT:
            regime = Regime.HIGH_VOLATILITY
            reason = f"VIX intraday +{vix_change:.1f}% >= {HIGH_VOL_VIX_SPIKE_PCT}%"

        # --- Priority 2: CHOPPY ---
        elif spy_60m_range < CHOPPY_RANGE_PCT:
            regime = Regime.CHOPPY
            reason = f"SPY 60m range={spy_60m_range:.3f}% < {CHOPPY_RANGE_PCT}%"
        elif spy_30m_rev >= CHOPPY_REVERSALS:
            regime = Regime.CHOPPY
            reason = f"SPY 30m reversals={spy_30m_rev} >= {CHOPPY_REVERSALS}"

        # --- Priority 3: TRENDING ---
        elif spy_30m_move >= TRENDING_MOVE_PCT and spy_vol_ratio >= TRENDING_VOLUME_MIN:
            regime = Regime.TRENDING_UP
            reason = (f"SPY +{spy_30m_move:.2f}% >= {TRENDING_MOVE_PCT}%, "
                      f"vol={spy_vol_ratio:.2f}x >= {TRENDING_VOLUME_MIN}x")
        elif spy_30m_move <= -TRENDING_MOVE_PCT and spy_vol_ratio >= TRENDING_VOLUME_MIN:
            regime = Regime.TRENDING_DOWN
            reason = (f"SPY {spy_30m_move:+.2f}% <= -{TRENDING_MOVE_PCT}%, "
                      f"vol={spy_vol_ratio:.2f}x >= {TRENDING_VOLUME_MIN}x")

        # --- Priority 4: Default = CHOPPY (already set) ---

        tod = self._classify_time_of_day()

        snapshot = MarketSnapshot(
            regime=regime, time_of_day=tod,
            timestamp=datetime.utcnow().isoformat(),
            spy_30min_move_pct=round(spy_30m_move, 4),
            spy_60min_range_pct=round(spy_60m_range, 4),
            spy_30min_reversals=spy_30m_rev,
            spy_volume_ratio=round(spy_vol_ratio, 2),
            vix_level=round(vix, 2),
            vix_intraday_change_pct=round(vix_change, 2),
            regime_reason=reason,
        )

        self._last_snapshot = snapshot
        self._last_update = now
        logger.info(f"Market context: {regime.value} ({reason}) | ToD={tod.value}")
        return snapshot

    def get_regime(self) -> Regime:
        """Return current regime. Calls update() if stale."""
        return self.update().regime

    def get_time_of_day(self) -> TimeOfDay:
        """Return current time-of-day classification."""
        return self._classify_time_of_day()

    def get_snapshot(self) -> MarketSnapshot:
        """Return full context with all input values. Calls update() if stale."""
        return self.update()

    def _vix_intraday_change(self, current_vix: float) -> float:
        """VIX % change from today's 9:30 AM ET open (fetched from Yahoo Finance)."""
        if self._vix_open is None:
            self._vix_open = fetch_vix_open()
            if self._vix_open is None:
                logger.warning("Could not fetch VIX open — using current value as baseline")
                self._vix_open = current_vix
                return 0.0
        if self._vix_open == 0:
            return 0.0
        return ((current_vix - self._vix_open) / self._vix_open) * 100

    def _classify_time_of_day(self) -> TimeOfDay:
        """Classify current ET time into market session period."""
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            from datetime import timedelta
            now = datetime.utcnow() - timedelta(hours=4)

        t = now.hour * 60 + now.minute
        if t < 570:    return TimeOfDay.OUTSIDE
        elif t < 615:  return TimeOfDay.OPEN
        elif t < 690:  return TimeOfDay.MID_MORNING
        elif t < 840:  return TimeOfDay.MIDDAY
        elif t < 930:  return TimeOfDay.POWER_HOUR
        elif t < 960:  return TimeOfDay.CLOSE
        else:          return TimeOfDay.OUTSIDE

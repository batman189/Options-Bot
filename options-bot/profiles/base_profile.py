"""Abstract base for strategy profiles. Profiles consume scanner + scorer
outputs and decide whether to trade. They do NOT call Lumibot directly —
they return decisions that the integration layer executes.

Configurable fields (Phase 9 adjustable without code changes):
  - min_confidence: threshold for entry (adjusted by learning layer)
  - supported_regimes: which regimes this profile trades in
  - max_hold_minutes: maximum position duration
  - hard_stop_pct: backstop loss percentage (35% default)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from config import MACRO_EVENT_BUFFER_MINUTES
from macro.reader import MacroContext, events_for_symbol, snapshot_macro_context
from market.context import Regime
from scoring.scorer import ScoringResult

logger = logging.getLogger("options-bot.profiles")


@dataclass
class EntryDecision:
    """What the profile tells the integration layer."""
    enter: bool
    symbol: str
    direction: str            # "bullish" or "bearish"
    confidence: float
    hold_minutes: int         # Expected hold time for options selector
    reason: str               # Why entering or not
    profile_name: str


@dataclass
class ExitDecision:
    """What the profile tells the integration layer about an open position."""
    exit: bool
    reason: str               # "thesis_broken", "thesis_weakening", "time_decay", "profit_lock", "hard_stop", "stale_data"
    scale_out: bool = False   # True = close half, False = close all


@dataclass
class PositionState:
    """Tracked state for an open position managed by a profile."""
    trade_id: str
    symbol: str
    direction: str
    entry_confidence: float
    entry_setup_score: float
    entry_time: str
    entry_price: float
    current_pnl_pct: float = 0.0
    peak_pnl_pct: float = 0.0
    cycles_without_score: int = 0
    scaled_out: bool = False
    weak_readings: int = 0  # consecutive below-threshold scanner readings


class BaseProfile(ABC):
    """Abstract base for all strategy profiles."""

    def __init__(self, name: str, min_confidence: float, supported_regimes: list[Regime],
                 max_hold_minutes: int, hard_stop_pct: float = 35.0,
                 profit_target_pct: float = 50.0,
                 trailing_stop_pct: float = 0.0,
                 stale_cycles_before_exit: Optional[int] = None,
                 check_interval_seconds: int = 60,
                 no_entry_after_et_hour: Optional[int] = None,
                 force_close_et_hhmm: Optional[str] = None):
        self.name = name
        self.min_confidence = min_confidence       # Phase 9 adjustable
        self.supported_regimes = supported_regimes
        self.max_hold_minutes = max_hold_minutes
        self.hard_stop_pct = hard_stop_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.profit_target_pct = profit_target_pct
        self.stale_cycles_before_exit = stale_cycles_before_exit  # None = hold forever
        self.check_interval_seconds = check_interval_seconds  # Trade manager polling frequency
        # Optional time-of-day rules (config-driven, no per-symbol hardcoding):
        #   no_entry_after_et_hour: reject entries once ET clock hour >= value
        #   force_close_et_hhmm:    force position exit at this ET wall time "HH:MM"
        # When either is None the rule does not apply to this profile instance.
        self.no_entry_after_et_hour = no_entry_after_et_hour
        self.force_close_et_hhmm = force_close_et_hhmm
        self._positions: dict[str, PositionState] = {}

    def apply_config(self, config: dict):
        """Apply DB profile config to override hardcoded defaults."""
        if "profit_target_pct" in config:
            self.profit_target_pct = float(config["profit_target_pct"])
        if "trailing_stop_pct" in config:
            self.trailing_stop_pct = float(config["trailing_stop_pct"])
        if "stop_loss_pct" in config:
            self.hard_stop_pct = float(config["stop_loss_pct"])
        if "max_hold_minutes" in config:
            self.max_hold_minutes = int(config["max_hold_minutes"])
        if "min_confidence" in config:
            self.min_confidence = float(config["min_confidence"])
        if "no_entry_after_et_hour" in config:
            val = config["no_entry_after_et_hour"]
            # 0 and None both mean "no cutoff" — any positive int is the ET
            # hour past which entries are rejected. The UI form defaults
            # non-mean_reversion presets to 0 (with "0 disables" in the
            # slider hint) and filters 0 → null on save, but any other
            # writer that stores literal 0 here must be treated as
            # disabled. The pre-fix `val is not None` check treated 0 as
            # "reject every hour" because et_hour >= 0 is always true.
            self.no_entry_after_et_hour = int(val) if val else None
        if "force_close_et_hhmm" in config:
            val = config["force_close_et_hhmm"]
            self.force_close_et_hhmm = str(val) if val else None
        logger.info(
            f"{self.name}: config applied — "
            f"profit_target={self.profit_target_pct}% "
            f"trailing_stop={self.trailing_stop_pct}% "
            f"hard_stop={self.hard_stop_pct}% "
            f"max_hold={self.max_hold_minutes}min "
            f"min_confidence={self.min_confidence:.3f} "
            f"no_entry_after={self.no_entry_after_et_hour} "
            f"force_close={self.force_close_et_hhmm}"
        )

    def should_enter(
        self,
        score_result: ScoringResult,
        regime: Regime,
        macro_ctx: Optional[MacroContext] = None,
    ) -> EntryDecision:
        """Decide whether to enter a trade based on confidence and regime.

        macro_ctx: per-iteration snapshot passed down from v2_strategy. If
        None, a fresh snapshot is taken — convenient for isolated tests,
        wasteful if called in a loop (tests in a loop must pass ctx).
        """
        if regime not in self.supported_regimes:
            return EntryDecision(
                enter=False, symbol=score_result.symbol,
                direction=score_result.direction, confidence=score_result.capped_score,
                hold_minutes=self.max_hold_minutes, profile_name=self.name,
                reason=f"regime {regime.value} not supported by {self.name}",
            )

        # Time-of-day entry cutoff — configurable per profile instance. Reject
        # new entries once the ET wall-clock hour passes the cutoff. None
        # disables the rule. Replaces the old SPY-hardcoded check that used
        # to live in profiles/mean_reversion.py.
        if self.no_entry_after_et_hour is not None:
            try:
                from zoneinfo import ZoneInfo
                from datetime import datetime as _dt
                et_hour = _dt.now(ZoneInfo("America/New_York")).hour
                if et_hour >= self.no_entry_after_et_hour:
                    return EntryDecision(
                        enter=False, symbol=score_result.symbol,
                        direction=score_result.direction,
                        confidence=score_result.capped_score,
                        hold_minutes=self.max_hold_minutes, profile_name=self.name,
                        reason=f"no_entry_after_et_hour: {et_hour}:xx >= cutoff "
                               f"{self.no_entry_after_et_hour}:00",
                    )
            except Exception:
                pass  # Fail-safe: don't block on clock errors

        # Macro event veto — runs BEFORE the confidence check. The scorer
        # veto cap sets capped_score=0.0 when a HIGH event is imminent, which
        # would trip the `confidence < min_confidence` branch below and
        # mislabel the rejection as low-confidence. Checking the macro
        # snapshot here first means the signal log reports the real cause.
        # Belt-and-suspenders with the scorer veto (both use the same
        # MacroContext / reader helper — they stay in sync within one
        # trading iteration). Fail-safe: empty snapshot → events is [] →
        # trade proceeds to the remaining checks.
        ctx = macro_ctx if macro_ctx is not None else snapshot_macro_context()
        active = events_for_symbol(ctx, score_result.symbol)
        high_events = [e for e in active
                       if e.impact_level == "HIGH"
                       and e.minutes_until <= MACRO_EVENT_BUFFER_MINUTES]
        if high_events:
            ev = high_events[0]
            return EntryDecision(
                enter=False, symbol=score_result.symbol,
                direction=score_result.direction, confidence=score_result.capped_score,
                hold_minutes=self.max_hold_minutes, profile_name=self.name,
                reason=f"macro_event_veto: {ev.event_type} in {ev.minutes_until}min",
            )

        if score_result.capped_score < self.min_confidence:
            return EntryDecision(
                enter=False, symbol=score_result.symbol,
                direction=score_result.direction, confidence=score_result.capped_score,
                hold_minutes=self.max_hold_minutes, profile_name=self.name,
                reason=f"confidence {score_result.capped_score:.3f} < {self.min_confidence:.3f}",
            )

        # Profile-specific additional checks
        if not self._profile_specific_entry_check(score_result, regime):
            return EntryDecision(
                enter=False, symbol=score_result.symbol,
                direction=score_result.direction, confidence=score_result.capped_score,
                hold_minutes=self.max_hold_minutes, profile_name=self.name,
                reason=f"{self.name} profile-specific check failed",
            )

        return EntryDecision(
            enter=True, symbol=score_result.symbol,
            direction=score_result.direction, confidence=score_result.capped_score,
            hold_minutes=self.max_hold_minutes, profile_name=self.name,
            reason=f"confidence {score_result.capped_score:.3f} >= {self.min_confidence:.3f} in {regime.value}",
        )

    def check_exit(self, trade_id: str, current_pnl_pct: float,
                    current_setup_score: Optional[float],
                    elapsed_minutes: int) -> ExitDecision:
        """Evaluate exit conditions for an open position.

        Exit priority order (7 levels, evaluated in this exact sequence):
          1. Thesis broken / thesis weakening (primary — profile-specific)
          2. Profit target (configurable per profile: 40-60%)
          3. Time decay protection (80% of max hold and not 20%+ profitable)
          4. Profit lock (80% -> scale out, 50% peak -> breakeven stop)
          5. Hard stop at 35% loss (backstop only)
          6. Stale data (scanner unavailable for N cycles)
          7. Max hold time exceeded
        """
        pos = self._positions.get(trade_id)
        if pos is None:
            return ExitDecision(exit=False, reason="position not tracked")

        # Update state
        pos.current_pnl_pct = current_pnl_pct
        if current_pnl_pct > pos.peak_pnl_pct:
            pos.peak_pnl_pct = current_pnl_pct

        # Track stale data cycles — only if this profile actually consumes
        # the counter. When stale_cycles_before_exit is None (mean_reversion
        # et al.), the counter is never read, so incrementing it is dead
        # state that just grows over time. Short-circuit to make the
        # "profile holds through scanner outages" semantic explicit.
        if self.stale_cycles_before_exit is not None:
            if current_setup_score is None:
                pos.cycles_without_score += 1
            else:
                pos.cycles_without_score = 0

        # --- Priority 1: Thesis evaluation ---
        thesis = self._evaluate_thesis(pos, current_setup_score)
        if thesis is not None:
            return thesis

        # --- Priority 2: Profit target / trailing stop ---
        # Trailing stop latches: once peak_pnl exceeds profit_target, the trail
        # stays active even if current PnL drops below the activation threshold.
        trailing_active = (self.trailing_stop_pct > 0 and
                           pos.peak_pnl_pct >= self.profit_target_pct)
        if trailing_active:
            drawdown_from_peak = pos.peak_pnl_pct - current_pnl_pct
            if drawdown_from_peak >= self.trailing_stop_pct:
                logger.info(
                    f"Trailing stop triggered: peak={pos.peak_pnl_pct:.1f}% "
                    f"current={current_pnl_pct:.1f}% "
                    f"drawdown={drawdown_from_peak:.1f}% >= {self.trailing_stop_pct}%"
                )
                return ExitDecision(exit=True, reason="trailing_stop")
            # Trail active but not triggered — let it run
        elif current_pnl_pct >= self.profit_target_pct:
            if self.trailing_stop_pct <= 0:
                return ExitDecision(exit=True, reason="profit_target")

        # --- Priority 3: Time decay protection ---
        # If held for >80% of max hold time and not sufficiently profitable,
        # exit to avoid theta decay in the remaining window.
        time_threshold = self.max_hold_minutes * 0.80
        if elapsed_minutes > time_threshold and current_pnl_pct < 20.0:
            return ExitDecision(exit=True, reason="time_decay_protection")

        # --- Priority 4: Profit lock ---
        # Skip when trailing stop is active — the trail manages the exit.
        if not trailing_active:
            if current_pnl_pct >= 80.0 and not pos.scaled_out:
                pos.scaled_out = True
                return ExitDecision(exit=True, reason="profit_lock_80", scale_out=True)
            if pos.peak_pnl_pct >= 50.0 and current_pnl_pct <= 0.0:
                return ExitDecision(exit=True, reason="profit_lock_breakeven")

        # --- Priority 5: Hard stop (backstop) ---
        if current_pnl_pct <= -self.hard_stop_pct:
            return ExitDecision(exit=True, reason="hard_stop")

        # --- Priority 6: Stale data ---
        if (self.stale_cycles_before_exit is not None
                and pos.cycles_without_score >= self.stale_cycles_before_exit):
            return ExitDecision(exit=True, reason="stale_data")

        # --- Priority 7: Max hold time ---
        if elapsed_minutes >= self.max_hold_minutes:
            return ExitDecision(exit=True, reason="max_hold_time")

        return ExitDecision(exit=False, reason="thesis_holds")

    def record_entry(self, trade_id: str, symbol: str, direction: str,
                      confidence: float, setup_score: float,
                      entry_time: str, entry_price: float):
        """Called by integration layer after fill confirmation."""
        self._positions[trade_id] = PositionState(
            trade_id=trade_id, symbol=symbol, direction=direction,
            entry_confidence=confidence, entry_setup_score=setup_score,
            entry_time=entry_time, entry_price=entry_price,
        )
        logger.info(f"{self.name} recorded entry: {trade_id[:8]} {symbol} {direction} conf={confidence:.3f}")

    def record_exit(self, trade_id: str):
        """Called by integration layer after exit."""
        self._positions.pop(trade_id, None)

    @abstractmethod
    def _profile_specific_entry_check(self, score_result: ScoringResult, regime: Regime) -> bool:
        """Override for additional entry checks. Return True to allow."""
        ...

    @abstractmethod
    def _evaluate_thesis(self, pos: PositionState, current_setup_score: Optional[float]) -> Optional[ExitDecision]:
        """Override to implement thesis-based exit logic. Return ExitDecision or None to continue."""
        ...

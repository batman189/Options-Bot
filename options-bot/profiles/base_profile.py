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
from dataclasses import dataclass, field
from typing import Optional

from market.context import Regime, TimeOfDay
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


class BaseProfile(ABC):
    """Abstract base for all strategy profiles."""

    def __init__(self, name: str, min_confidence: float, supported_regimes: list[Regime],
                 max_hold_minutes: int, hard_stop_pct: float = 35.0,
                 profit_target_pct: float = 50.0,
                 stale_cycles_before_exit: Optional[int] = None,
                 check_interval_seconds: int = 60):
        self.name = name
        self.min_confidence = min_confidence       # Phase 9 adjustable
        self.supported_regimes = supported_regimes
        self.max_hold_minutes = max_hold_minutes
        self.hard_stop_pct = hard_stop_pct
        self.profit_target_pct = profit_target_pct
        self.stale_cycles_before_exit = stale_cycles_before_exit  # None = hold forever
        self.check_interval_seconds = check_interval_seconds  # Trade manager polling frequency
        self._positions: dict[str, PositionState] = {}

    def should_enter(self, score_result: ScoringResult, regime: Regime) -> EntryDecision:
        """Decide whether to enter a trade based on confidence and regime."""
        if regime not in self.supported_regimes:
            return EntryDecision(
                enter=False, symbol=score_result.symbol,
                direction=score_result.direction, confidence=score_result.capped_score,
                hold_minutes=self.max_hold_minutes, profile_name=self.name,
                reason=f"regime {regime.value} not supported by {self.name}",
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

        # Track stale data cycles
        if current_setup_score is None:
            pos.cycles_without_score += 1
        else:
            pos.cycles_without_score = 0

        # --- Priority 1: Thesis evaluation ---
        thesis = self._evaluate_thesis(pos, current_setup_score)
        if thesis is not None:
            return thesis

        # --- Priority 2: Profit target ---
        if current_pnl_pct >= self.profit_target_pct:
            return ExitDecision(exit=True, reason="profit_target")

        # --- Priority 3: Time decay protection ---
        # If held for >80% of max hold time and not sufficiently profitable,
        # exit to avoid theta decay in the remaining window.
        time_threshold = self.max_hold_minutes * 0.80
        if elapsed_minutes > time_threshold and current_pnl_pct < 20.0:
            return ExitDecision(exit=True, reason="time_decay_protection")

        # --- Priority 4: Profit lock ---
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

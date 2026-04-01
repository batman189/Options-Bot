"""Catalyst/Event profile — trades news-driven moves.
All regimes except HIGH_VOLATILITY. Minutes to hours hold.
Thesis: sentiment signal is still strong AND options flow confirms.
Exits immediately if signal cannot be confirmed."""

import logging
from typing import Optional

from market.context import Regime
from scoring.scorer import ScoringResult
from profiles.base_profile import BaseProfile, ExitDecision, PositionState

logger = logging.getLogger("options-bot.profiles.catalyst")

# Thesis thresholds
THESIS_STRONG = 0.35     # Catalyst score above this = event still driving
THESIS_DISSIPATED = 0.15 # Below this = event impact faded


class CatalystProfile(BaseProfile):
    """Catalyst: trades confirmed news events with unusual options flow."""

    def __init__(self, min_confidence: float = 0.72):
        super().__init__(
            name="catalyst",
            min_confidence=min_confidence,  # Higher bar (binary risk)
            supported_regimes=[
                Regime.TRENDING_UP,
                Regime.TRENDING_DOWN,
                Regime.CHOPPY,
                # NOT HIGH_VOLATILITY — options already overpriced
            ],
            max_hold_minutes=240,     # 4 hours max
            hard_stop_pct=35.0,
            stale_cycles_before_exit=1,  # Exit IMMEDIATELY on missing data
            check_interval_seconds=60,   # Evaluated every 60s by trade manager
        )

    def _profile_specific_entry_check(self, score_result: ScoringResult, regime: Regime) -> bool:
        """Catalyst requires the setup_type to actually be 'catalyst'.
        A high confidence momentum signal should not trigger a catalyst profile."""
        if score_result.setup_type != "catalyst":
            logger.info(f"Catalyst: setup_type={score_result.setup_type} is not catalyst — skip")
            return False
        return True

    def _evaluate_thesis(self, pos: PositionState, current_setup_score: Optional[float]) -> Optional[ExitDecision]:
        """Catalyst thesis: is the event still driving the move?

        Catalyst trades live and die by the signal. If sentiment
        dissipates or unusual volume dries up, the thesis is gone.
        Unlike momentum, there is no "fading" state — it's binary.
        """
        if current_setup_score is None:
            # Stale data = immediate exit (stale_cycles_before_exit=1)
            return None  # Base class handles this

        if current_setup_score < THESIS_DISSIPATED:
            logger.info(f"Catalyst thesis DISSIPATED: score={current_setup_score:.3f} < {THESIS_DISSIPATED}")
            return ExitDecision(exit=True, reason="thesis_broken")

        # Catalyst above 2x premium = consider taking profit
        if pos.current_pnl_pct >= 100.0:
            logger.info(f"Catalyst profit target: pnl={pos.current_pnl_pct:.1f}% >= 100%")
            return ExitDecision(exit=True, reason="thesis_profit_target")

        return None  # Event still active, hold

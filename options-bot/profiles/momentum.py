"""Momentum profile — rides strong directional moves.
TRENDING_UP or TRENDING_DOWN only. 20 min to 2 hour hold.
Thesis: directional bars still strong with volume. Exits when momentum fades."""

import logging
from typing import Optional

from market.context import Regime
from scoring.scorer import ScoringResult
from profiles.base_profile import BaseProfile, ExitDecision, PositionState

logger = logging.getLogger("options-bot.profiles.momentum")

# Thesis thresholds
THESIS_STRONG = 0.40     # Setup score above this = thesis holds
THESIS_WEAKENING = 0.20  # Below this = thesis broken
THESIS_FADING = 0.30     # Between weakening and strong = fading (scale out)


class MomentumProfile(BaseProfile):
    """Momentum: trades consistent directional moves with volume."""

    def __init__(self, min_confidence: float = 0.65):
        super().__init__(
            name="momentum",
            min_confidence=min_confidence,
            supported_regimes=[Regime.TRENDING_UP, Regime.TRENDING_DOWN],
            max_hold_minutes=120,     # 2 hours max
            hard_stop_pct=35.0,
            profit_target_pct=40.0,   # Faster scalp target
            stale_cycles_before_exit=2,  # Exit after 2 missed scanner cycles
            check_interval_seconds=60,   # Evaluated every 60s by trade manager
        )

    def _profile_specific_entry_check(self, score_result: ScoringResult, regime: Regime) -> bool:
        """Momentum requires the direction to match the regime."""
        if regime == Regime.TRENDING_UP and score_result.direction == "bearish":
            logger.info(f"Momentum: bearish signal in TRENDING_UP — skipping (counter-trend)")
            return False
        if regime == Regime.TRENDING_DOWN and score_result.direction == "bullish":
            logger.info(f"Momentum: bullish signal in TRENDING_DOWN — skipping (counter-trend)")
            return False
        return True

    def _evaluate_thesis(self, pos: PositionState, current_setup_score: Optional[float]) -> Optional[ExitDecision]:
        """Momentum thesis: is the directional move still happening?

        The setup score from the scanner reflects whether bars are still
        directional with volume. When it drops, momentum is fading.
        """
        if current_setup_score is None:
            return None  # Stale data handled by base class (2 cycle limit)

        if current_setup_score < THESIS_WEAKENING:
            logger.info(f"Momentum thesis BROKEN: score={current_setup_score:.3f} < {THESIS_WEAKENING}")
            return ExitDecision(exit=True, reason="thesis_broken")

        if current_setup_score < THESIS_FADING and not pos.scaled_out:
            logger.info(f"Momentum thesis FADING: score={current_setup_score:.3f} < {THESIS_FADING}")
            pos.scaled_out = True
            return ExitDecision(exit=True, reason="thesis_weakening", scale_out=True)

        return None  # Thesis holds

"""Mean Reversion profile — trades extended moves returning to mean.
Prefers CHOPPY or end of TRENDING. Holds 30 min to 3 days.
Thesis: price is still statistically extended from the mean."""

import logging
from typing import Optional

from market.context import Regime
from scoring.scorer import ScoringResult
from profiles.base_profile import BaseProfile, ExitDecision, PositionState

logger = logging.getLogger("options-bot.profiles.mean_reversion")

# Thesis thresholds
THESIS_STILL_EXTENDED = 0.25  # Setup score above this = still extended, hold
THESIS_RESOLVED = 0.10        # Below this = price returned to mean, exit


class MeanReversionProfile(BaseProfile):
    """Mean Reversion: trades oversold/overbought conditions reverting."""

    def __init__(self, min_confidence: float = 0.60):
        super().__init__(
            name="mean_reversion",
            min_confidence=min_confidence,
            supported_regimes=[
                Regime.CHOPPY,
                Regime.TRENDING_UP,     # End-of-trend exhaustion
                Regime.TRENDING_DOWN,   # End-of-trend exhaustion
                # NOT HIGH_VOLATILITY — options too expensive
            ],
            max_hold_minutes=4320,     # 3 days (72 hours)
            hard_stop_pct=35.0,
            stale_cycles_before_exit=None,  # Hold through scanner outages
            check_interval_seconds=300,    # Evaluated every 5 min by trade manager
        )

    def _profile_specific_entry_check(self, score_result: ScoringResult, regime: Regime) -> bool:
        """Mean reversion in TRENDING regimes requires the signal to be
        counter-trend (buying the dip in an uptrend, or selling the rip
        in a downtrend). In CHOPPY, any direction is valid."""
        if regime == Regime.TRENDING_UP and score_result.direction == "bullish":
            logger.info("MeanRev: bullish reversion in TRENDING_UP — not counter-trend, skip")
            return False
        if regime == Regime.TRENDING_DOWN and score_result.direction == "bearish":
            logger.info("MeanRev: bearish reversion in TRENDING_DOWN — not counter-trend, skip")
            return False
        return True

    def _evaluate_thesis(self, pos: PositionState, current_setup_score: Optional[float]) -> Optional[ExitDecision]:
        """Mean reversion thesis: is price still extended from the mean?

        The setup score reflects RSI extremes, BB position, and distance
        from mean. When the score drops to near zero, price has returned
        to the mean — the trade has worked and should be closed.
        """
        if current_setup_score is None:
            return None  # Hold through missing data (stale_cycles=None)

        if current_setup_score < THESIS_RESOLVED:
            logger.info(f"MeanRev thesis RESOLVED: score={current_setup_score:.3f} < {THESIS_RESOLVED} (mean reached)")
            return ExitDecision(exit=True, reason="thesis_broken")

        # RSI crossing back through 50 = mean reached (implicit in low score)
        return None  # Still extended, hold

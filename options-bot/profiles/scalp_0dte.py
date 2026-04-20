"""0DTE Scalp profile — fast directional trades on any liquid underlying.
Trades any regime except HIGH_VOLATILITY. Always 0DTE. OTM strike.
Hold 10-45 minutes. Trailing stop after 60% gain.
Thesis: price is moving directionally with volume RIGHT NOW."""

from market.context import Regime
from scoring.scorer import ScoringResult
from profiles.base_profile import BaseProfile, ExitDecision, PositionState
from typing import Optional
import logging

logger = logging.getLogger("options-bot.profiles.scalp_0dte")

THESIS_STRONG = 0.30
THESIS_BROKEN = 0.15


class Scalp0DTEProfile(BaseProfile):
    """Aggressive 0DTE scalp. Enters on momentum, compression, or macro_trend."""

    def __init__(self, min_confidence: float = 0.55):
        super().__init__(
            name="scalp_0dte",
            min_confidence=min_confidence,
            supported_regimes=[
                Regime.TRENDING_UP,
                Regime.TRENDING_DOWN,
                Regime.CHOPPY,
            ],
            max_hold_minutes=45,
            hard_stop_pct=25.0,
            profit_target_pct=60.0,
            stale_cycles_before_exit=1,
            check_interval_seconds=60,
        )
        self.trailing_stop_pct = 25.0

    def _profile_specific_entry_check(self, score_result: ScoringResult, regime: Regime) -> bool:
        """Accept all setups except mean_reversion and catalyst."""
        if score_result.setup_type == "mean_reversion":
            return False
        if score_result.setup_type == "catalyst":
            return False
        if score_result.setup_type == "momentum":
            if regime == Regime.TRENDING_UP and score_result.direction == "bearish":
                return False
            if regime == Regime.TRENDING_DOWN and score_result.direction == "bullish":
                return False
        return True

    def _evaluate_thesis(self, pos: PositionState, current_setup_score: Optional[float]) -> Optional[ExitDecision]:
        """Is the move still going? Require two consecutive weak readings
        before exiting — one noisy bar should not close a winning trade.
        None score is handled by stale_cycles_before_exit (=1) in base class."""
        if current_setup_score is None:
            return ExitDecision(exit=True, reason="thesis_broken")
        if current_setup_score < THESIS_BROKEN:
            pos.weak_readings += 1
            if pos.weak_readings >= 2:
                logger.info(
                    f"Scalp0DTE: thesis broken ({pos.weak_readings} weak readings), "
                    f"score={current_setup_score:.3f}"
                )
                return ExitDecision(exit=True, reason="thesis_broken")
            logger.info(
                f"Scalp0DTE: weak reading {pos.weak_readings}/2 "
                f"score={current_setup_score:.3f} — holding"
            )
            return None
        pos.weak_readings = 0
        return None

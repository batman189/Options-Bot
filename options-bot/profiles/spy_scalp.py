"""SPY 0DTE Scalp profile — fast directional trades on SPY.
Trades any regime except HIGH_VOLATILITY. Always 0DTE. ATM strike.
Hold 10-45 minutes. Exit at 50% profit or 25% loss.
Thesis: price is moving directionally with volume RIGHT NOW."""

from market.context import Regime
from scoring.scorer import ScoringResult
from profiles.base_profile import BaseProfile, ExitDecision, PositionState
from typing import Optional
import logging

logger = logging.getLogger("options-bot.profiles.spy_scalp")

THESIS_STRONG = 0.30      # Setup score above this = move still happening
THESIS_BROKEN = 0.15      # Below this = move stalled, exit


class SPY0DTEScalpProfile(BaseProfile):
    """Aggressive 0DTE scalp on SPY. Enters on momentum OR compression breakout."""

    def __init__(self, min_confidence: float = 0.55):
        super().__init__(
            name="spy_scalp",
            min_confidence=min_confidence,
            supported_regimes=[
                Regime.TRENDING_UP,
                Regime.TRENDING_DOWN,
                Regime.CHOPPY,           # Trades CHOPPY too — breakouts happen in range days
                # NOT HIGH_VOLATILITY — spreads too wide, fills terrible
            ],
            max_hold_minutes=45,          # Hard cap — never hold 0DTE more than 45 min
            hard_stop_pct=25.0,           # Tighter stop — 0DTE can go to zero fast
            profit_target_pct=50.0,       # Take 50% and move on
            stale_cycles_before_exit=1,   # Exit immediately if scanner goes dark
            check_interval_seconds=60,
        )

    def _profile_specific_entry_check(self, score_result: ScoringResult, regime: Regime) -> bool:
        """Accept momentum and compression_breakout setups. Not mean_reversion (too slow for 0DTE)."""
        if score_result.setup_type == "mean_reversion":
            logger.info("SPY0DTE: rejecting mean_reversion — wrong setup for 0DTE scalp")
            return False
        if score_result.setup_type == "catalyst":
            logger.info("SPY0DTE: rejecting catalyst — sentiment unreliable for SPY")
            return False
        # Require directional alignment with regime for momentum setups
        if score_result.setup_type == "momentum":
            if regime == Regime.TRENDING_UP and score_result.direction == "bearish":
                return False
            if regime == Regime.TRENDING_DOWN and score_result.direction == "bullish":
                return False
        return True

    def _evaluate_thesis(self, pos: PositionState, current_setup_score: Optional[float]) -> Optional[ExitDecision]:
        """Is SPY still moving? If the setup score drops, the move is over."""
        if current_setup_score is None:
            return ExitDecision(exit=True, reason="thesis_broken")
        if current_setup_score < THESIS_BROKEN:
            logger.info(f"SPY0DTE: move stalled, score={current_setup_score:.3f}")
            return ExitDecision(exit=True, reason="thesis_broken")
        return None

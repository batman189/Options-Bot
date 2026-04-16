"""SPY Swing profile — multi-day directional trades on SPY.
Targets 2-5 DTE options on confirmed trends. Holds 1-3 days.
Higher confidence bar than scalp. Wider profit target — let winners run.
Thesis: regime is clearly trending and the move has more room to go."""

import logging
from typing import Optional

from market.context import Regime
from scoring.scorer import ScoringResult
from profiles.base_profile import BaseProfile, ExitDecision, PositionState

logger = logging.getLogger("options-bot.profiles.spy_swing")

THESIS_STRONG = 0.35      # Setup score above this = trend still intact
THESIS_BROKEN = 0.15      # Below this = trend exhausted, exit


class SPYSwingProfile(BaseProfile):
    """SPY Swing: trades confirmed TRENDING regimes with 2-5 DTE options."""

    def __init__(self, min_confidence: float = 0.68):
        super().__init__(
            name="spy_swing",
            min_confidence=min_confidence,
            supported_regimes=[
                Regime.TRENDING_UP,
                Regime.TRENDING_DOWN,
            ],
            max_hold_minutes=4320,            # 3 days max
            hard_stop_pct=40.0,               # Wider stop for multi-day hold
            profit_target_pct=100.0,          # Let winners run — swing for 2x
            stale_cycles_before_exit=None,    # Hold through scanner outages
            check_interval_seconds=300,       # Check every 5 min
        )
        self.trailing_stop_pct = 35.0  # Wider trail for multi-day swing

    def _profile_specific_entry_check(self, score_result: ScoringResult, regime: Regime) -> bool:
        """Swing only takes momentum setups aligned with the trend direction."""
        if score_result.setup_type not in ("momentum", "compression_breakout"):
            logger.info(f"SPYSwing: rejecting setup_type={score_result.setup_type}")
            return False
        if regime == Regime.TRENDING_UP and score_result.direction == "bearish":
            logger.info("SPYSwing: bearish signal in TRENDING_UP — counter-trend, skip")
            return False
        if regime == Regime.TRENDING_DOWN and score_result.direction == "bullish":
            logger.info("SPYSwing: bullish signal in TRENDING_DOWN — counter-trend, skip")
            return False
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime as _dt
            hour = _dt.now(ZoneInfo("America/New_York")).hour
            if hour >= 15:
                logger.info("SPYSwing: no new entries after 3 PM ET")
                return False
        except Exception:
            pass
        return True

    def _evaluate_thesis(self, pos: PositionState, current_setup_score: Optional[float]) -> Optional[ExitDecision]:
        """Swing thesis: is the trend still intact?"""
        if current_setup_score is None:
            return None  # Hold through scanner outages
        if current_setup_score < THESIS_BROKEN:
            logger.info(f"SPYSwing: trend exhausted, score={current_setup_score:.3f}")
            return ExitDecision(exit=True, reason="thesis_broken")
        return None

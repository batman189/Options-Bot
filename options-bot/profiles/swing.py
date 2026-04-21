"""Swing profile — multi-day directional trades on confirmed trends.
Targets 2-5 DTE options. Holds 1-3 days. Higher confidence bar.
Thesis: regime is clearly trending and the move has more room to go."""

import logging
from typing import Optional

from market.context import Regime
from scoring.scorer import ScoringResult
from profiles.base_profile import BaseProfile, ExitDecision, PositionState

logger = logging.getLogger("options-bot.profiles.swing")

THESIS_STRONG = 0.35
THESIS_BROKEN = 0.15


class SwingProfile(BaseProfile):
    """Swing: trades confirmed TRENDING regimes with multi-day DTE options."""

    def __init__(self, min_confidence: float = 0.68):
        super().__init__(
            name="swing",
            min_confidence=min_confidence,
            supported_regimes=[
                Regime.TRENDING_UP,
                Regime.TRENDING_DOWN,
            ],
            max_hold_minutes=4320,
            hard_stop_pct=40.0,
            profit_target_pct=100.0,
            stale_cycles_before_exit=None,
            check_interval_seconds=300,
            # Aggregator: matches the _profile_specific_entry_check `in`
            # tuple below.
            accepted_setup_types={"momentum", "compression_breakout", "macro_trend"},
        )
        self.trailing_stop_pct = 35.0

    def _profile_specific_entry_check(self, score_result: ScoringResult, regime: Regime) -> bool:
        """Swing only takes momentum/compression setups aligned with trend."""
        if score_result.setup_type not in ("momentum", "compression_breakout", "macro_trend"):
            return False
        if regime == Regime.TRENDING_UP and score_result.direction == "bearish":
            return False
        if regime == Regime.TRENDING_DOWN and score_result.direction == "bullish":
            return False
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime as _dt
            if _dt.now(ZoneInfo("America/New_York")).hour >= 15:
                return False
        except Exception:
            pass
        return True

    def _evaluate_thesis(self, pos: PositionState, current_setup_score: Optional[float]) -> Optional[ExitDecision]:
        """Is the trend still intact?"""
        if current_setup_score is None:
            return None
        if current_setup_score < THESIS_BROKEN:
            logger.info(f"Swing: trend exhausted, score={current_setup_score:.3f}")
            return ExitDecision(exit=True, reason="thesis_broken")
        return None

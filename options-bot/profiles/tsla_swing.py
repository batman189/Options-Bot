"""TSLA Swing profile — multi-day directional trades on volatile stocks.
Uses the 'swing' preset config. 7-14 DTE options. Holds 2-7 days.
Wider stops than SPY swing — TSLA moves 5-10% intraday regularly.
Thesis: confirmed trend with strong momentum on 15-min and 1-min bars."""

import logging
from typing import Optional
from market.context import Regime
from scoring.scorer import ScoringResult
from profiles.base_profile import BaseProfile, ExitDecision, PositionState

logger = logging.getLogger("options-bot.profiles.tsla_swing")

THESIS_BROKEN = 0.15


class TSLASwingProfile(BaseProfile):
    """Swing trades on TSLA and other volatile single stocks."""

    def __init__(self, min_confidence: float = 0.72):
        super().__init__(
            name="tsla_swing",
            min_confidence=min_confidence,
            supported_regimes=[
                Regime.TRENDING_UP,
                Regime.TRENDING_DOWN,
            ],
            max_hold_minutes=10080,    # 7 days max
            hard_stop_pct=50.0,        # TSLA can drop 10% in a day
            profit_target_pct=100.0,   # Trailing activates at 2x
            stale_cycles_before_exit=None,
            check_interval_seconds=300,
        )
        self.trailing_stop_pct = 40.0  # Wider trail — TSLA whipsaws

    def _profile_specific_entry_check(self, score_result: ScoringResult, regime: Regime) -> bool:
        """Only momentum and macro_trend setups. Direction must match regime."""
        if score_result.setup_type not in ("momentum", "macro_trend"):
            return False
        if regime == Regime.TRENDING_UP and score_result.direction == "bearish":
            return False
        if regime == Regime.TRENDING_DOWN and score_result.direction == "bullish":
            return False
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime as _dt
            if _dt.now(ZoneInfo("America/New_York")).hour >= 13:
                return False
        except Exception:
            pass
        return True

    def _evaluate_thesis(self, pos: PositionState, current_setup_score: Optional[float]) -> Optional[ExitDecision]:
        """Trend still intact? Hold through minor dips."""
        if current_setup_score is None:
            return None
        if current_setup_score < THESIS_BROKEN:
            logger.info(f"TSLASwing: trend broken, score={current_setup_score:.3f}")
            return ExitDecision(exit=True, reason="thesis_broken")
        return None

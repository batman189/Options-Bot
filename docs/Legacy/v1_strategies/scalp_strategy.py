"""
Scalp trading strategy — 0DTE options on SPY.
Matches PROJECT_ARCHITECTURE.md Section 6 — Scalp preset (Phase 5).

Configuration (from preset defaults):
    - min_dte: 0
    - max_dte: 0
    - sleeptime: 1M (1 minute)
    - max_hold_days: 0 (same day exit)
    - prediction_horizon: 30min
    - profit_target_pct: 20
    - stop_loss_pct: 15
    - min_confidence: 0.60 (replaces min_predicted_move_pct)
    - requires_min_equity: 25000

All trading logic inherited from BaseOptionsStrategy, which has scalp-specific
branches for:
    - 1-minute bar fetching and feature computation
    - Confidence threshold instead of predicted move threshold
    - Adapted EV calculation using signed confidence
    - Same-day forced exit at 3:45 PM ET
    - $25K equity gate at startup

This class exists to:
    1. Be explicitly named for clarity in logs and Lumibot's Trader registry
    2. Be registered in main.py's _get_strategy_class() mapping
    3. Ensure the correct feature set (scalp_features) is applied via self.preset
"""

import logging

from strategies.base_strategy import BaseOptionsStrategy

logger = logging.getLogger("options-bot.strategy.scalp")


class ScalpStrategy(BaseOptionsStrategy):
    """Scalp trading strategy — 0DTE options, 1-minute iterations, same-day exit."""
    pass

"""
Swing trading strategy.
Matches PROJECT_ARCHITECTURE.md Section 6 — Swing preset.

Configuration (from preset defaults):
    - min_dte: 7
    - max_dte: 45
    - max_hold_days: 7
    - prediction_horizon: 5d
    - profit_target_pct: 50
    - stop_loss_pct: 30
    - sleeptime: 5M

All trading logic inherited from BaseOptionsStrategy.
This class exists to:
    1. Be explicitly named for clarity
    2. Allow swing-specific overrides in the future
"""

import logging

from strategies.base_strategy import BaseOptionsStrategy

logger = logging.getLogger("options-bot.strategy.swing")


class SwingStrategy(BaseOptionsStrategy):
    """Swing trading strategy — 7+ DTE options, hold up to 7 days."""
    pass

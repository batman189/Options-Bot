"""
General trading strategy.
Matches PROJECT_ARCHITECTURE.md Section 6 — General preset.

Configuration (from preset defaults):
    - min_dte: 21
    - max_dte: 60
    - max_hold_days: 14
    - prediction_horizon: 10d
    - profit_target_pct: 40
    - stop_loss_pct: 25
    - sleeptime: 5M

All trading logic inherited from BaseOptionsStrategy.
This class exists to:
    1. Be explicitly named for clarity in logs and Lumibot's Trader registry
    2. Allow general-specific overrides in the future
    3. Ensure the correct feature set (general_features) is applied via self.preset
"""

import logging

from strategies.base_strategy import BaseOptionsStrategy

logger = logging.getLogger("options-bot.strategy.general")


class GeneralStrategy(BaseOptionsStrategy):
    """General trading strategy — 21+ DTE options, hold up to 14 days."""
    pass

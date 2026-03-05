"""
VIX regime-based confidence adjuster.
Phase C — ML Accuracy Improvements.

Scales the model's prediction confidence based on the current VIX regime.
High-VIX environments tend to have more noise and wider spreads, so we
reduce confidence. Low-VIX environments are calmer and more predictable.

Used in base_strategy.py AFTER the prediction step (Step 5) and BEFORE
the threshold check (Step 6).
"""

import logging
import sys
from pathlib import Path
# Add project root to sys.path — no setup.py/pyproject.toml in this project
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    VIX_REGIME_LOW_THRESHOLD,
    VIX_REGIME_HIGH_THRESHOLD,
    VIX_REGIME_LOW_MULTIPLIER,
    VIX_REGIME_NORMAL_MULTIPLIER,
    VIX_REGIME_HIGH_MULTIPLIER,
)

logger = logging.getLogger("options-bot.ml.regime_adjuster")

# VIX regime thresholds and multipliers imported from config.py
# (single source of truth — see config.py for documentation)
DEFAULT_VIX_LOW_THRESHOLD = VIX_REGIME_LOW_THRESHOLD
DEFAULT_VIX_HIGH_THRESHOLD = VIX_REGIME_HIGH_THRESHOLD
DEFAULT_LOW_VOL_MULTIPLIER = VIX_REGIME_LOW_MULTIPLIER
DEFAULT_NORMAL_VOL_MULTIPLIER = VIX_REGIME_NORMAL_MULTIPLIER
DEFAULT_HIGH_VOL_MULTIPLIER = VIX_REGIME_HIGH_MULTIPLIER


def adjust_prediction_confidence(
    predicted_return: float,
    vix_level: float,
    vix_low_threshold: float = DEFAULT_VIX_LOW_THRESHOLD,
    vix_high_threshold: float = DEFAULT_VIX_HIGH_THRESHOLD,
    low_vol_multiplier: float = DEFAULT_LOW_VOL_MULTIPLIER,
    normal_vol_multiplier: float = DEFAULT_NORMAL_VOL_MULTIPLIER,
    high_vol_multiplier: float = DEFAULT_HIGH_VOL_MULTIPLIER,
) -> tuple[float, str]:
    """
    Scale the predicted return based on the VIX regime.

    Args:
        predicted_return: Model's raw predicted forward return %
        vix_level: Current VIXY price (proxy for VIX level)
        vix_low_threshold: VIXY below this = low vol
        vix_high_threshold: VIXY above this = high vol
        low_vol_multiplier: Confidence multiplier for low vol
        normal_vol_multiplier: Confidence multiplier for normal vol
        high_vol_multiplier: Confidence multiplier for high vol

    Returns:
        (adjusted_return, regime_name)
    """
    if vix_level is None or vix_level <= 0:
        logger.debug("VIX level unavailable — no regime adjustment")
        return predicted_return, "unknown"

    if vix_level < vix_low_threshold:
        regime = "low_vol"
        multiplier = low_vol_multiplier
    elif vix_level > vix_high_threshold:
        regime = "high_vol"
        multiplier = high_vol_multiplier
    else:
        regime = "normal"
        multiplier = normal_vol_multiplier

    adjusted = predicted_return * multiplier

    logger.debug(
        f"Regime adjust: VIXY={vix_level:.2f} regime={regime} "
        f"multiplier={multiplier:.2f} raw={predicted_return:.3f}% "
        f"adjusted={adjusted:.3f}%"
    )

    return adjusted, regime

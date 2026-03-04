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

logger = logging.getLogger("options-bot.ml.regime_adjuster")

# VIX regime thresholds (using VIXY as proxy — post-reverse-split: VIXY ≈ VIX 1:1)
# These can be overridden via config.py
DEFAULT_VIX_LOW_THRESHOLD = 18.0    # VIXY below this = low vol regime
DEFAULT_VIX_HIGH_THRESHOLD = 28.0   # VIXY above this = high vol regime

# Confidence multipliers by regime
DEFAULT_LOW_VOL_MULTIPLIER = 1.1    # Slightly boost in low vol (calmer, more predictable)
DEFAULT_NORMAL_VOL_MULTIPLIER = 1.0 # No adjustment in normal vol
DEFAULT_HIGH_VOL_MULTIPLIER = 0.7   # Reduce in high vol (noisier, wider spreads)


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
    if vix_level <= 0 or vix_level is None:
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

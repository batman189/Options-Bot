"""
Swing-specific features — mean-reversion indicators.
Matches PROJECT_ARCHITECTURE.md Section 8b — Swing (+5).

Added to base features for swing profiles only.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger("options-bot.features.swing")

BARS_PER_DAY = 78


def compute_swing_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add swing-specific features to a DataFrame that already has base features.

    Swing Features (+5):
        1. dist_from_sma_20d: Distance from 20-day SMA as % of price
        2. bb_extreme: Bollinger Band position extremes (0-1 scale, 1 = at band)
        3. rsi_ob_os_duration: Bars since RSI was in oversold/overbought zone
        4. mean_rev_zscore: Z-score of price vs 20-day mean (mean-reversion signal)
        5. prior_bounce_magnitude: Size of the last price bounce from a local min/max
    """
    logger.info(f"Computing swing-specific features (BARS_PER_DAY={BARS_PER_DAY})")
    close = df["close"]

    # 1. Distance from 20-day SMA (more precise than sma_ratio_20)
    sma_20d = close.rolling(BARS_PER_DAY * 20).mean()
    df["swing_dist_sma_20d"] = (close - sma_20d) / sma_20d.replace(0, np.nan)

    # 2. Bollinger Band extreme — how close to upper or lower band
    # 0 = at middle, 1 = at upper band, -1 = at lower band
    if "bb_pctb" in df.columns:
        df["swing_bb_extreme"] = (df["bb_pctb"] - 0.5) * 2  # Scale from [-1, 1]
    else:
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        df["swing_bb_extreme"] = (close - bb_mid) / (bb_std.replace(0, np.nan))

    # 3. RSI oversold/overbought duration
    # Count bars since RSI was < 30 (oversold) or > 70 (overbought)
    if "rsi_14" in df.columns:
        rsi = df["rsi_14"]
    else:
        import ta
        rsi = ta.momentum.rsi(close, window=14)

    is_oversold = (rsi < 30).astype(int)
    is_overbought = (rsi > 70).astype(int)

    # Bars since last oversold
    os_groups = (~is_oversold.astype(bool)).cumsum()
    bars_since_os = is_oversold.groupby(os_groups).cumcount()
    # Bars since last overbought
    ob_groups = (~is_overbought.astype(bool)).cumsum()
    bars_since_ob = is_overbought.groupby(ob_groups).cumcount()
    # Combined: negative when coming from oversold, positive from overbought
    df["swing_rsi_ob_os_duration"] = bars_since_ob - bars_since_os

    # 4. Mean-reversion Z-score
    # How many std devs is current price from its 20-day mean
    mean_20d = close.rolling(BARS_PER_DAY * 20).mean()
    std_20d = close.rolling(BARS_PER_DAY * 20).std()
    df["swing_mean_rev_zscore"] = (close - mean_20d) / std_20d.replace(0, np.nan)

    # 5. Prior bounce magnitude
    # How much did price bounce from the most recent 5-day low/high
    low_5d = close.rolling(BARS_PER_DAY * 5).min()
    high_5d = close.rolling(BARS_PER_DAY * 5).max()
    bounce_from_low = (close - low_5d) / low_5d.replace(0, np.nan)
    bounce_from_high = (close - high_5d) / high_5d.replace(0, np.nan)
    # Use whichever is larger in magnitude — indicates direction of bounce
    df["swing_prior_bounce"] = np.where(
        bounce_from_low.abs() > bounce_from_high.abs(),
        bounce_from_low,
        bounce_from_high,
    )

    logger.info("Swing features computed: 5 features added")
    return df


def get_swing_feature_names() -> list[str]:
    """Return swing-specific feature column names."""
    return [
        "swing_dist_sma_20d",
        "swing_bb_extreme",
        "swing_rsi_ob_os_duration",
        "swing_mean_rev_zscore",
        "swing_prior_bounce",
    ]

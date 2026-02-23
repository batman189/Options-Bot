"""
General-specific features — trend and longer-horizon indicators.
Matches PROJECT_ARCHITECTURE.md Section 8b — General (+5).

Added to base features for general profiles only.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger("options-bot.features.general")

BARS_PER_DAY = 78


def compute_general_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add general-specific features to a DataFrame that already has base features.

    General Features (+5):
        1. trend_slope_50d: Slope of 50-day SMA (linear regression)
        2. sector_rel_strength: Placeholder — requires sector ETF data (NaN for Phase 1)
        3. momentum_long: Longer-term momentum (20d return / 50d return ratio)
        4. trend_consistency: Percentage of days in last 20d where close > open
        5. vol_regime: Volatility regime indicator (low/normal/high/crisis as 0-3)
    """
    logger.info("Computing general-specific features")
    close = df["close"]
    open_price = df["open"]

    # 1. Trend slope (50-day SMA)
    # Linear regression slope of the 50-day SMA over the last 50 bars
    sma_50d = close.rolling(BARS_PER_DAY * 50).mean()
    # Use rolling slope: change in SMA over last 10 days / 10
    sma_50d_shifted = sma_50d.shift(BARS_PER_DAY * 10)
    df["general_trend_slope_50d"] = (
        (sma_50d - sma_50d_shifted) / sma_50d_shifted.replace(0, np.nan)
    )

    # 2. Sector relative strength — placeholder for Phase 1
    # Would require SPY or sector ETF data alongside the symbol
    df["general_sector_rel_strength"] = np.nan

    # 3. Longer-term momentum
    # Ratio of 20d return to 50d return — shows if momentum is accelerating
    ret_20d = close.pct_change(BARS_PER_DAY * 20)
    ret_50d = close.pct_change(BARS_PER_DAY * 50)
    df["general_momentum_long"] = ret_20d / ret_50d.replace(0, np.nan)

    # 4. Trend consistency
    # What fraction of bars in the last 20 days had close > open (bullish bars)
    is_bullish = (close > open_price).astype(float)
    df["general_trend_consistency"] = is_bullish.rolling(BARS_PER_DAY * 20).mean()

    # 5. Volatility regime indicator
    # Based on rvol_20d percentile in its own history:
    # 0 = low vol (<25th pctl), 1 = normal (25-75), 2 = high (75-95), 3 = crisis (>95th)
    if "rvol_20d" in df.columns:
        rvol = df["rvol_20d"]
    else:
        log_ret = np.log(close / close.shift(1))
        rvol = log_ret.rolling(BARS_PER_DAY * 20).std() * np.sqrt(BARS_PER_DAY * 252)

    # Rolling percentile (over ~1 year of bars)
    lookback = BARS_PER_DAY * 252  # 1 year
    rvol_rank = rvol.rolling(lookback, min_periods=BARS_PER_DAY * 20).rank(pct=True)

    df["general_vol_regime"] = np.select(
        [
            rvol_rank < 0.25,
            rvol_rank < 0.75,
            rvol_rank < 0.95,
            rvol_rank >= 0.95,
        ],
        [0, 1, 2, 3],
        default=1,
    )

    logger.info("General features computed: 5 features added")
    return df


def get_general_feature_names() -> list[str]:
    """Return general-specific feature column names."""
    return [
        "general_trend_slope_50d",
        "general_sector_rel_strength",
        "general_momentum_long",
        "general_trend_consistency",
        "general_vol_regime",
    ]

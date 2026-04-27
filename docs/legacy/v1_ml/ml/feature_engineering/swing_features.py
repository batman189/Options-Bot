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
        3. rsi_ob_os_duration: Consecutive bars RSI is in oversold/overbought zone
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
    # Count consecutive bars currently IN the oversold/overbought zone.
    # When RSI < 30, bars_since_os increments each bar; resets to 0 when RSI exits.
    # When RSI > 70, bars_since_ob increments each bar; resets to 0 when RSI exits.
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

    # ═══════════════════════════════════════════════════════════════════
    # DAILY TREND FEATURES (+10) — captures multi-day momentum patterns
    # ═══════════════════════════════════════════════════════════════════

    # 6. Rate of change over 5 days
    df["swing_roc_5d"] = close.pct_change(BARS_PER_DAY * 5) * 100

    # 7. Rate of change over 10 days
    df["swing_roc_10d"] = close.pct_change(BARS_PER_DAY * 10) * 100

    # 8. SMA 10-day slope: is the short-term trend up or down?
    sma_10d = close.rolling(BARS_PER_DAY * 10).mean()
    sma_10d_prev = sma_10d.shift(BARS_PER_DAY)
    df["swing_sma_10d_slope"] = (sma_10d - sma_10d_prev) / sma_10d_prev.replace(0, np.nan) * 100

    # 9. Price vs SMA 10/50: above both = strong uptrend, below both = strong downtrend
    sma_50d = close.rolling(BARS_PER_DAY * 50).mean()
    above_10 = (close > sma_10d).astype(float)
    above_50 = (close > sma_50d).astype(float)
    df["swing_trend_alignment"] = above_10 + above_50 - 1  # [-1, 0, +1]

    # 10. Higher highs count (5-day): how many of last 5 daily highs are above prior day
    daily_high = df["high"].rolling(BARS_PER_DAY).max()
    df["swing_higher_highs_5d"] = sum(
        (daily_high.shift(BARS_PER_DAY * i) > daily_high.shift(BARS_PER_DAY * (i + 1))).astype(float)
        for i in range(5)
    )

    # 11. Daily range vs 20-day average range: expansion = breakout potential
    daily_range = df["high"].rolling(BARS_PER_DAY).max() - df["low"].rolling(BARS_PER_DAY).min()
    avg_daily_range = daily_range.rolling(BARS_PER_DAY * 20).mean().replace(0, np.nan)
    df["swing_range_expansion"] = daily_range / avg_daily_range

    # 12. Volume trend 5-day: is volume increasing or decreasing?
    vol = df["volume"].astype(float)
    vol_daily = vol.rolling(BARS_PER_DAY).sum()
    vol_daily_prev = vol_daily.shift(BARS_PER_DAY * 5)
    df["swing_volume_trend_5d"] = (vol_daily - vol_daily_prev) / vol_daily_prev.replace(0, np.nan)

    # 13. Up-volume ratio 5 days: fraction of volume on up-bars vs total
    is_up = (close > df["open"]).astype(float)
    up_vol_5d = (vol * is_up).rolling(BARS_PER_DAY * 5).sum()
    total_vol_5d = vol.rolling(BARS_PER_DAY * 5).sum().replace(0, np.nan)
    df["swing_up_volume_ratio"] = up_vol_5d / total_vol_5d

    # 14. Bollinger bandwidth: tight bands = potential breakout
    bb_upper = close.rolling(BARS_PER_DAY * 20).mean() + 2 * close.rolling(BARS_PER_DAY * 20).std()
    bb_lower = close.rolling(BARS_PER_DAY * 20).mean() - 2 * close.rolling(BARS_PER_DAY * 20).std()
    df["swing_bb_width"] = (bb_upper - bb_lower) / close.replace(0, np.nan) * 100

    # 15. Consecutive green/red days: momentum persistence
    daily_close = close.iloc[::BARS_PER_DAY] if len(close) > BARS_PER_DAY else close
    # Approximate: use rolling BARS_PER_DAY return direction
    day_return = close.pct_change(BARS_PER_DAY)
    is_green = (day_return > 0).astype(float)
    # Rolling count of recent green days (out of last 5)
    df["swing_green_day_count"] = is_green.rolling(BARS_PER_DAY * 5).sum() / 5

    logger.info("Swing features computed: 15 features added (5 original + 10 daily trend)")
    return df


def get_swing_feature_names() -> list[str]:
    """Return swing-specific feature column names."""
    return [
        # Original 5 mean-reversion features
        "swing_dist_sma_20d",
        "swing_bb_extreme",
        "swing_rsi_ob_os_duration",
        "swing_mean_rev_zscore",
        "swing_prior_bounce",
        # Daily trend features
        "swing_roc_5d",
        "swing_roc_10d",
        "swing_sma_10d_slope",
        "swing_trend_alignment",
        "swing_higher_highs_5d",
        "swing_range_expansion",
        "swing_volume_trend_5d",
        "swing_up_volume_ratio",
        "swing_bb_width",
        "swing_green_day_count",
    ]

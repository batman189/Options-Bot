"""
Scalp-specific features — intraday microstructure and momentum indicators.
Matches PROJECT_ARCHITECTURE.md Section 8b — Scalp (+10).

Added to base features for scalp profiles only.
These features are designed for 1-minute bar data on SPY 0DTE trading.

BARS_PER_DAY = 390 for 1-min bars (6.5 hours × 60 bars/hour).
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger("options-bot.features.scalp")

# 1-minute bars: 6.5 hours × 60 = 390 bars per trading day
SCALP_BARS_PER_DAY = 390


def compute_scalp_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add scalp-specific features to a DataFrame that already has base features.
    Input is expected to be 1-minute bar data with DatetimeIndex.

    Scalp Features (+10):
        1. scalp_momentum_1min: 1-bar return (instantaneous momentum)
        2. scalp_momentum_5min: 5-bar return (short-term trend)
        3. scalp_orb_distance: Distance from opening range (first 30 min high/low)
        4. scalp_vwap_slope: Slope of VWAP over last 15 minutes
        5. scalp_volume_surge: Current volume / rolling 30-bar avg volume
        6. scalp_spread_proxy: (high - low) / close as bid-ask spread proxy
        7. scalp_microstructure_imbalance: Buy vs sell pressure from bar direction
        8. scalp_time_bucket: Time-of-day encoded as 0-12 (30-min buckets)
        9. scalp_gamma_exposure_est: Estimated gamma exposure from price acceleration
        10. scalp_intraday_range_pos: Position within today's price range (0 = low, 1 = high)
    """
    logger.info(f"Computing scalp-specific features (SCALP_BARS_PER_DAY={SCALP_BARS_PER_DAY})")
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].astype(float)
    open_price = df["open"]

    # 1. 1-minute momentum (instantaneous)
    df["scalp_momentum_1min"] = close.pct_change(1)

    # 2. 5-minute momentum (short-term directional)
    df["scalp_momentum_5min"] = close.pct_change(5)

    # 3. Opening Range Breakout distance
    # Opening range = first 30 bars (30 min) of each trading day
    # Distance = how far current price is from the OR high/low, normalized
    if df.index.tz is not None:
        _dates = df.index.tz_convert("US/Eastern").date
    else:
        _dates = df.index.tz_localize("UTC").tz_convert("US/Eastern").date

    df["_trade_date"] = _dates
    or_high = df.groupby("_trade_date")["high"].transform(
        lambda x: x.iloc[:30].max() if len(x) >= 30 else x.max()
    )
    or_low = df.groupby("_trade_date")["low"].transform(
        lambda x: x.iloc[:30].min() if len(x) >= 30 else x.min()
    )
    or_range = (or_high - or_low).replace(0, np.nan)
    # Positive = above OR midpoint, negative = below
    or_mid = (or_high + or_low) / 2
    df["scalp_orb_distance"] = (close - or_mid) / or_range

    # 4. VWAP slope over last 15 bars
    # VWAP is computed cumulatively per day (base_features already has vwap_dev).
    # Here we compute the slope of price-vs-VWAP over 15 bars.
    typical = (high + low + close) / 3
    cum_tp_vol = (typical * volume).groupby(df["_trade_date"]).cumsum()
    cum_vol = volume.groupby(df["_trade_date"]).cumsum()
    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    vwap_ratio = close / vwap.replace(0, np.nan)
    # Slope: change in vwap_ratio over 15 bars
    df["scalp_vwap_slope"] = vwap_ratio - vwap_ratio.shift(15)

    # 5. Volume surge — current bar volume vs rolling 30-bar average
    vol_avg_30 = volume.rolling(30).mean()
    df["scalp_volume_surge"] = volume / vol_avg_30.replace(0, np.nan)

    # 6. Spread proxy — bar range as fraction of price
    # Tight bars = low spread/volatility; wide bars = high activity
    df["scalp_spread_proxy"] = (high - low) / close.replace(0, np.nan)

    # 7. Microstructure imbalance
    # Rolling ratio of bullish bars (close > open) over last 15 bars
    # > 0.5 = buying pressure, < 0.5 = selling pressure
    is_bullish = (close > open_price).astype(float)
    df["scalp_microstructure_imbalance"] = (
        is_bullish.rolling(15).mean() - 0.5
    ) * 2  # Scale to [-1, 1]

    # 8. Time-of-day bucket (0-12)
    # Market hours: 9:30-16:00 = 13 half-hour buckets
    # This captures intraday seasonality (e.g., first 30 min volatility,
    # lunch lull, power hour)
    if df.index.tz is not None:
        _hours = df.index.tz_convert("US/Eastern")
    else:
        _hours = df.index.tz_localize("UTC").tz_convert("US/Eastern")
    minutes_from_open = (_hours.hour * 60 + _hours.minute) - (9 * 60 + 30)
    # Clamp to market hours [0, 390]
    minutes_from_open = np.clip(minutes_from_open, 0, 390)
    df["scalp_time_bucket"] = (minutes_from_open // 30).astype(float)

    # 9. Gamma exposure estimate
    # Price acceleration as a proxy for dealer gamma hedging
    # Second derivative of price: (ret_t - ret_t-1)
    ret_1 = close.pct_change(1)
    df["scalp_gamma_exposure_est"] = ret_1 - ret_1.shift(1)

    # 10. Intraday range position
    # Where is current price within today's observed range? (0=day low, 1=day high)
    day_high = df.groupby("_trade_date")["high"].transform("cummax")
    day_low = df.groupby("_trade_date")["low"].transform(
        lambda x: x.expanding().min()
    )
    day_range = (day_high - day_low).replace(0, np.nan)
    df["scalp_intraday_range_pos"] = (close - day_low) / day_range

    # Cleanup helper column
    df.drop(columns=["_trade_date"], inplace=True, errors="ignore")

    logger.info("Scalp features computed: 10 features added")
    return df


def get_scalp_feature_names() -> list[str]:
    """Return scalp-specific feature column names."""
    return [
        "scalp_momentum_1min",
        "scalp_momentum_5min",
        "scalp_orb_distance",
        "scalp_vwap_slope",
        "scalp_volume_surge",
        "scalp_spread_proxy",
        "scalp_microstructure_imbalance",
        "scalp_time_bucket",
        "scalp_gamma_exposure_est",
        "scalp_intraday_range_pos",
    ]

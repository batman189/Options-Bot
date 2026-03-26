"""
Momentum-specific features — detect strong directional moves in progress.

These features answer the question: "Is a significant move happening RIGHT NOW,
and is it likely to continue?" This is fundamentally different from the scalp
features which predict direction. Momentum features detect moves already underway.

Designed for 1-minute bar data. Used by the Momentum Scalp strategy type.

Feature groups:
  1. Price velocity (rate of change over multiple windows)
  2. Volume surge (institutional activity detection)
  3. VWAP structure (trend confirmation)
  4. Acceleration (is the move speeding up or slowing down?)
  5. Microstructure (order flow, candle structure)
  6. Context (time of day, daily range usage)
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger("options-bot.features.momentum")

BARS_PER_DAY = 390  # 1-min bars


def compute_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add momentum detection features to a DataFrame that already has base features.
    Input: 1-minute bar data with DatetimeIndex.

    Returns the same DataFrame with ~25 momentum features added.
    """
    logger.info("Computing momentum features")
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].astype(float)
    open_price = df["open"]

    # ── Trade date helper ─────────────────────────────────────────────
    if df.index.tz is not None:
        _et = df.index.tz_convert("US/Eastern")
    else:
        _et = df.index.tz_localize("UTC").tz_convert("US/Eastern")
    df["_trade_date"] = _et.date

    # ═══════════════════════════════════════════════════════════════════
    # GROUP 1: Price Velocity — how fast is price moving?
    # ═══════════════════════════════════════════════════════════════════

    # 1. 3-minute velocity (very short-term — first sign of a move)
    df["mom_velocity_3m"] = close.pct_change(3) * 100  # in percent

    # 2. 5-minute velocity (confirms the 3-min signal is real)
    df["mom_velocity_5m"] = close.pct_change(5) * 100

    # 3. 10-minute velocity (medium-term — established move)
    df["mom_velocity_10m"] = close.pct_change(10) * 100

    # 4. 15-minute velocity (the move is well underway)
    df["mom_velocity_15m"] = close.pct_change(15) * 100

    # 5. 30-minute velocity (captures the full move window)
    df["mom_velocity_30m"] = close.pct_change(30) * 100

    # ═══════════════════════════════════════════════════════════════════
    # GROUP 2: Acceleration — is the move speeding up or slowing down?
    # ═══════════════════════════════════════════════════════════════════

    # 6. 5-min acceleration: velocity change (1st derivative of velocity)
    vel_5 = df["mom_velocity_5m"]
    df["mom_acceleration_5m"] = vel_5 - vel_5.shift(5)

    # 7. Short-term acceleration: last 3 bars vs prior 3 bars
    vel_3 = df["mom_velocity_3m"]
    df["mom_acceleration_3m"] = vel_3 - vel_3.shift(3)

    # 8. Acceleration of acceleration (2nd derivative — jerk)
    # Positive jerk in a down move = move is accelerating downward
    acc_5 = df["mom_acceleration_5m"]
    df["mom_jerk"] = acc_5 - acc_5.shift(3)

    # ═══════════════════════════════════════════════════════════════════
    # GROUP 3: Volume Surge — is smart money moving?
    # ═══════════════════════════════════════════════════════════════════

    # 9. Volume surge ratio: current 1-min volume vs 20-bar rolling average
    vol_avg_20 = volume.rolling(20).mean().replace(0, np.nan)
    df["mom_volume_surge_1m"] = volume / vol_avg_20

    # 10. Volume surge 5-min: sum of last 5 bars vs average 5-bar volume
    vol_5 = volume.rolling(5).sum()
    vol_avg_5bar = volume.rolling(100).mean().replace(0, np.nan) * 5
    df["mom_volume_surge_5m"] = vol_5 / vol_avg_5bar

    # 11. Volume trend: is volume increasing over the last 10 bars?
    # Slope of log(volume) over 10 bars
    log_vol = np.log1p(volume)
    df["mom_volume_trend"] = log_vol.rolling(10).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 10 else 0,
        raw=False
    )

    # 12. Cumulative volume delta (net buy - sell, normalized)
    bar_range = (high - low).replace(0, np.nan)
    buy_frac = (close - low) / bar_range
    buy_frac = buy_frac.fillna(0.5)
    net_flow = volume * (2 * buy_frac - 1)  # [-vol, +vol]
    cum_net = net_flow.groupby(df["_trade_date"]).cumsum()
    cum_vol = volume.groupby(df["_trade_date"]).cumsum().replace(0, np.nan)
    df["mom_cum_volume_delta"] = cum_net / cum_vol

    # 13. Directional volume ratio: volume on up bars vs down bars (10 bar window)
    up_vol = (volume * (close > open_price).astype(float)).rolling(10).sum()
    down_vol = (volume * (close <= open_price).astype(float)).rolling(10).sum()
    total_dir = (up_vol + down_vol).replace(0, np.nan)
    df["mom_directional_volume"] = (up_vol - down_vol) / total_dir  # [-1, +1]

    # ═══════════════════════════════════════════════════════════════════
    # GROUP 4: VWAP Structure — trend confirmation
    # ═══════════════════════════════════════════════════════════════════

    # 14. VWAP deviation percent
    typical = (high + low + close) / 3
    cum_tp_vol = (typical * volume).groupby(df["_trade_date"]).cumsum()
    cum_vol_day = volume.groupby(df["_trade_date"]).cumsum().replace(0, np.nan)
    vwap = cum_tp_vol / cum_vol_day
    df["mom_vwap_dev_pct"] = ((close - vwap) / vwap.replace(0, np.nan)) * 100

    # 15. VWAP deviation velocity: how fast is price moving away from VWAP?
    vwap_dev = df["mom_vwap_dev_pct"]
    df["mom_vwap_velocity"] = vwap_dev - vwap_dev.shift(5)

    # 16. Price vs VWAP direction consistency (5 bars)
    # How many of the last 5 bars were on the same side of VWAP?
    above_vwap = (close > vwap).astype(float)
    df["mom_vwap_consistency"] = above_vwap.rolling(5).mean()  # 1.0 = all above, 0.0 = all below

    # ═══════════════════════════════════════════════════════════════════
    # GROUP 5: Price Structure — breakouts and levels
    # ═══════════════════════════════════════════════════════════════════

    # 17. Distance from 30-min rolling high (normalized by ATR)
    rolling_high_30 = high.rolling(30).max()
    rolling_low_30 = low.rolling(30).min()
    atr_15 = (high - low).rolling(15).mean().replace(0, np.nan)
    df["mom_dist_from_30m_high"] = (close - rolling_high_30) / atr_15

    # 18. Distance from 30-min rolling low (normalized by ATR)
    df["mom_dist_from_30m_low"] = (close - rolling_low_30) / atr_15

    # 19. New 30-min high flag: did we just make a new 30-bar high?
    df["mom_new_30m_high"] = (close >= rolling_high_30).astype(float)

    # 20. New 30-min low flag
    df["mom_new_30m_low"] = (close <= rolling_low_30).astype(float)

    # 21. Candle body ratio: how decisive are the recent candles?
    # Strong moves have big bodies (close far from open). Indecision has small bodies.
    body = (close - open_price).abs()
    total_range = (high - low).replace(0, np.nan)
    df["mom_candle_body_ratio"] = (body / total_range).rolling(5).mean()

    # 22. Consecutive directional bars: how many bars in a row are moving same direction?
    direction = np.sign(close - open_price)
    df["mom_consecutive_bars"] = direction.groupby(
        (direction != direction.shift()).cumsum()
    ).cumcount() + 1
    # Cap at 15 to prevent extreme values
    df["mom_consecutive_bars"] = df["mom_consecutive_bars"].clip(upper=15).astype(float)

    # ═══════════════════════════════════════════════════════════════════
    # GROUP 6: Context — time and daily range
    # ═══════════════════════════════════════════════════════════════════

    # 23. Time of day (minutes since market open, normalized to 0-1)
    minutes_from_open = (_et.hour * 60 + _et.minute) - (9 * 60 + 30)
    minutes_from_open = np.clip(minutes_from_open, 0, 390)
    df["mom_time_normalized"] = minutes_from_open / 390.0

    # 24. Daily range used: how much of the avg daily range has been used today?
    day_high = df.groupby("_trade_date")["high"].transform("cummax")
    day_low = df.groupby("_trade_date")["low"].transform(
        lambda x: x.expanding().min()
    )
    today_range = day_high - day_low
    avg_daily_range = (high - low).rolling(BARS_PER_DAY).sum().rolling(5).mean()
    avg_daily_range = avg_daily_range.replace(0, np.nan)
    df["mom_range_used_pct"] = today_range / (avg_daily_range / BARS_PER_DAY * 10)
    # Rough normalization — values > 1.0 mean today is wider than average

    # 25. Intraday range position (0 = at day low, 1 = at day high)
    day_range = (day_high - day_low).replace(0, np.nan)
    df["mom_intraday_position"] = (close - day_low) / day_range

    # ── Cleanup ───────────────────────────────────────────────────────
    df.drop(columns=["_trade_date"], inplace=True, errors="ignore")

    logger.info("Momentum features computed: 25 features added")
    return df


def get_momentum_feature_names() -> list[str]:
    """Return momentum-specific feature column names."""
    return [
        # Velocity
        "mom_velocity_3m",
        "mom_velocity_5m",
        "mom_velocity_10m",
        "mom_velocity_15m",
        "mom_velocity_30m",
        # Acceleration
        "mom_acceleration_5m",
        "mom_acceleration_3m",
        "mom_jerk",
        # Volume
        "mom_volume_surge_1m",
        "mom_volume_surge_5m",
        "mom_volume_trend",
        "mom_cum_volume_delta",
        "mom_directional_volume",
        # VWAP
        "mom_vwap_dev_pct",
        "mom_vwap_velocity",
        "mom_vwap_consistency",
        # Price structure
        "mom_dist_from_30m_high",
        "mom_dist_from_30m_low",
        "mom_new_30m_high",
        "mom_new_30m_low",
        "mom_candle_body_ratio",
        "mom_consecutive_bars",
        # Context
        "mom_time_normalized",
        "mom_range_used_pct",
        "mom_intraday_position",
    ]

"""
Base feature engineering — shared features across all profile types.
Matches PROJECT_ARCHITECTURE.md Section 8a.

Computes ~45 features from:
  - Stock OHLCV bars (5-minute, from Alpaca)
  - Options Greeks/IV data (daily, from Theta Data)

Stock features are computed at bar resolution (5-min).
Options features are computed at daily resolution and forward-filled.

Usage:
    from ml.feature_engineering.base_features import compute_base_features
    df = compute_base_features(bars_df, options_daily_df)
"""

import logging
import numpy as np
import pandas as pd
import ta

logger = logging.getLogger("options-bot.features.base")

def _infer_bars_per_day(df: pd.DataFrame) -> int:
    """
    Auto-detect whether bars are intraday or daily.
    Returns number of bars per trading day:
      - 78 for 5-min bars
      - 390 for 1-min bars
      - 1 for daily bars
    """
    if len(df) < 3:
        return 1

    # Check median time delta between consecutive bars
    deltas = df.index.to_series().diff().dropna()
    if len(deltas) == 0:
        return 1

    median_delta = deltas.median()
    minutes = median_delta.total_seconds() / 60

    if minutes < 2:       # ~1 min bars
        return 390
    elif minutes < 10:    # ~5 min bars
        return 78
    elif minutes < 20:    # ~15 min bars
        return 26
    elif minutes < 70:    # ~1 hour bars
        return 7
    else:                 # daily or longer
        return 1


def compute_stock_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all stock-based features from OHLCV bars.
    Input DataFrame must have columns: [open, high, low, close, volume]
    with a DatetimeIndex.

    Returns the same DataFrame with feature columns added.
    NaN rows at the start (due to lookback) are expected and handled
    by the caller (dropped before training).

    Features computed (~25):
        Price Returns (8): ret_5min, ret_15min, ret_1hr, ret_4hr, ret_1d, ret_5d, ret_10d, ret_20d
        Moving Averages (8): sma_ratio_10..200, ema_ratio_9..50
        Volatility (6): rvol_1hr..20d
        Oscillators (6): rsi_14, rsi_7, macd_line, macd_signal, macd_hist, adx_14
        Bands (5): bb_upper_ratio, bb_lower_ratio, bb_bandwidth, bb_pctb, atr_14_pct
        Volume (3): vol_ratio_20, obv_slope, vwap_dev
        Price Position (2): dist_20d_high, dist_20d_low
        Time (3): day_of_week, hour_of_day, minutes_to_close
    """
    BARS_PER_DAY = _infer_bars_per_day(df)
    logger.info(f"Computing stock features for {len(df)} bars (BARS_PER_DAY={BARS_PER_DAY})")
    if BARS_PER_DAY == 1 and len(df) < 200:
        logger.warning(f"Only {len(df)} daily bars — need 200+ for all features")
    elif BARS_PER_DAY > 1 and len(df) < 200:
        logger.warning(f"Only {len(df)} bars — need 200+ for all features")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].astype(float)

    # =========================================================================
    # Price Returns (8)
    # Lookback windows scale with bar frequency.
    # For daily bars (BPD=1): ret_5min=1bar, ret_15min=1bar, ret_1hr=1bar,
    #   ret_4hr=1bar, ret_1d=1bar, ret_5d=5bars, etc.
    # For 5-min bars (BPD=78): ret_5min=1bar, ret_15min=3bars, ret_1hr=12bars, etc.
    # =========================================================================
    if BARS_PER_DAY == 1:
        # Daily bars: sub-daily returns all map to 1-bar return
        df["ret_5min"] = close.pct_change(1)
        df["ret_15min"] = close.pct_change(1)
        df["ret_1hr"] = close.pct_change(1)
        df["ret_4hr"] = close.pct_change(1)
        df["ret_1d"] = close.pct_change(1)
    else:
        df["ret_5min"] = close.pct_change(1)
        df["ret_15min"] = close.pct_change(3)
        df["ret_1hr"] = close.pct_change(12)
        df["ret_4hr"] = close.pct_change(48)
        df["ret_1d"] = close.pct_change(BARS_PER_DAY)
    df["ret_5d"] = close.pct_change(max(BARS_PER_DAY * 5, 5))
    df["ret_10d"] = close.pct_change(max(BARS_PER_DAY * 10, 10))
    df["ret_20d"] = close.pct_change(max(BARS_PER_DAY * 20, 20))

    # =========================================================================
    # Moving Average Ratios (8)
    # Price / MA — values > 1 mean price above MA
    # =========================================================================
    df["sma_ratio_10"] = close / close.rolling(10).mean()
    df["sma_ratio_20"] = close / close.rolling(20).mean()
    df["sma_ratio_50"] = close / close.rolling(50).mean()
    df["sma_ratio_100"] = close / close.rolling(100).mean()
    df["sma_ratio_200"] = close / close.rolling(200).mean()

    df["ema_ratio_9"] = close / close.ewm(span=9, adjust=False).mean()
    df["ema_ratio_21"] = close / close.ewm(span=21, adjust=False).mean()
    df["ema_ratio_50"] = close / close.ewm(span=50, adjust=False).mean()

    # =========================================================================
    # Realized Volatility (6)
    # Annualized std of log returns over various windows
    # Annualization: sqrt(BARS_PER_DAY * 252) for intraday, sqrt(252) for daily
    # =========================================================================
    log_ret = np.log(close / close.shift(1))
    annualize = np.sqrt(BARS_PER_DAY * 252)

    if BARS_PER_DAY == 1:
        # Daily bars: sub-daily vols use small lookbacks
        df["rvol_1hr"] = log_ret.rolling(5).std() * annualize
        df["rvol_4hr"] = log_ret.rolling(5).std() * annualize
        df["rvol_1d"] = log_ret.rolling(5).std() * annualize
    else:
        df["rvol_1hr"] = log_ret.rolling(12).std() * annualize
        df["rvol_4hr"] = log_ret.rolling(48).std() * annualize
        df["rvol_1d"] = log_ret.rolling(BARS_PER_DAY).std() * annualize
    df["rvol_5d"] = log_ret.rolling(max(BARS_PER_DAY * 5, 5)).std() * annualize
    df["rvol_10d"] = log_ret.rolling(max(BARS_PER_DAY * 10, 10)).std() * annualize
    df["rvol_20d"] = log_ret.rolling(max(BARS_PER_DAY * 20, 20)).std() * annualize

    # =========================================================================
    # Oscillators (6)
    # Using ta library for standard implementations
    # =========================================================================
    df["rsi_14"] = ta.momentum.rsi(close, window=14)
    df["rsi_7"] = ta.momentum.rsi(close, window=7)

    macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    df["macd_line"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    adx = ta.trend.ADXIndicator(high, low, close, window=14)
    df["adx_14"] = adx.adx()

    # =========================================================================
    # Bollinger Bands + ATR (5)
    # =========================================================================
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    bb_mid = bb.bollinger_mavg()

    df["bb_upper_ratio"] = close / bb_upper
    df["bb_lower_ratio"] = close / bb_lower
    df["bb_bandwidth"] = (bb_upper - bb_lower) / bb_mid
    df["bb_pctb"] = bb.bollinger_pband()

    atr = ta.volatility.AverageTrueRange(high, low, close, window=14)
    df["atr_14_pct"] = atr.average_true_range() / close

    # =========================================================================
    # Volume Features (3)
    # =========================================================================
    vol_sma_20 = volume.rolling(20).mean()
    df["vol_ratio_20"] = volume / vol_sma_20.replace(0, np.nan)

    obv = ta.volume.OnBalanceVolumeIndicator(close, volume)
    obv_values = obv.on_balance_volume()
    obv_lookback = 12 if BARS_PER_DAY > 1 else 5
    df["obv_slope"] = (obv_values - obv_values.shift(obv_lookback)) / (obv_values.shift(obv_lookback).replace(0, np.nan))

    # VWAP deviation — cumulative within each day (for intraday) or rolling for daily
    if BARS_PER_DAY > 1:
        df["_typical_price"] = (high + low + close) / 3
        df["_cum_tp_vol"] = (df["_typical_price"] * volume).groupby(df.index.date).cumsum()
        df["_cum_vol"] = volume.groupby(df.index.date).cumsum()
        vwap = df["_cum_tp_vol"] / df["_cum_vol"].replace(0, np.nan)
        df["vwap_dev"] = (close - vwap) / vwap
        df.drop(columns=["_typical_price", "_cum_tp_vol", "_cum_vol"], inplace=True)
    else:
        # For daily bars, use rolling VWAP-like measure (volume-weighted avg price over 5 days)
        typical_price = (high + low + close) / 3
        rolling_vwap = (typical_price * volume).rolling(5).sum() / volume.rolling(5).sum().replace(0, np.nan)
        df["vwap_dev"] = (close - rolling_vwap) / rolling_vwap

    # =========================================================================
    # Price Position (2)
    # Distance from 20-day high/low as percentage
    # =========================================================================
    rolling_high = high.rolling(max(BARS_PER_DAY * 20, 20)).max()
    rolling_low = low.rolling(max(BARS_PER_DAY * 20, 20)).min()
    df["dist_20d_high"] = (close - rolling_high) / rolling_high
    df["dist_20d_low"] = (close - rolling_low) / rolling_low

    # =========================================================================
    # Time Features (3)
    # =========================================================================
    try:
        if df.index.tz is not None:
            eastern = df.index.tz_convert("US/Eastern")
        else:
            eastern = df.index.tz_localize("UTC").tz_convert("US/Eastern")
    except Exception:
        # Fallback if timezone conversion fails (e.g., tz-naive daily bars)
        eastern = df.index

    df["day_of_week"] = eastern.dayofweek  # 0=Mon, 4=Fri
    if BARS_PER_DAY > 1:
        df["hour_of_day"] = eastern.hour + eastern.minute / 60.0
        df["minutes_to_close"] = (16 * 60) - (eastern.hour * 60 + eastern.minute)
        df["minutes_to_close"] = df["minutes_to_close"].clip(lower=0)
    else:
        # Daily bars: fixed values (market close)
        df["hour_of_day"] = 16.0
        df["minutes_to_close"] = 0.0

    logger.info(f"Stock features computed: {sum(1 for c in df.columns if c not in ['open','high','low','close','volume'])} features added")
    return df


def compute_options_features(
    bars_df: pd.DataFrame,
    options_daily_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute options-based features and merge with bar data.

    Args:
        bars_df: DataFrame with stock features already computed (DatetimeIndex).
        options_daily_df: DataFrame with daily options data. Must have columns:
            - date: date of the observation
            - atm_call_delta, atm_call_gamma, atm_call_theta, atm_call_vega
            - atm_put_delta, atm_put_gamma, atm_put_theta, atm_put_vega
            - atm_iv (ATM implied volatility)
            - iv_skew (OTM put IV - OTM call IV)
            - put_call_vol_ratio
            - put_call_oi_ratio
            - atm_call_bid_ask_pct, atm_put_bid_ask_pct
            Any missing columns will result in NaN features.

    Returns:
        bars_df with options feature columns added.
        Options features are forward-filled to align with 5-min bars.

    Options Features (~20):
        atm_iv, iv_skew, iv_rank_20d, rv_iv_spread,
        put_call_vol_ratio, put_call_oi_ratio,
        atm_call_delta, atm_call_theta, atm_call_gamma, atm_call_vega,
        atm_put_delta, atm_put_theta, atm_put_gamma, atm_put_vega,
        theta_delta_ratio, gamma_theta_ratio, vega_theta_ratio,
        atm_call_spread_pct, atm_put_spread_pct
    """
    logger.info(f"Computing options features from {len(options_daily_df)} daily rows")

    if options_daily_df.empty:
        logger.warning("No options data provided — options features will be NaN")
        opt_cols = [
            "atm_iv", "iv_skew", "iv_rank_20d", "rv_iv_spread",
            "put_call_vol_ratio", "put_call_oi_ratio",
            "atm_call_delta", "atm_call_theta", "atm_call_gamma", "atm_call_vega",
            "atm_put_delta", "atm_put_theta", "atm_put_gamma", "atm_put_vega",
            "theta_delta_ratio", "gamma_theta_ratio", "vega_theta_ratio",
            "atm_call_spread_pct", "atm_put_spread_pct",
        ]
        for col in opt_cols:
            bars_df[col] = np.nan
        return bars_df

    opt = options_daily_df.copy()

    # Ensure date column is date type
    if "date" in opt.columns:
        opt["date"] = pd.to_datetime(opt["date"]).dt.date
    elif opt.index.name == "date":
        opt = opt.reset_index()
        opt["date"] = pd.to_datetime(opt["date"]).dt.date

    # --- Derived features computed from daily data ---

    # IV Rank (20-day): where current IV sits vs last 20 days
    if "atm_iv" in opt.columns:
        iv_20d_min = opt["atm_iv"].rolling(20, min_periods=5).min()
        iv_20d_max = opt["atm_iv"].rolling(20, min_periods=5).max()
        iv_range = iv_20d_max - iv_20d_min
        opt["iv_rank_20d"] = ((opt["atm_iv"] - iv_20d_min) / iv_range.replace(0, np.nan))
    else:
        opt["iv_rank_20d"] = np.nan

    # RV-IV Spread: realized vol - implied vol (from bars data)
    # We'll compute this after merging by using rvol_1d from stock features
    opt["rv_iv_spread"] = np.nan  # Placeholder — computed after merge

    # Theta/Delta ratio (call side, absolute values)
    if "atm_call_theta" in opt.columns and "atm_call_delta" in opt.columns:
        opt["theta_delta_ratio"] = (
            opt["atm_call_theta"].abs() /
            opt["atm_call_delta"].abs().replace(0, np.nan)
        )
    else:
        opt["theta_delta_ratio"] = np.nan

    # Gamma/Theta ratio
    if "atm_call_gamma" in opt.columns and "atm_call_theta" in opt.columns:
        opt["gamma_theta_ratio"] = (
            opt["atm_call_gamma"].abs() /
            opt["atm_call_theta"].abs().replace(0, np.nan)
        )
    else:
        opt["gamma_theta_ratio"] = np.nan

    # Vega/Theta ratio
    if "atm_call_vega" in opt.columns and "atm_call_theta" in opt.columns:
        opt["vega_theta_ratio"] = (
            opt["atm_call_vega"].abs() /
            opt["atm_call_theta"].abs().replace(0, np.nan)
        )
    else:
        opt["vega_theta_ratio"] = np.nan

    # --- Merge daily options data with 5-min bars ---
    # Create a date column in bars for merging
    if bars_df.index.tz is not None:
        bars_dates = bars_df.index.tz_convert("US/Eastern").date
    else:
        bars_dates = bars_df.index.tz_localize("UTC").tz_convert("US/Eastern").date

    bars_df["_merge_date"] = bars_dates

    # Select columns to merge
    merge_cols = [
        "date",
        "atm_iv", "iv_skew", "iv_rank_20d",
        "put_call_vol_ratio", "put_call_oi_ratio",
        "atm_call_delta", "atm_call_theta", "atm_call_gamma", "atm_call_vega",
        "atm_put_delta", "atm_put_theta", "atm_put_gamma", "atm_put_vega",
        "theta_delta_ratio", "gamma_theta_ratio", "vega_theta_ratio",
        "atm_call_spread_pct", "atm_put_spread_pct",
        "rv_iv_spread",
    ]
    # Only include columns that exist
    available_merge_cols = ["date"] + [c for c in merge_cols[1:] if c in opt.columns]
    opt_merge = opt[available_merge_cols].copy()

    bars_df = bars_df.merge(
        opt_merge,
        left_on="_merge_date",
        right_on="date",
        how="left",
    )
    bars_df.drop(columns=["_merge_date", "date"], inplace=True, errors="ignore")

    # Forward-fill any remaining gaps in options features
    opt_feature_cols = [c for c in available_merge_cols if c != "date"]
    for col in opt_feature_cols:
        if col in bars_df.columns:
            bars_df[col] = bars_df[col].ffill()

    # Compute RV-IV spread now that we have rvol_1d from stock features
    if "rvol_1d" in bars_df.columns and "atm_iv" in bars_df.columns:
        bars_df["rv_iv_spread"] = bars_df["rvol_1d"] - bars_df["atm_iv"]

    # Ensure all expected options columns exist (fill with NaN if missing)
    expected_opt_cols = [
        "atm_iv", "iv_skew", "iv_rank_20d", "rv_iv_spread",
        "put_call_vol_ratio", "put_call_oi_ratio",
        "atm_call_delta", "atm_call_theta", "atm_call_gamma", "atm_call_vega",
        "atm_put_delta", "atm_put_theta", "atm_put_gamma", "atm_put_vega",
        "theta_delta_ratio", "gamma_theta_ratio", "vega_theta_ratio",
        "atm_call_spread_pct", "atm_put_spread_pct",
    ]
    for col in expected_opt_cols:
        if col not in bars_df.columns:
            bars_df[col] = np.nan

    logger.info(f"Options features merged. Total columns: {len(bars_df.columns)}")
    return bars_df


def compute_base_features(
    bars_df: pd.DataFrame,
    options_daily_df: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Compute all base features (stock + options).

    Args:
        bars_df: OHLCV DataFrame with DatetimeIndex. Columns: [open, high, low, close, volume]
        options_daily_df: Daily options data (optional). See compute_options_features for schema.

    Returns:
        DataFrame with all base features added. Rows with NaN (from lookback) are preserved —
        the caller decides how to handle them (usually drop before training).
    """
    logger.info(f"Computing base features: {len(bars_df)} bars")

    # Validate input
    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(bars_df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Step 1: Stock features
    df = compute_stock_features(bars_df.copy())

    # Step 2: Options features
    if options_daily_df is not None and not options_daily_df.empty:
        df = compute_options_features(df, options_daily_df)
    else:
        logger.info("No options data — skipping options features (will be NaN)")
        opt_cols = [
            "atm_iv", "iv_skew", "iv_rank_20d", "rv_iv_spread",
            "put_call_vol_ratio", "put_call_oi_ratio",
            "atm_call_delta", "atm_call_theta", "atm_call_gamma", "atm_call_vega",
            "atm_put_delta", "atm_put_theta", "atm_put_gamma", "atm_put_vega",
            "theta_delta_ratio", "gamma_theta_ratio", "vega_theta_ratio",
            "atm_call_spread_pct", "atm_put_spread_pct",
        ]
        for col in opt_cols:
            df[col] = np.nan

    feature_cols = [c for c in df.columns if c not in ["open", "high", "low", "close", "volume"]]
    logger.info(f"Base features complete: {len(feature_cols)} features total")
    return df


def get_base_feature_names() -> list[str]:
    """Return the list of all base feature column names in order."""
    return [
        # Price Returns (8)
        "ret_5min", "ret_15min", "ret_1hr", "ret_4hr",
        "ret_1d", "ret_5d", "ret_10d", "ret_20d",
        # Moving Averages (8)
        "sma_ratio_10", "sma_ratio_20", "sma_ratio_50",
        "sma_ratio_100", "sma_ratio_200",
        "ema_ratio_9", "ema_ratio_21", "ema_ratio_50",
        # Volatility (6)
        "rvol_1hr", "rvol_4hr", "rvol_1d", "rvol_5d", "rvol_10d", "rvol_20d",
        # Oscillators (6)
        "rsi_14", "rsi_7", "macd_line", "macd_signal", "macd_hist", "adx_14",
        # Bands (5)
        "bb_upper_ratio", "bb_lower_ratio", "bb_bandwidth", "bb_pctb", "atr_14_pct",
        # Volume (3)
        "vol_ratio_20", "obv_slope", "vwap_dev",
        # Price Position (2)
        "dist_20d_high", "dist_20d_low",
        # Time (3)
        "day_of_week", "hour_of_day", "minutes_to_close",
        # Options (19)
        "atm_iv", "iv_skew", "iv_rank_20d", "rv_iv_spread",
        "put_call_vol_ratio", "put_call_oi_ratio",
        "atm_call_delta", "atm_call_theta", "atm_call_gamma", "atm_call_vega",
        "atm_put_delta", "atm_put_theta", "atm_put_gamma", "atm_put_vega",
        "theta_delta_ratio", "gamma_theta_ratio", "vega_theta_ratio",
        "atm_call_spread_pct", "atm_put_spread_pct",
    ]

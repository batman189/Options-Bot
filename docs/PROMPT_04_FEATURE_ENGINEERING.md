# CLAUDE CODE PROMPT 04 — Feature Engineering

## TASK
Create the feature engineering module that computes all features from raw data (stock bars + options data) for ML training. This is Phase 1, Step 7 from the architecture.

**Design**:
- Stock features (~25) computed from 5-minute OHLCV bars using the `ta` library + pandas
- Options features (~20) computed from daily Theta Data Greeks, forward-filled to match bar resolution
- Style-specific features (+5 each for swing and general)
- All features output as a single DataFrame ready for ML training
- Features computed per-bar — each row is one 5-minute bar with all features attached

**Bar lookback requirements** (5-min bars):
- 1hr = 12 bars, 4hr = 48 bars, 1d = 78 bars (6.5hr trading day)
- 5d = 390 bars, 10d = 780 bars, 20d = 1560 bars
- SMA-200 needs 200 bars minimum
- To compute all features, provide at least 1600 bars of history before the target window

**CRITICAL**: Read this ENTIRE prompt before writing any code. Build exactly what is specified.

---

## FILES TO CREATE

1. `options-bot/ml/__init__.py` — empty
2. `options-bot/ml/feature_engineering/__init__.py` — empty
3. `options-bot/ml/feature_engineering/base_features.py` — shared stock + options features
4. `options-bot/ml/feature_engineering/swing_features.py` — swing-specific features
5. `options-bot/ml/feature_engineering/general_features.py` — general-specific features

---

## FILE 1: `options-bot/ml/__init__.py`

```python
```

---

## FILE 2: `options-bot/ml/feature_engineering/__init__.py`

```python
```

---

## FILE 3: `options-bot/ml/feature_engineering/base_features.py`

```python
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

# 5-min bars per trading day (6.5 hours * 12 bars/hour)
BARS_PER_DAY = 78


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
    logger.info(f"Computing stock features for {len(df)} bars")
    if len(df) < 200:
        logger.warning(f"Only {len(df)} bars — need 200+ for all features")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].astype(float)

    # =========================================================================
    # Price Returns (8)
    # Percentage change over various lookback periods
    # =========================================================================
    df["ret_5min"] = close.pct_change(1)
    df["ret_15min"] = close.pct_change(3)
    df["ret_1hr"] = close.pct_change(12)
    df["ret_4hr"] = close.pct_change(48)
    df["ret_1d"] = close.pct_change(BARS_PER_DAY)
    df["ret_5d"] = close.pct_change(BARS_PER_DAY * 5)
    df["ret_10d"] = close.pct_change(BARS_PER_DAY * 10)
    df["ret_20d"] = close.pct_change(BARS_PER_DAY * 20)

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
    # Annualization: sqrt(BARS_PER_DAY * 252) for 5-min bars
    # =========================================================================
    log_ret = np.log(close / close.shift(1))
    annualize = np.sqrt(BARS_PER_DAY * 252)

    df["rvol_1hr"] = log_ret.rolling(12).std() * annualize
    df["rvol_4hr"] = log_ret.rolling(48).std() * annualize
    df["rvol_1d"] = log_ret.rolling(BARS_PER_DAY).std() * annualize
    df["rvol_5d"] = log_ret.rolling(BARS_PER_DAY * 5).std() * annualize
    df["rvol_10d"] = log_ret.rolling(BARS_PER_DAY * 10).std() * annualize
    df["rvol_20d"] = log_ret.rolling(BARS_PER_DAY * 20).std() * annualize

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
    df["obv_slope"] = (obv_values - obv_values.shift(12)) / (obv_values.shift(12).replace(0, np.nan))

    # VWAP deviation — cumulative within each day
    df["_typical_price"] = (high + low + close) / 3
    df["_cum_tp_vol"] = (df["_typical_price"] * volume).groupby(df.index.date).cumsum()
    df["_cum_vol"] = volume.groupby(df.index.date).cumsum()
    vwap = df["_cum_tp_vol"] / df["_cum_vol"].replace(0, np.nan)
    df["vwap_dev"] = (close - vwap) / vwap
    df.drop(columns=["_typical_price", "_cum_tp_vol", "_cum_vol"], inplace=True)

    # =========================================================================
    # Price Position (2)
    # Distance from 20-day high/low as percentage
    # =========================================================================
    rolling_high = high.rolling(BARS_PER_DAY * 20).max()
    rolling_low = low.rolling(BARS_PER_DAY * 20).min()
    df["dist_20d_high"] = (close - rolling_high) / rolling_high
    df["dist_20d_low"] = (close - rolling_low) / rolling_low

    # =========================================================================
    # Time Features (3)
    # =========================================================================
    if df.index.tz is not None:
        eastern = df.index.tz_convert("US/Eastern")
    else:
        eastern = df.index.tz_localize("UTC").tz_convert("US/Eastern")

    df["day_of_week"] = eastern.dayofweek  # 0=Mon, 4=Fri
    df["hour_of_day"] = eastern.hour + eastern.minute / 60.0
    # Minutes until 16:00 close
    df["minutes_to_close"] = (16 * 60) - (eastern.hour * 60 + eastern.minute)
    df["minutes_to_close"] = df["minutes_to_close"].clip(lower=0)

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
```

---

## FILE 4: `options-bot/ml/feature_engineering/swing_features.py`

```python
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
    logger.info("Computing swing-specific features")
    close = df["close"]

    # 1. Distance from 20-day SMA (more precise than sma_ratio_20)
    sma_20d = close.rolling(BARS_PER_DAY * 20).mean()
    df["swing_dist_sma_20d"] = (close - sma_20d) / sma_20d

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
    bounce_from_low = (close - low_5d) / low_5d
    bounce_from_high = (close - high_5d) / high_5d
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
```

---

## FILE 5: `options-bot/ml/feature_engineering/general_features.py`

```python
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
```

---

## STEP 6: Create a test script for feature engineering

**File**: `options-bot/scripts/test_features.py`

```python
"""
Test script for feature engineering.
Fetches a small sample of real data and computes all features.

Usage:
    cd options-bot
    python scripts/test_features.py

Requires:
    - .env configured
    - Theta Terminal running (for options features test)
"""

import sys
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_features")


def test_stock_features():
    """Test stock feature computation with real Alpaca data."""
    logger.info("=" * 60)
    logger.info("TEST: Stock Features (from real Alpaca data)")
    logger.info("=" * 60)

    from data.alpaca_provider import AlpacaStockProvider
    from ml.feature_engineering.base_features import compute_stock_features, get_base_feature_names

    provider = AlpacaStockProvider()

    # Fetch ~2 weeks of 5-min bars (enough for most lookbacks, not all 20d)
    end = datetime.now() - timedelta(hours=1)
    start = end - timedelta(days=14)
    logger.info(f"Fetching 5-min bars: {start.date()} to {end.date()}")
    bars = provider.get_historical_bars("TSLA", start, end, "5min")

    if bars.empty:
        logger.error("❌ No bars returned from Alpaca")
        return False

    logger.info(f"Got {len(bars)} bars")

    # Compute stock features
    df = compute_stock_features(bars.copy())

    # Check feature columns exist
    stock_feature_cols = [c for c in df.columns if c not in ["open", "high", "low", "close", "volume"]]
    logger.info(f"Features computed: {len(stock_feature_cols)}")
    logger.info(f"Feature columns: {stock_feature_cols}")

    # Check for reasonable values on the last row (should have least NaNs)
    last_row = df.iloc[-1]
    nan_count = last_row[stock_feature_cols].isna().sum()
    logger.info(f"NaN count in last row: {nan_count} / {len(stock_feature_cols)}")

    # Spot check some values
    checks = {
        "ret_5min": (-0.05, 0.05),
        "rsi_14": (0, 100),
        "sma_ratio_20": (0.8, 1.2),
        "day_of_week": (0, 4),
    }
    all_ok = True
    for feat, (lo, hi) in checks.items():
        if feat in df.columns:
            val = last_row[feat]
            if pd.isna(val):
                logger.info(f"  {feat}: NaN (expected if < lookback period)")
            elif lo <= val <= hi:
                logger.info(f"  ✅ {feat}: {val:.4f} (range {lo}-{hi})")
            else:
                logger.warning(f"  ⚠️ {feat}: {val:.4f} OUTSIDE expected range {lo}-{hi}")
                all_ok = False

    logger.info(f"Stock features test: {'✅ PASS' if all_ok else '⚠️ CHECK WARNINGS'}")
    return True


def test_swing_features():
    """Test swing feature computation."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST: Swing Features")
    logger.info("=" * 60)

    from data.alpaca_provider import AlpacaStockProvider
    from ml.feature_engineering.base_features import compute_base_features
    from ml.feature_engineering.swing_features import compute_swing_features, get_swing_feature_names

    provider = AlpacaStockProvider()

    end = datetime.now() - timedelta(hours=1)
    start = end - timedelta(days=14)
    bars = provider.get_historical_bars("TSLA", start, end, "5min")

    if bars.empty:
        logger.error("❌ No bars")
        return False

    # Compute base first, then swing
    df = compute_base_features(bars.copy())
    df = compute_swing_features(df)

    swing_cols = get_swing_feature_names()
    present = [c for c in swing_cols if c in df.columns]
    logger.info(f"Swing features present: {len(present)}/{len(swing_cols)}")
    logger.info(f"Swing columns: {present}")

    last_row = df.iloc[-1]
    for col in swing_cols:
        val = last_row.get(col, "MISSING")
        logger.info(f"  {col}: {val}")

    logger.info("Swing features test: ✅ PASS")
    return True


def test_general_features():
    """Test general feature computation."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST: General Features")
    logger.info("=" * 60)

    from data.alpaca_provider import AlpacaStockProvider
    from ml.feature_engineering.base_features import compute_base_features
    from ml.feature_engineering.general_features import compute_general_features, get_general_feature_names

    provider = AlpacaStockProvider()

    end = datetime.now() - timedelta(hours=1)
    start = end - timedelta(days=14)
    bars = provider.get_historical_bars("TSLA", start, end, "5min")

    if bars.empty:
        logger.error("❌ No bars")
        return False

    df = compute_base_features(bars.copy())
    df = compute_general_features(df)

    gen_cols = get_general_feature_names()
    present = [c for c in gen_cols if c in df.columns]
    logger.info(f"General features present: {len(present)}/{len(gen_cols)}")
    logger.info(f"General columns: {present}")

    last_row = df.iloc[-1]
    for col in gen_cols:
        val = last_row.get(col, "MISSING")
        logger.info(f"  {col}: {val}")

    logger.info("General features test: ✅ PASS")
    return True


def test_full_feature_count():
    """Verify total feature counts match architecture spec."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST: Feature Count Verification")
    logger.info("=" * 60)

    from ml.feature_engineering.base_features import get_base_feature_names
    from ml.feature_engineering.swing_features import get_swing_feature_names
    from ml.feature_engineering.general_features import get_general_feature_names

    base = get_base_feature_names()
    swing = get_swing_feature_names()
    general = get_general_feature_names()

    logger.info(f"Base features: {len(base)}")
    logger.info(f"Swing features: {len(swing)}")
    logger.info(f"General features: {len(general)}")
    logger.info(f"Swing total (base + swing): {len(base) + len(swing)}")
    logger.info(f"General total (base + general): {len(base) + len(general)}")

    # Architecture says ~50 per profile
    swing_total = len(base) + len(swing)
    gen_total = len(base) + len(general)

    ok = True
    if swing_total < 40 or swing_total > 60:
        logger.warning(f"⚠️ Swing total {swing_total} outside expected ~50 range")
        ok = False
    if gen_total < 40 or gen_total > 60:
        logger.warning(f"⚠️ General total {gen_total} outside expected ~50 range")
        ok = False

    # Check for duplicate names
    all_swing = base + swing
    all_general = base + general
    if len(all_swing) != len(set(all_swing)):
        logger.error("❌ Duplicate feature names in swing set!")
        ok = False
    if len(all_general) != len(set(all_general)):
        logger.error("❌ Duplicate feature names in general set!")
        ok = False

    logger.info(f"Feature count test: {'✅ PASS' if ok else '❌ FAIL'}")
    return ok


def main():
    logger.info("Feature Engineering Test Suite")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("")

    count_ok = test_full_feature_count()
    stock_ok = test_stock_features()
    swing_ok = test_swing_features()
    general_ok = test_general_features()

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Feature counts:   {'✅' if count_ok else '❌'}")
    logger.info(f"  Stock features:   {'✅' if stock_ok else '❌'}")
    logger.info(f"  Swing features:   {'✅' if swing_ok else '❌'}")
    logger.info(f"  General features: {'✅' if general_ok else '❌'}")

    if all([count_ok, stock_ok, swing_ok, general_ok]):
        logger.info("")
        logger.info("🎉 All feature tests passed. Ready for model training.")


if __name__ == "__main__":
    main()
```

---

## VERIFICATION

After creating all files, run these commands:

```bash
cd options-bot

# 1. Verify files exist
echo "=== Checking files ==="
for f in \
    ml/__init__.py \
    ml/feature_engineering/__init__.py \
    ml/feature_engineering/base_features.py \
    ml/feature_engineering/swing_features.py \
    ml/feature_engineering/general_features.py \
    scripts/test_features.py; do
    if [ -f "$f" ]; then echo "  ✅ $f"; else echo "  ❌ MISSING: $f"; fi
done

# 2. Verify imports
echo ""
echo "=== Testing imports ==="
python -c "from ml.feature_engineering.base_features import compute_base_features, get_base_feature_names; print(f'  ✅ base_features.py: {len(get_base_feature_names())} features')"
python -c "from ml.feature_engineering.swing_features import compute_swing_features, get_swing_feature_names; print(f'  ✅ swing_features.py: {len(get_swing_feature_names())} features')"
python -c "from ml.feature_engineering.general_features import compute_general_features, get_general_feature_names; print(f'  ✅ general_features.py: {len(get_general_feature_names())} features')"

# 3. Run feature tests
echo ""
echo "=== Running feature tests ==="
python scripts/test_features.py
```

## WHAT SUCCESS LOOKS LIKE

1. All 6 files created
2. Imports clean
3. Feature count: base ~41 + swing 5 = ~46, base ~41 + general 5 = ~46 (close to architecture's ~50; options features account for the rest but many will be NaN in this test since we're not passing options data)
4. Stock features computed without errors on real Alpaca data
5. Spot checks pass (RSI between 0-100, SMA ratios between 0.8-1.2, etc.)
6. No duplicate feature names
7. Swing and general features produce non-NaN values where data is sufficient

## WHAT FAILURE LOOKS LIKE

- Import errors (missing `ta` library — should already be in requirements.txt)
- Feature computation crashes on NaN/inf values
- RSI or other indicators outside expected ranges
- Duplicate feature names between base and style features

## DO NOT

- Do NOT create `ml/trainer.py` or any ML training code (that's Prompt 05)
- Do NOT create `data/validator.py` or `data/greeks_calculator.py` yet
- Do NOT fetch years of data in the test — use 2 weeks max
- Do NOT modify any files from previous prompts
- Do NOT add features beyond what Section 8 specifies
- Do NOT create scalp_features.py (that's Phase 5)

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
from config import RISK_FREE_RATE
from data.greeks_calculator import compute_greeks_vectorized

logger = logging.getLogger("options-bot.features.base")

# 78 five-minute bars per 6.5-hour trading day
BARS_PER_DAY = 78


def compute_stock_features(df: pd.DataFrame, bars_per_day: int = 78) -> pd.DataFrame:
    """
    Compute all stock-based features from OHLCV bars.
    Input DataFrame must have columns: [open, high, low, close, volume]
    with a DatetimeIndex.

    Returns the same DataFrame with feature columns added.
    NaN rows at the start (due to lookback) are expected and handled
    by the caller (dropped before training).

    Features computed (~44):
        Price Returns (8): ret_5min, ret_15min, ret_1hr, ret_4hr, ret_1d, ret_5d, ret_10d, ret_20d
        Moving Averages (8): sma_ratio_10..200, ema_ratio_9..50
        Volatility (6): rvol_1hr..20d
        Oscillators (6): rsi_14, rsi_7, macd_line, macd_signal, macd_hist, adx_14
        Bands (5): bb_upper_ratio, bb_lower_ratio, bb_bandwidth, bb_pctb, atr_14_pct
        Volume (3): vol_ratio_20, obv_slope, vwap_dev
        Price Position (2): dist_20d_high, dist_20d_low
        Intraday Momentum (3): intraday_return, gap_from_prev_close, last_hour_momentum
        Time (3): day_of_week, hour_of_day, minutes_to_close
    """
    logger.info(f"Computing stock features for {len(df)} bars (bars_per_day={bars_per_day})")
    if len(df) < 200:
        logger.warning(f"Only {len(df)} bars — need 200+ for all features")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].astype(float)

    # =========================================================================
    # Price Returns (8)
    # =========================================================================
    df["ret_5min"] = close.pct_change(1)
    df["ret_15min"] = close.pct_change(3)
    df["ret_1hr"] = close.pct_change(12)
    df["ret_4hr"] = close.pct_change(48)
    df["ret_1d"] = close.pct_change(bars_per_day)
    df["ret_5d"] = close.pct_change(bars_per_day * 5)
    df["ret_10d"] = close.pct_change(bars_per_day * 10)
    df["ret_20d"] = close.pct_change(bars_per_day * 20)

    # =========================================================================
    # Moving Average Ratios (8)
    # Price / MA — values > 1 mean price above MA
    # =========================================================================
    df["sma_ratio_10"] = close / close.rolling(10).mean().replace(0, np.nan)
    df["sma_ratio_20"] = close / close.rolling(20).mean().replace(0, np.nan)
    df["sma_ratio_50"] = close / close.rolling(50).mean().replace(0, np.nan)
    df["sma_ratio_100"] = close / close.rolling(100).mean().replace(0, np.nan)
    df["sma_ratio_200"] = close / close.rolling(200).mean().replace(0, np.nan)

    df["ema_ratio_9"] = close / close.ewm(span=9, adjust=False).mean().replace(0, np.nan)
    df["ema_ratio_21"] = close / close.ewm(span=21, adjust=False).mean().replace(0, np.nan)
    df["ema_ratio_50"] = close / close.ewm(span=50, adjust=False).mean().replace(0, np.nan)

    # =========================================================================
    # Realized Volatility (6)
    # Annualized std of log returns over various windows
    # Annualization: sqrt(BARS_PER_DAY * 252) for intraday, sqrt(252) for daily
    # =========================================================================
    log_ret = np.log(close / close.shift(1))
    annualize = np.sqrt(bars_per_day * 252)

    df["rvol_1hr"] = log_ret.rolling(12).std() * annualize
    df["rvol_4hr"] = log_ret.rolling(48).std() * annualize
    df["rvol_1d"] = log_ret.rolling(bars_per_day).std() * annualize
    df["rvol_5d"] = log_ret.rolling(bars_per_day * 5).std() * annualize
    df["rvol_10d"] = log_ret.rolling(bars_per_day * 10).std() * annualize
    df["rvol_20d"] = log_ret.rolling(bars_per_day * 20).std() * annualize

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

    df["bb_upper_ratio"] = close / bb_upper.replace(0, np.nan)
    df["bb_lower_ratio"] = close / bb_lower.replace(0, np.nan)
    df["bb_bandwidth"] = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)
    df["bb_pctb"] = bb.bollinger_pband()

    atr = ta.volatility.AverageTrueRange(high, low, close, window=14)
    df["atr_14_pct"] = atr.average_true_range() / close.replace(0, np.nan)

    # =========================================================================
    # Volume Features (3)
    # =========================================================================
    vol_sma_20 = volume.rolling(20).mean()
    df["vol_ratio_20"] = volume / vol_sma_20.replace(0, np.nan)

    obv = ta.volume.OnBalanceVolumeIndicator(close, volume)
    obv_values = obv.on_balance_volume()
    df["obv_slope"] = (obv_values - obv_values.shift(12)) / (obv_values.shift(12).replace(0, np.nan))

    # VWAP deviation — cumulative within each trading day (use Eastern time
    # so sessions don't split at UTC midnight during extended hours)
    if df.index.tz is not None:
        _vwap_dates = df.index.tz_convert("US/Eastern").date
    else:
        # Assumption: tz-naive timestamps are UTC (Alpaca returns UTC timestamps)
        _vwap_dates = df.index.tz_localize("UTC").tz_convert("US/Eastern").date
    df["_typical_price"] = (high + low + close) / 3
    df["_cum_tp_vol"] = (df["_typical_price"] * volume).groupby(_vwap_dates).cumsum()
    df["_cum_vol"] = volume.groupby(_vwap_dates).cumsum()
    vwap = df["_cum_tp_vol"] / df["_cum_vol"].replace(0, np.nan)
    df["vwap_dev"] = (close - vwap) / vwap.replace(0, np.nan)
    df.drop(columns=["_typical_price", "_cum_tp_vol", "_cum_vol"], inplace=True)

    # =========================================================================
    # Price Position (2)
    # Distance from 20-day high/low as percentage
    # =========================================================================
    rolling_high = high.rolling(bars_per_day * 20).max()
    rolling_low = low.rolling(bars_per_day * 20).min()
    df["dist_20d_high"] = (close - rolling_high) / rolling_high.replace(0, np.nan)
    df["dist_20d_low"] = (close - rolling_low) / rolling_low.replace(0, np.nan)

    # =========================================================================
    # Intraday Momentum (3)
    # Captures within-day price action that backward-looking indicators miss.
    # =========================================================================
    if df.index.tz is not None:
        _eastern_idx = df.index.tz_convert("US/Eastern")
    else:
        _eastern_idx = df.index.tz_localize("UTC").tz_convert("US/Eastern")
    _intra_dates = _eastern_idx.date

    # intraday_return: return from today's open to current bar close
    day_open = df["open"].groupby(_intra_dates).transform("first")
    df["intraday_return"] = (close - day_open) / day_open.replace(0, np.nan)

    # gap_from_prev_close: overnight gap (today's open vs yesterday's last close)
    prev_day_close = close.groupby(_intra_dates).transform("last").shift(1)
    df["gap_from_prev_close"] = (day_open - prev_day_close) / prev_day_close.replace(0, np.nan)

    # last_hour_momentum: return over the last 12 bars (1 hour of 5-min bars)
    df["last_hour_momentum"] = close.pct_change(12)

    # =========================================================================
    # Time Features (3)
    # =========================================================================
    if df.index.tz is not None:
        eastern = df.index.tz_convert("US/Eastern")
    else:
        eastern = df.index.tz_localize("UTC").tz_convert("US/Eastern")

    df["day_of_week"] = eastern.dayofweek  # 0=Mon, 4=Fri
    df["hour_of_day"] = eastern.hour + eastern.minute / 60.0
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
            (put_call_oi_ratio removed — ThetaData EOD endpoint does not provide OI)
            - atm_call_spread_pct, atm_put_spread_pct
            Any missing columns will result in NaN features.

    Returns:
        bars_df with options feature columns added.
        Options features are forward-filled to align with 5-min bars.

    Options Features (~20):
        atm_iv, iv_skew, iv_rank_20d, rv_iv_spread,
        put_call_vol_ratio,
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
            "put_call_vol_ratio",
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
        "put_call_vol_ratio",
        "atm_call_delta", "atm_call_theta", "atm_call_gamma", "atm_call_vega",
        "atm_put_delta", "atm_put_theta", "atm_put_gamma", "atm_put_vega",
        "theta_delta_ratio", "gamma_theta_ratio", "vega_theta_ratio",
        "atm_call_spread_pct", "atm_put_spread_pct",
        "rv_iv_spread",
    ]
    # Only include columns that exist
    available_merge_cols = ["date"] + [c for c in merge_cols[1:] if c in opt.columns]
    opt_merge = opt[available_merge_cols].copy()

    # Preserve DatetimeIndex across merge (merge resets to RangeIndex)
    original_index = bars_df.index

    original_row_count = len(bars_df)
    bars_df = bars_df.merge(
        opt_merge,
        left_on="_merge_date",
        right_on="date",
        how="left",
    )
    # Guard: if options data has duplicate dates, the merge can produce more rows
    # than the original bars DataFrame. Drop duplicates to restore 1:1 alignment.
    if len(bars_df) > original_row_count:
        logger.warning(
            f"Options merge produced {len(bars_df)} rows from {original_row_count} bars "
            f"— dropping {len(bars_df) - original_row_count} duplicate rows"
        )
        bars_df = bars_df.iloc[:original_row_count]
    bars_df.index = original_index
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
        "put_call_vol_ratio",
        "atm_call_delta", "atm_call_theta", "atm_call_gamma", "atm_call_vega",
        "atm_put_delta", "atm_put_theta", "atm_put_gamma", "atm_put_vega",
        "theta_delta_ratio", "gamma_theta_ratio", "vega_theta_ratio",
        "atm_call_spread_pct", "atm_put_spread_pct",
    ]
    for col in expected_opt_cols:
        if col not in bars_df.columns:
            bars_df[col] = np.nan

    # ─── 2nd Order Greeks (Phase 4) ────────────────────────────────────────
    # Computed via Black-Scholes using:
    #   S = close price (ATM approximation: K = S)
    #   T = 21/365 (representative swing target DTE — mid-range of 7-45 DTE preset)
    #   r = RISK_FREE_RATE from config (approximate Fed funds)
    #   sigma = atm_iv (already merged above)
    #
    # We use a fixed T = 21 days rather than per-bar DTE because:
    # 1. We don't have per-bar DTE during training (only daily options snapshots)
    # 2. The relative values of vanna/vomma/charm/speed are meaningful even with fixed T
    # 3. The model learns the pattern, not the absolute magnitude
    TARGET_T = 21.0 / 365.0  # 21 calendar days to expiry
    # Note: For scalp profiles using 1-min bars, T=21/365 is still used for
    # 2nd order Greeks in training. The model learns appropriate weights for
    # the scalp context. Live scalp Greeks come from Lumibot at actual DTE.

    if "atm_iv" in bars_df.columns and "close" in bars_df.columns:
        S = bars_df["close"].values
        K = S  # ATM: strike = current price
        T = np.full(len(bars_df), TARGET_T)
        sigma = bars_df["atm_iv"].values
        r = RISK_FREE_RATE

        # Mask where IV is NaN (will produce 0s via vectorized function's valid mask)
        sigma_safe = np.where(np.isnan(sigma), 0.0, sigma)

        call_greeks = compute_greeks_vectorized(S, K, T, r, sigma_safe, option_type="call")
        put_greeks  = compute_greeks_vectorized(S, K, T, r, sigma_safe, option_type="put")

        # Store 2nd order Greeks; replace 0s with NaN where IV was NaN (keep NaN consistent)
        iv_nan_mask = np.isnan(sigma)
        for col, arr in [
            ("atm_call_vanna", call_greeks["vanna"]),
            ("atm_call_vomma", call_greeks["vomma"]),
            ("atm_call_charm", call_greeks["charm"]),
            ("atm_call_speed", call_greeks["speed"]),
            ("atm_put_vanna",  put_greeks["vanna"]),
            ("atm_put_vomma",  put_greeks["vomma"]),
            ("atm_put_charm",  put_greeks["charm"]),
            ("atm_put_speed",  put_greeks["speed"]),
        ]:
            result = arr.copy().astype(float)
            result[iv_nan_mask] = np.nan
            bars_df[col] = result

        logger.info("2nd order Greeks computed: vanna, vomma, charm, speed (call + put)")
    else:
        logger.warning("atm_iv or close not available — 2nd order Greeks will be NaN")
        for col in [
            "atm_call_vanna", "atm_call_vomma", "atm_call_charm", "atm_call_speed",
            "atm_put_vanna",  "atm_put_vomma",  "atm_put_charm",  "atm_put_speed",
        ]:
            bars_df[col] = np.nan

    logger.info(f"Options features merged. Total columns: {len(bars_df.columns)}")
    return bars_df


def compute_base_features(
    bars_df: pd.DataFrame,
    options_daily_df: pd.DataFrame = None,
    vix_daily_df: pd.DataFrame = None,
    bars_per_day: int = 78,
) -> pd.DataFrame:
    """
    Compute all base features (stock + options + VIX).

    Args:
        bars_df: OHLCV DataFrame with DatetimeIndex. Columns: [open, high, low, close, volume]
        options_daily_df: Daily options data (optional). See compute_options_features for schema.
        vix_daily_df: Daily VIX proxy data (optional). DataFrame with 'vixy_close' and
                      optionally 'vixm_close' columns and a DatetimeIndex.

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
    df = compute_stock_features(bars_df.copy(), bars_per_day=bars_per_day)

    # Step 2: Options features
    if options_daily_df is not None and not options_daily_df.empty:
        df = compute_options_features(df, options_daily_df)
    else:
        logger.info("No options data — skipping options features (will be NaN)")
        opt_cols = [
            "atm_iv", "iv_skew", "iv_rank_20d", "rv_iv_spread",
            "put_call_vol_ratio",
            "atm_call_delta", "atm_call_theta", "atm_call_gamma", "atm_call_vega",
            "atm_put_delta", "atm_put_theta", "atm_put_gamma", "atm_put_vega",
            "theta_delta_ratio", "gamma_theta_ratio", "vega_theta_ratio",
            "atm_call_spread_pct", "atm_put_spread_pct",
            # 2nd order Greeks (Phase 4)
            "atm_call_vanna", "atm_call_vomma", "atm_call_charm", "atm_call_speed",
            "atm_put_vanna",  "atm_put_vomma",  "atm_put_charm",  "atm_put_speed",
        ]
        for col in opt_cols:
            df[col] = np.nan

    # Step 3: VIX features (Phase C — volatility regime context)
    # Uses VIXY (short-term VIX ETF) and VIXM (mid-term VIX ETF) as proxies.
    # VIX9D/VIX3M are CBOE indices not available on Alpaca.
    if vix_daily_df is not None and not vix_daily_df.empty and "vixy_close" in vix_daily_df.columns:
        logger.info("Computing VIX features from VIXY/VIXM data")
        # Align VIX daily data to bar-level by date.
        # Use Eastern-time dates for bar alignment (consistent with VWAP, intraday,
        # and time features above). VIX daily data uses calendar dates which align
        # with Eastern trading sessions since US markets operate on Eastern time.
        if df.index.tz is not None:
            _vix_bar_dates = df.index.tz_convert("US/Eastern").date
        else:
            _vix_bar_dates = df.index.tz_localize("UTC").tz_convert("US/Eastern").date
        df["_date"] = _vix_bar_dates

        vix_copy = vix_daily_df.copy()
        if hasattr(vix_copy.index, 'tz') and vix_copy.index.tz is not None:
            vix_copy["_date"] = vix_copy.index.tz_convert("US/Eastern").date
        else:
            vix_copy["_date"] = vix_copy.index.date if hasattr(vix_copy.index, 'date') else pd.to_datetime(vix_copy.index).date

        date_map = vix_copy.set_index("_date")

        # vix_level: VIXY close as proxy for VIX level (VIXY ≈ VIX / 5)
        vixy_series = date_map.get("vixy_close")
        if vixy_series is None:
            logger.warning("VIX feature 'vixy_close' column missing from date_map — vix_level will be NaN")
            df["vix_level"] = np.nan
        else:
            df["vix_level"] = df["_date"].map(vixy_series)
            if df["vix_level"].isna().all():
                logger.warning("vix_level is all-NaN after merge — check VIX date alignment")

        # vix_term_structure: ratio of VIXY to VIXM (contango/backwardation indicator)
        if "vixm_close" in vix_copy.columns:
            date_map["_term_ratio"] = date_map["vixy_close"] / date_map["vixm_close"].replace(0, np.nan)
            term_series = date_map.get("_term_ratio")
            if term_series is None:
                logger.warning("VIX term structure column missing — vix_term_structure will be NaN")
                df["vix_term_structure"] = np.nan
            else:
                df["vix_term_structure"] = df["_date"].map(term_series)
                if df["vix_term_structure"].isna().all():
                    logger.warning("vix_term_structure is all-NaN after merge — check VIX date alignment")
        else:
            logger.warning("'vixm_close' not in VIX data — vix_term_structure will be NaN")
            df["vix_term_structure"] = np.nan

        # vix_change_5d: 5-day change in VIXY (momentum of volatility)
        date_map["_vixy_chg5d"] = date_map["vixy_close"].pct_change(5) * 100
        chg5d_series = date_map.get("_vixy_chg5d")
        if chg5d_series is None:
            logger.warning("VIX 5d change column missing — vix_change_5d will be NaN")
            df["vix_change_5d"] = np.nan
        else:
            df["vix_change_5d"] = df["_date"].map(chg5d_series)
            if df["vix_change_5d"].isna().all():
                logger.warning("vix_change_5d is all-NaN after merge — check VIX date alignment")

        df.drop(columns=["_date"], inplace=True)
        logger.info("VIX features added: vix_level, vix_term_structure, vix_change_5d")
    else:
        logger.info("No VIX data — VIX features will be NaN")
        df["vix_level"] = np.nan
        df["vix_term_structure"] = np.nan
        df["vix_change_5d"] = np.nan

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
        # Intraday Momentum (3)
        "intraday_return", "gap_from_prev_close", "last_hour_momentum",
        # Time (3)
        "day_of_week", "hour_of_day", "minutes_to_close",
        # Options (18)
        "atm_iv", "iv_skew", "iv_rank_20d", "rv_iv_spread",
        "put_call_vol_ratio",
        "atm_call_delta", "atm_call_theta", "atm_call_gamma", "atm_call_vega",
        "atm_put_delta", "atm_put_theta", "atm_put_gamma", "atm_put_vega",
        "theta_delta_ratio", "gamma_theta_ratio", "vega_theta_ratio",
        "atm_call_spread_pct", "atm_put_spread_pct",
        # 2nd Order Greeks (8)
        "atm_call_vanna", "atm_call_vomma", "atm_call_charm", "atm_call_speed",
        "atm_put_vanna", "atm_put_vomma", "atm_put_charm", "atm_put_speed",
        # VIX Features (3) — Phase C
        "vix_level", "vix_term_structure", "vix_change_5d",
    ]

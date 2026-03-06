"""
Historical options data fetcher for ML training.

Fetches daily ATM options snapshots from Theta Terminal V3 (EOD endpoint),
computes implied volatility from option prices via Black-Scholes bisection,
and returns a DataFrame matching the schema expected by
compute_options_features() in base_features.py.

Strategy:
    1. Extract daily close prices from stock bars to determine ATM strikes
    2. Group trading days into monthly batches
    3. For each batch, pick a monthly expiration (~30 DTE from mid-period)
    4. Fetch bulk EOD data from Theta (all strikes, calls + puts)
    5. For each day, extract ATM data and compute IV from option midpoint prices
    6. Compute IV skew from OTM put/call IV
    7. Cache results to parquet for subsequent training runs

The EOD endpoint returns 1 row per strike per day and supports date ranges,
making it ~100x more efficient than the intraday Greeks endpoint.
"""

import io
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import THETA_BASE_URL_V3, PROJECT_ROOT, RISK_FREE_RATE

logger = logging.getLogger("options-bot.data.options_fetcher")

CACHE_DIR = PROJECT_ROOT / "data" / "cache"
# Intentionally 30s (vs theta_provider's 60s) — EOD fetcher makes simpler
# requests that should complete faster; a shorter timeout surfaces stalls sooner.
REQUEST_TIMEOUT = 30


# ─────────────────────────────────────────────────────────────────────────────
# Black-Scholes IV solver
# ─────────────────────────────────────────────────────────────────────────────

def _bs_price(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str = "call") -> float:
    """Black-Scholes option price."""
    if T <= 1e-8 or sigma <= 1e-8 or S <= 0 or K <= 0:
        return 0.0
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    if option_type == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    else:
        return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def _implied_vol(market_price: float, S: float, K: float, T: float,
                 r: float, option_type: str = "call") -> float:
    """
    Solve for implied volatility using bisection.
    Returns NaN if no solution found or inputs are invalid.
    """
    if market_price <= 0 or T <= 1e-8 or S <= 0 or K <= 0:
        return np.nan

    # Intrinsic value check
    if option_type == "call":
        intrinsic = max(S - K * np.exp(-r * T), 0)
    else:
        intrinsic = max(K * np.exp(-r * T) - S, 0)
    if market_price < intrinsic * 0.9:
        return np.nan  # Price below intrinsic — bad data

    lo, hi = 0.01, 5.0  # IV range: 1% to 500%
    for _ in range(60):
        mid = (lo + hi) / 2
        bs = _bs_price(S, K, T, r, mid, option_type)
        if abs(bs - market_price) < 0.005:
            return mid
        if bs > market_price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ─────────────────────────────────────────────────────────────────────────────
# Expiration picker
# ─────────────────────────────────────────────────────────────────────────────

def _third_friday(year: int, month: int) -> date:
    """Get the 3rd Friday of a given month (standard monthly options expiration)."""
    # 1st of month
    first = date(year, month, 1)
    # Find first Friday: weekday 4 = Friday
    first_friday = first + timedelta(days=(4 - first.weekday()) % 7)
    # 3rd Friday = first Friday + 14 days
    return first_friday + timedelta(days=14)


def _pick_expiration_for_period(mid_date: date, target_dte: int = 30) -> date:
    """
    Pick a monthly expiration approximately target_dte days from mid_date.
    Returns the 3rd Friday of the appropriate month.
    """
    target = mid_date + timedelta(days=target_dte)
    # Get the 3rd Friday of the target month
    exp = _third_friday(target.year, target.month)
    # If the 3rd Friday is before our target, use next month
    if exp < mid_date + timedelta(days=max(target_dte - 10, 7)):
        if target.month == 12:
            exp = _third_friday(target.year + 1, 1)
        else:
            exp = _third_friday(target.year, target.month + 1)
    return exp


# ─────────────────────────────────────────────────────────────────────────────
# Theta EOD fetcher
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_eod_batch(
    symbol: str,
    expiration: date,
    start_date: date,
    end_date: date,
    base_url: str = THETA_BASE_URL_V3,
) -> pd.DataFrame:
    """
    Fetch EOD options data for ALL strikes, both call+put, over a date range.
    Returns DataFrame with columns: [symbol, expiration, strike, right, created,
    last_trade, open, high, low, close, volume, count, bid, ask, ...]
    """
    url = f"{base_url}/option/history/eod"
    params = {
        "symbol": symbol,
        "expiration": expiration.strftime("%Y%m%d"),
        "strike": "*",
        "right": "both",
        "start_date": start_date.strftime("%Y%m%d"),
        "end_date": end_date.strftime("%Y%m%d"),
    }

    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                df = pd.read_csv(io.StringIO(resp.text))
                return df
            elif resp.status_code in (404, 472):
                # No data for this expiration/date range
                return pd.DataFrame()
            else:
                logger.warning(
                    f"Theta EOD status {resp.status_code} for {symbol} "
                    f"exp={expiration} {start_date}-{end_date}: {resp.text[:100]}"
                )
        except requests.exceptions.ConnectionError:
            logger.warning(f"Theta connection failed (attempt {attempt+1})")
        except requests.exceptions.Timeout:
            logger.warning(f"Theta timeout (attempt {attempt+1})")
        except Exception as e:
            logger.warning(f"Theta error: {e} (attempt {attempt+1})")

        if attempt < 2:
            time.sleep(1 * (attempt + 1))

    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Daily aggregation
# ─────────────────────────────────────────────────────────────────────────────

def _process_eod_day(
    day_df: pd.DataFrame,
    underlying_close: float,
    expiration: date,
    trade_date: date,
) -> dict:
    """
    Process one day of EOD data (all strikes, both sides) into
    the daily options snapshot that compute_options_features() expects.

    Returns dict with keys matching the options_daily_df schema.
    """
    if day_df.empty or underlying_close <= 0:
        return {}

    # Normalize column names
    df = day_df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    # Parse strike as float
    if "strike" not in df.columns:
        return {}
    df["strike"] = df["strike"].astype(float)

    # Normalize right column
    right_col = None
    for c in df.columns:
        if c in ("right", "type", "call_put"):
            right_col = c
            break
    if right_col is None:
        return {}
    df["_right"] = df[right_col].astype(str).str.strip().str.upper()

    # Find ATM strike (closest to underlying close)
    strikes = sorted(df["strike"].unique())
    if not strikes:
        return {}
    atm_strike = min(strikes, key=lambda s: abs(s - underlying_close))

    # Days to expiration
    dte = (expiration - trade_date).days
    if dte <= 0:
        return {}
    T = dte / 365.0

    result = {"date": trade_date}

    # ── ATM Call ──
    atm_calls = df[(df["strike"] == atm_strike) & (df["_right"].isin(["CALL", "C"]))]
    if not atm_calls.empty:
        row = atm_calls.iloc[-1]
        bid = float(row.get("bid", 0) or 0)
        ask = float(row.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(row.get("close", 0) or 0)

        if mid > 0:
            iv = _implied_vol(mid, underlying_close, atm_strike, T,
                              RISK_FREE_RATE, "call")
            if not np.isnan(iv) and iv > 0.01:
                result["atm_iv"] = iv

                # Compute 1st order Greeks from IV
                from data.greeks_calculator import compute_greeks
                greeks = compute_greeks(underlying_close, atm_strike, T,
                                        RISK_FREE_RATE, iv, "call")
                result["atm_call_delta"] = greeks["delta"]
                result["atm_call_gamma"] = greeks["gamma"]
                result["atm_call_theta"] = greeks["theta"]
                result["atm_call_vega"] = greeks["vega"]

        # Bid-ask spread
        if bid > 0 and ask > 0 and mid > 0:
            result["atm_call_spread_pct"] = (ask - bid) / mid

    # ── ATM Put ──
    atm_puts = df[(df["strike"] == atm_strike) & (df["_right"].isin(["PUT", "P"]))]
    if not atm_puts.empty:
        row = atm_puts.iloc[-1]
        bid = float(row.get("bid", 0) or 0)
        ask = float(row.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(row.get("close", 0) or 0)

        if mid > 0:
            iv = _implied_vol(mid, underlying_close, atm_strike, T,
                              RISK_FREE_RATE, "put")
            if not np.isnan(iv) and iv > 0.01:
                from data.greeks_calculator import compute_greeks
                greeks = compute_greeks(underlying_close, atm_strike, T,
                                        RISK_FREE_RATE, iv, "put")
                result["atm_put_delta"] = greeks["delta"]
                result["atm_put_gamma"] = greeks["gamma"]
                result["atm_put_theta"] = greeks["theta"]
                result["atm_put_vega"] = greeks["vega"]

        if bid > 0 and ask > 0 and mid > 0:
            result["atm_put_spread_pct"] = (ask - bid) / mid

    # ── IV Skew (OTM put IV - OTM call IV) ──
    # Use ~5% OTM strikes
    otm_offset = underlying_close * 0.05
    otm_put_strike = min(strikes, key=lambda s: abs(s - (underlying_close - otm_offset)))
    otm_call_strike = min(strikes, key=lambda s: abs(s - (underlying_close + otm_offset)))

    otm_put_iv = np.nan
    otm_call_iv = np.nan

    otm_puts = df[(df["strike"] == otm_put_strike) & (df["_right"].isin(["PUT", "P"]))]
    if not otm_puts.empty:
        row = otm_puts.iloc[-1]
        bid = float(row.get("bid", 0) or 0)
        ask = float(row.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(row.get("close", 0) or 0)
        if mid > 0:
            otm_put_iv = _implied_vol(mid, underlying_close, otm_put_strike, T,
                                      RISK_FREE_RATE, "put")

    otm_calls = df[(df["strike"] == otm_call_strike) & (df["_right"].isin(["CALL", "C"]))]
    if not otm_calls.empty:
        row = otm_calls.iloc[-1]
        bid = float(row.get("bid", 0) or 0)
        ask = float(row.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(row.get("close", 0) or 0)
        if mid > 0:
            otm_call_iv = _implied_vol(mid, underlying_close, otm_call_strike, T,
                                       RISK_FREE_RATE, "call")

    if not np.isnan(otm_put_iv) and not np.isnan(otm_call_iv):
        result["iv_skew"] = otm_put_iv - otm_call_iv

    # ── Put/Call Volume Ratio ──
    call_vol = df[df["_right"].isin(["CALL", "C"])]["volume"].sum()
    put_vol = df[df["_right"].isin(["PUT", "P"])]["volume"].sum()
    if call_vol > 0:
        result["put_call_vol_ratio"] = put_vol / call_vol

    # ── Put/Call Open Interest Ratio ──
    # EOD endpoint doesn't include OI, so leave as NaN

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main public API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_options_for_training(
    symbol: str,
    bars_df: pd.DataFrame,
    min_dte: int = 7,
    max_dte: int = 45,
    use_cache: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Fetch historical daily options data from Theta Terminal for training.

    Args:
        symbol: Ticker symbol (e.g. "TSLA")
        bars_df: Stock bars DataFrame with DatetimeIndex and 'close' column.
                 Used to determine trading days and ATM strikes.
        min_dte: Minimum days to expiration (from profile preset)
        max_dte: Maximum days to expiration (from profile preset)
        use_cache: Whether to use disk cache

    Returns:
        DataFrame with daily options data matching compute_options_features() schema:
        [date, atm_call_delta, atm_call_gamma, atm_call_theta, atm_call_vega,
         atm_put_delta, atm_put_gamma, atm_put_theta, atm_put_vega,
         atm_iv, iv_skew, put_call_vol_ratio, atm_call_spread_pct,
         atm_put_spread_pct]
        Returns None if Theta Terminal is unavailable.
    """
    pipeline_start = time.time()
    target_dte = (min_dte + max_dte) // 2  # e.g., 26 for swing

    # ── Extract daily close prices ──
    if bars_df.index.tz is not None:
        et_index = bars_df.index.tz_convert("US/Eastern")
    else:
        et_index = bars_df.index.tz_localize("UTC").tz_convert("US/Eastern")

    daily_close = bars_df["close"].copy()
    daily_close.index = et_index
    daily_close = daily_close.groupby(daily_close.index.date).last()
    # daily_close: index=date, values=close price

    trading_days = sorted(daily_close.index)
    if not trading_days:
        logger.warning("No trading days found in bars_df")
        return None

    first_day = trading_days[0]
    last_day = trading_days[-1]
    logger.info(
        f"Fetching options data for {symbol}: {first_day} to {last_day} "
        f"({len(trading_days)} trading days, target_dte={target_dte})"
    )

    # ── Check cache ──
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{symbol}_options_daily_dte{min_dte}-{max_dte}.parquet"

    cached_df = None
    cached_dates = set()
    if use_cache and cache_file.exists():
        try:
            cached_df = pd.read_parquet(cache_file)
            cached_df["date"] = pd.to_datetime(cached_df["date"]).dt.date
            cached_dates = set(cached_df["date"])
            logger.info(f"Cache loaded: {len(cached_dates)} days from {cache_file.name}")
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")
            cached_df = None

    # Determine which days need fetching.
    # Exclude today — EOD data won't exist until after market close.
    # Yesterday's daily options data gets forward-filled to today's bars,
    # which is correct since options features are daily resolution.
    today = date.today()
    needed_days = [d for d in trading_days if d not in cached_dates and d != today]
    if not needed_days:
        logger.info("All trading days found in cache — no Theta fetch needed")
        result = cached_df[cached_df["date"].isin(set(trading_days))].copy()
        result = result.sort_values("date").reset_index(drop=True)
        elapsed = time.time() - pipeline_start
        logger.info(f"Options data ready from cache: {len(result)} days in {elapsed:.1f}s")
        return result

    logger.info(f"Need to fetch {len(needed_days)} days from Theta ({len(cached_dates)} cached)")

    # ── Test Theta connectivity (only when cache doesn't cover all days) ──
    try:
        resp = requests.get(
            f"{THETA_BASE_URL_V3}/stock/list/symbols",
            timeout=5,
        )
        if resp.status_code != 200:
            logger.warning("Theta Terminal not responding — cannot fetch options data")
            return None
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        logger.warning("Theta Terminal not connected — cannot fetch options data")
        return None

    # ── Group needed days into monthly batches ──
    # Each batch: same month, same expiration
    from collections import defaultdict
    monthly_batches = defaultdict(list)
    for d in needed_days:
        key = (d.year, d.month)
        monthly_batches[key].append(d)

    # ── Fetch each batch ──
    new_rows = []
    total_batches = len(monthly_batches)
    fetch_start = time.time()

    for batch_idx, ((year, month), days) in enumerate(sorted(monthly_batches.items()), 1):
        mid_date = date(year, month, 15)
        expiration = _pick_expiration_for_period(mid_date, target_dte)

        batch_start = min(days)
        batch_end = max(days)

        logger.info(
            f"  Batch {batch_idx}/{total_batches}: {year}-{month:02d} "
            f"({len(days)} days, exp={expiration})"
        )

        eod_df = _fetch_eod_batch(symbol, expiration, batch_start, batch_end)

        if eod_df.empty:
            logger.debug(f"  No EOD data for {symbol} exp={expiration} {batch_start}-{batch_end}")
            # Try an alternate expiration (next month)
            if month == 12:
                alt_exp = _third_friday(year + 1, 1)
            else:
                alt_exp = _third_friday(year, month + 1)
            if alt_exp != expiration:
                logger.debug(f"  Trying alternate expiration: {alt_exp}")
                eod_df = _fetch_eod_batch(symbol, alt_exp, batch_start, batch_end)
                if not eod_df.empty:
                    expiration = alt_exp

        if eod_df.empty:
            logger.debug(f"  Skipping batch {year}-{month:02d} (no data)")
            continue

        # Parse trade date from 'created' column.
        # .str[:10] assumes ISO-8601 prefix "YYYY-MM-DD..." (Theta V3 format).
        # Wrapped in try/except in case Theta changes the date format.
        if "created" in eod_df.columns:
            try:
                eod_df["_trade_date"] = pd.to_datetime(
                    eod_df["created"].str[:10]
                ).dt.date
            except Exception as e:
                logger.warning(f"  Failed to parse 'created' column dates: {e}")
                continue
        elif "last_trade" in eod_df.columns:
            try:
                eod_df["_trade_date"] = pd.to_datetime(
                    eod_df["last_trade"].str[:10]
                ).dt.date
            except Exception as e:
                logger.warning(f"  Failed to parse 'last_trade' column dates: {e}")
                continue
        else:
            logger.warning("  No date column found in EOD data")
            continue

        # Process each day in this batch
        for d in days:
            day_data = eod_df[eod_df["_trade_date"] == d]
            if day_data.empty:
                continue

            close_price = daily_close.get(d)
            if close_price is None or np.isnan(close_price):
                continue

            row = _process_eod_day(day_data, float(close_price), expiration, d)
            if row and "atm_iv" in row:
                new_rows.append(row)

    fetch_elapsed = time.time() - fetch_start
    logger.info(
        f"Theta fetch complete: {len(new_rows)} days with options data "
        f"out of {len(needed_days)} requested ({fetch_elapsed:.1f}s)"
    )

    # ── Merge with cache and save ──
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        if cached_df is not None and not cached_df.empty:
            combined = pd.concat([cached_df, new_df], ignore_index=True)
            # Deduplicate by date (prefer newer data)
            combined = combined.drop_duplicates(subset=["date"], keep="last")
        else:
            combined = new_df

        combined = combined.sort_values("date").reset_index(drop=True)

        # Save cache
        try:
            combined.to_parquet(cache_file, index=False)
            logger.info(f"Cache updated: {len(combined)} days saved to {cache_file.name}")
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")
    else:
        combined = cached_df if cached_df is not None else pd.DataFrame()

    # Filter to requested trading days
    if combined is not None and not combined.empty:
        result = combined[combined["date"].isin(set(trading_days))].copy()
        result = result.sort_values("date").reset_index(drop=True)
    else:
        result = pd.DataFrame()

    elapsed = time.time() - pipeline_start
    coverage = len(result) / len(trading_days) * 100 if trading_days else 0
    logger.info(
        f"Options data ready: {len(result)}/{len(trading_days)} days "
        f"({coverage:.0f}% coverage) in {elapsed:.1f}s"
    )

    return result if not result.empty else None

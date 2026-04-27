"""
Data integrity validator for training symbols.
Matches PROJECT_ARCHITECTURE.md Section 13 Phase 2, item 8.

Called programmatically before model training to confirm:
    1. Alpaca returns data for the symbol
    2. Sufficient historical depth (configurable minimum days)
    3. No large gaps in the data (missing trading days)
    4. OHLCV values are in a reasonable range (no zeros, no nulls in price)
    5. Adequate bar count for feature computation

This is NOT a connection tester — that is scripts/validate_data.py.
This validates the actual data returned for a symbol is clean and usable.

Usage:
    from data.validator import validate_symbol_data

    result = validate_symbol_data("NVDA")
    if result["valid"]:
        print("Data OK — safe to train")
    else:
        print(f"Data issues: {result['issues']}")
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("options-bot.data.validator")

# Minimum number of calendar days of history required
MIN_HISTORY_DAYS = 365

# Minimum number of 5-min bars required (roughly 252 trading days × 78 bars)
MIN_BAR_COUNT = 10000

# Maximum allowed gap between consecutive trading days (in calendar days).
# Gaps larger than this (excluding weekends/holidays) flag a data issue.
MAX_GAP_DAYS = 5

# A trading day is expected to have at least this many 5-min bars
MIN_BARS_PER_DAY = 50

# Percentage of trading days allowed to have fewer than MIN_BARS_PER_DAY bars
# (accommodates early closes, partial data days at edges)
MAX_SHORT_DAY_PCT = 5.0

# How many recent days to sample for the validation fetch
VALIDATION_FETCH_DAYS = 30

# How many historical days to fetch for the depth check
DEPTH_CHECK_YEARS = 2


def _check_bar_count(bars_df: pd.DataFrame, symbol: str) -> tuple:
    """
    Check that there are enough bars overall.

    Returns (passed: bool, detail: str)
    """
    count = len(bars_df)
    passed = count >= MIN_BAR_COUNT
    detail = (
        f"{count:,} bars ({'OK' if passed else f'INSUFFICIENT — need {MIN_BAR_COUNT:,}'})"
    )
    logger.info(f"  Bar count check: {detail}")
    return passed, detail


def _check_data_depth(bars_df: pd.DataFrame, symbol: str) -> tuple:
    """
    Check that data goes back far enough.

    Returns (passed: bool, detail: str)
    """
    if bars_df.empty:
        return False, "No data returned"

    earliest = bars_df.index.min()
    latest = bars_df.index.max()

    if hasattr(earliest, "tz_convert"):
        earliest_naive = earliest.tz_convert("UTC").replace(tzinfo=None)
        latest_naive = latest.tz_convert("UTC").replace(tzinfo=None)
    else:
        earliest_naive = earliest
        latest_naive = latest

    span_days = (latest_naive - earliest_naive).days
    passed = span_days >= MIN_HISTORY_DAYS

    detail = (
        f"Earliest={earliest.date()} Latest={latest.date()} "
        f"Span={span_days} days "
        f"({'OK' if passed else f'INSUFFICIENT — need {MIN_HISTORY_DAYS} days'})"
    )
    logger.info(f"  Data depth check: {detail}")
    return passed, detail


def _check_gaps(bars_df: pd.DataFrame, symbol: str) -> tuple:
    """
    Check for large gaps between consecutive trading days.
    Gaps > MAX_GAP_DAYS calendar days (beyond weekends/holidays) are flagged.

    Returns (passed: bool, detail: str, gap_list: list)
    """
    if bars_df.empty:
        return False, "No data", []

    # Get unique trading dates
    if bars_df.index.tz is not None:
        dates = pd.DatetimeIndex(
            bars_df.index.tz_convert("US/Eastern").normalize().unique()
        )
    else:
        dates = pd.DatetimeIndex(bars_df.index.normalize().unique())

    dates = dates.sort_values()

    if len(dates) < 2:
        return True, "Only 1 trading day — cannot check gaps", []

    # Find gaps between consecutive dates larger than MAX_GAP_DAYS
    large_gaps = []
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i - 1]).days
        if gap > MAX_GAP_DAYS:
            large_gaps.append({
                "from": str(dates[i - 1].date()),
                "to": str(dates[i].date()),
                "gap_days": gap,
            })

    passed = len(large_gaps) == 0
    if passed:
        detail = f"No large gaps found across {len(dates)} trading days"
    else:
        detail = (
            f"{len(large_gaps)} gap(s) > {MAX_GAP_DAYS} days found: "
            + ", ".join(
                f"{g['from']} → {g['to']} ({g['gap_days']}d)" for g in large_gaps[:3]
            )
            + ("..." if len(large_gaps) > 3 else "")
        )

    logger.info(f"  Gap check: {detail}")
    return passed, detail, large_gaps


def _check_ohlcv_quality(bars_df: pd.DataFrame, symbol: str) -> tuple:
    """
    Check OHLCV values for obvious data quality issues:
    - Zero or negative close prices
    - NaN in close column
    - High < Low (inverted bars)
    - Volume = 0 for more than a small fraction of bars

    Returns (passed: bool, detail: str, issues_list: list)
    """
    if bars_df.empty:
        return False, "No data", ["No data returned"]

    issues = []

    # Ensure lowercase column names
    df = bars_df.copy()
    df.columns = [c.lower() for c in df.columns]

    # Check for required columns
    required_cols = ["open", "high", "low", "close", "volume"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        issues.append(f"Missing columns: {missing_cols}")
        return False, f"Missing columns: {missing_cols}", issues

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # NaN in close
    nan_count = close.isna().sum()
    if nan_count > 0:
        issues.append(f"{nan_count} NaN values in close column")

    # Zero or negative close
    bad_close = (close <= 0).sum()
    if bad_close > 0:
        issues.append(f"{bad_close} bars with close <= 0")

    # Inverted bars (high < low)
    inverted = (high < low).sum()
    if inverted > 0:
        issues.append(f"{inverted} inverted bars (high < low)")

    # Zero volume bars (warn if > 10% of bars)
    zero_vol = (volume == 0).sum()
    zero_vol_pct = (zero_vol / len(df)) * 100
    if zero_vol_pct > 10:
        issues.append(f"{zero_vol_pct:.1f}% of bars have zero volume")

    # Price sanity: close should not jump more than 50% in a single bar
    # (catches obvious data errors, not real events)
    pct_change = close.pct_change().abs()
    extreme_moves = (pct_change > 0.50).sum()
    if extreme_moves > 5:
        issues.append(
            f"{extreme_moves} bars with >50% single-bar price change "
            f"(possible data error)"
        )

    passed = len(issues) == 0
    detail = (
        f"Close range ${close.min():.2f}–${close.max():.2f} | "
        f"NaN={nan_count} | ZeroVol={zero_vol_pct:.1f}% | "
        + ("OK" if passed else f"Issues: {'; '.join(issues)}")
    )
    logger.info(f"  OHLCV quality check: {detail}")
    return passed, detail, issues


def _check_daily_completeness(bars_df: pd.DataFrame, symbol: str) -> tuple:
    """
    Check that most trading days have a full session worth of bars.
    Days with fewer than MIN_BARS_PER_DAY bars may indicate missing data.

    Returns (passed: bool, detail: str)
    """
    if bars_df.empty:
        return False, "No data"

    if bars_df.index.tz is not None:
        eastern = bars_df.index.tz_convert("US/Eastern")
    else:
        eastern = bars_df.index

    daily_counts = bars_df.groupby(eastern.date).size()
    total_days = len(daily_counts)

    if total_days == 0:
        return False, "No trading days found"

    short_days = (daily_counts < MIN_BARS_PER_DAY).sum()
    short_day_pct = (short_days / total_days) * 100

    passed = short_day_pct <= MAX_SHORT_DAY_PCT
    detail = (
        f"{total_days} trading days | "
        f"Avg bars/day: {daily_counts.mean():.0f} | "
        f"Short days (<{MIN_BARS_PER_DAY} bars): {short_days} ({short_day_pct:.1f}%) "
        f"({'OK' if passed else f'HIGH — limit {MAX_SHORT_DAY_PCT}%'})"
    )
    logger.info(f"  Daily completeness check: {detail}")
    return passed, detail


def validate_symbol_data(
    symbol: str,
    years: int = DEPTH_CHECK_YEARS,
    strict: bool = False,
) -> dict:
    """
    Validate that historical data for a symbol is clean and sufficient for training.

    Fetches `years` of 5-min bars from Alpaca, then runs 5 checks:
        1. Bar count — enough total bars
        2. Data depth — history goes back far enough
        3. Gaps — no large missing windows
        4. OHLCV quality — no bad prices or inverted bars
        5. Daily completeness — most days have full sessions

    Args:
        symbol: Ticker symbol to validate (e.g., "NVDA").
        years: How many years of history to fetch for validation.
        strict: If True, ALL checks must pass for valid=True.
                If False (default), minor issues in checks 3 and 5 do not
                fail validation as long as checks 1, 2, and 4 pass.

    Returns:
        {
            "symbol": str,
            "valid": bool,
            "checks": {
                "bar_count": {"passed": bool, "detail": str},
                "data_depth": {"passed": bool, "detail": str},
                "gaps": {"passed": bool, "detail": str},
                "ohlcv_quality": {"passed": bool, "detail": str},
                "daily_completeness": {"passed": bool, "detail": str},
            },
            "issues": [str],         # All failed check details
            "warnings": [str],       # Non-critical issues (strict=False only)
            "bar_count": int,        # Total bars fetched
            "fetch_time_seconds": float,
            "data_start": str,       # Earliest date fetched (ISO)
            "data_end": str,         # Latest date fetched (ISO)
            "error": str or None,    # Set if an exception occurred during fetch
        }
    """
    logger.info("=" * 60)
    logger.info(f"Validating symbol: {symbol} ({years} years of data)")
    logger.info("=" * 60)

    result = {
        "symbol": symbol,
        "valid": False,
        "checks": {},
        "issues": [],
        "warnings": [],
        "bar_count": 0,
        "fetch_time_seconds": 0.0,
        "data_start": None,
        "data_end": None,
        "error": None,
    }

    # -------------------------------------------------------------------------
    # Fetch data
    # -------------------------------------------------------------------------
    logger.info(f"Fetching {years} years of 5-min bars for {symbol}...")
    fetch_start = time.time()

    try:
        from data.alpaca_provider import AlpacaStockProvider
        provider = AlpacaStockProvider()

        end_date = datetime.now(timezone.utc) - timedelta(hours=1)
        start_date = end_date - timedelta(days=years * 365)

        bars_df = provider.get_historical_bars(
            symbol, start_date, end_date, timeframe="5min"
        )
    except Exception as e:
        result["error"] = f"Failed to fetch data: {e}"
        result["issues"].append(result["error"])
        logger.error(f"Data fetch failed for {symbol}: {e}", exc_info=True)
        return result

    fetch_elapsed = time.time() - fetch_start
    result["fetch_time_seconds"] = round(fetch_elapsed, 1)

    if bars_df is None or bars_df.empty:
        result["error"] = f"No data returned from Alpaca for {symbol}"
        result["issues"].append(result["error"])
        logger.error(result["error"])
        return result

    result["bar_count"] = len(bars_df)
    result["data_start"] = str(bars_df.index.min().date())
    result["data_end"] = str(bars_df.index.max().date())

    logger.info(
        f"Fetched {len(bars_df):,} bars in {fetch_elapsed:.1f}s "
        f"({result['data_start']} to {result['data_end']})"
    )

    # -------------------------------------------------------------------------
    # Run checks
    # -------------------------------------------------------------------------

    # Check 1: Bar count
    passed, detail = _check_bar_count(bars_df, symbol)
    result["checks"]["bar_count"] = {"passed": passed, "detail": detail}
    if not passed:
        result["issues"].append(f"Bar count: {detail}")

    # Check 2: Data depth
    passed, detail = _check_data_depth(bars_df, symbol)
    result["checks"]["data_depth"] = {"passed": passed, "detail": detail}
    if not passed:
        result["issues"].append(f"Data depth: {detail}")

    # Check 3: Gaps
    passed, detail, gaps = _check_gaps(bars_df, symbol)
    result["checks"]["gaps"] = {"passed": passed, "detail": detail}
    if not passed:
        if strict:
            result["issues"].append(f"Gaps: {detail}")
        else:
            result["warnings"].append(f"Gaps: {detail}")

    # Check 4: OHLCV quality
    passed, detail, ohlcv_issues = _check_ohlcv_quality(bars_df, symbol)
    result["checks"]["ohlcv_quality"] = {"passed": passed, "detail": detail}
    if not passed:
        result["issues"].append(f"OHLCV quality: {detail}")

    # Check 5: Daily completeness
    passed, detail = _check_daily_completeness(bars_df, symbol)
    result["checks"]["daily_completeness"] = {"passed": passed, "detail": detail}
    if not passed:
        if strict:
            result["issues"].append(f"Daily completeness: {detail}")
        else:
            result["warnings"].append(f"Daily completeness: {detail}")

    # -------------------------------------------------------------------------
    # Overall validity
    # -------------------------------------------------------------------------
    # Critical checks: bar_count, data_depth, ohlcv_quality must pass
    # Non-critical (in non-strict mode): gaps, daily_completeness
    critical_checks = ["bar_count", "data_depth", "ohlcv_quality"]
    critical_passed = all(
        result["checks"][c]["passed"] for c in critical_checks
    )

    if strict:
        result["valid"] = len(result["issues"]) == 0
    else:
        result["valid"] = critical_passed

    # -------------------------------------------------------------------------
    # Summary log
    # -------------------------------------------------------------------------
    logger.info("")
    logger.info(f"Validation result for {symbol}: {'VALID' if result['valid'] else 'INVALID'}")
    for check_name, check_result in result["checks"].items():
        icon = "OK" if check_result["passed"] else "FAIL"
        logger.info(f"  [{icon}] {check_name}: {check_result['detail']}")
    if result["issues"]:
        logger.warning(f"  Issues: {result['issues']}")
    if result["warnings"]:
        logger.info(f"  Warnings (non-critical): {result['warnings']}")

    return result


def validate_all_symbols(
    symbols: list = None,
    years: int = DEPTH_CHECK_YEARS,
    strict: bool = False,
) -> dict:
    """
    Validate multiple symbols and return a summary.

    Args:
        symbols: List of symbols to validate. Defaults to ALL_SYMBOLS from config.
        years: Years of history to fetch per symbol.
        strict: Passed through to validate_symbol_data().

    Returns:
        {
            "all_valid": bool,
            "results": {symbol: validate_symbol_data result},
            "summary": {
                "total": int,
                "valid": int,
                "invalid": int,
            }
        }
    """
    if symbols is None:
        from config import ALL_SYMBOLS
        symbols = ALL_SYMBOLS

    logger.info(f"Validating {len(symbols)} symbols: {symbols}")

    all_results = {}
    for symbol in symbols:
        try:
            all_results[symbol] = validate_symbol_data(symbol, years=years, strict=strict)
        except Exception as e:
            logger.error(f"validate_all_symbols: unexpected error for {symbol}: {e}", exc_info=True)
            all_results[symbol] = {
                "symbol": symbol,
                "valid": False,
                "error": str(e),
                "checks": {},
                "issues": [str(e)],
                "warnings": [],
            }

    valid_count = sum(1 for r in all_results.values() if r["valid"])
    invalid_count = len(symbols) - valid_count

    logger.info("")
    logger.info("=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)
    for symbol, r in all_results.items():
        icon = "VALID" if r["valid"] else "INVALID"
        logger.info(f"  [{icon}] {symbol}")
    logger.info(f"  Total: {len(symbols)} | Valid: {valid_count} | Invalid: {invalid_count}")

    return {
        "all_valid": invalid_count == 0,
        "results": all_results,
        "summary": {
            "total": len(symbols),
            "valid": valid_count,
            "invalid": invalid_count,
        },
    }

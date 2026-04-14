"""
Earnings calendar checker using yfinance.

Used by base_strategy.py to skip entries when earnings fall inside
the hold window (IV crush risk).

Fail-open: if the library is unavailable or times out, allows the trade.
Cache: results cached per symbol for 24 hours.
"""
import logging
import time
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("options-bot.data.earnings_calendar")

# In-memory cache: {symbol: {"earnings_dates": list[date], "fetched_at": float}}
_cache: dict = {}
_CACHE_TTL_SECONDS = 86400  # 24 hours


def has_earnings_in_window(
    symbol: str,
    entry_date: date,
    hold_days: int,
    blackout_days_before: int,
    blackout_days_after: int,
    alpaca_api_key: str = "",    # Deprecated: kept for backward compatibility, unused internally
    alpaca_secret_key: str = "",  # Deprecated: kept for backward compatibility, unused internally
    timeout_secs: int = 5,
) -> tuple[bool, Optional[date]]:
    """
    Check whether the symbol has an earnings announcement within the trading window.

    The blackout window extends from (entry_date - blackout_days_before) to
    (entry_date + hold_days + blackout_days_after).

    Args:
        symbol:                Ticker symbol (e.g. "TSLA")
        entry_date:            Proposed trade entry date
        hold_days:             max_hold_days from profile config
        blackout_days_before:  Skip if earnings within this many days BEFORE entry
        blackout_days_after:   Skip if earnings within this many days AFTER hold window end
        alpaca_api_key:        Unused (kept for backward compatibility)
        alpaca_secret_key:     Unused (kept for backward compatibility)
        timeout_secs:          Unused (kept for backward compatibility)

    Returns:
        (has_earnings: bool, earnings_date: Optional[date])
    """
    logger.info(
        "has_earnings_in_window | symbol=%s entry=%s hold=%d blackout_before=%d blackout_after=%d",
        symbol, entry_date, hold_days, blackout_days_before, blackout_days_after,
    )

    window_start = entry_date - timedelta(days=blackout_days_before)
    window_end = entry_date + timedelta(days=hold_days + blackout_days_after)

    try:
        earnings_dates = _get_earnings_dates(symbol, window_start, window_end)

        if earnings_dates:
            nearest = min(earnings_dates, key=lambda d: abs((d - entry_date).days))
            logger.info(
                "Earnings found for %s within window [%s, %s]: nearest=%s",
                symbol, window_start, window_end, nearest,
            )
            return True, nearest

        logger.info(
            "No earnings for %s in window [%s, %s]",
            symbol, window_start, window_end,
        )
        return False, None

    except Exception:
        logger.error("has_earnings_in_window failed for %s — allowing trade (fail open)",
                      symbol, exc_info=True)
        return False, None


def _get_earnings_dates(
    symbol: str,
    window_start: date,
    window_end: date,
) -> list[date]:
    """
    Fetch earnings announcement dates using yfinance.
    Returns list of dates within the window. Uses cache.
    """
    # Check cache
    now = time.time()
    if symbol in _cache:
        cached = _cache[symbol]
        if now - cached["fetched_at"] < _CACHE_TTL_SECONDS:
            return [d for d in cached["earnings_dates"]
                    if window_start <= d <= window_end]

    try:
        import yfinance as yf
    except ImportError:
        logger.warning(
            "yfinance not installed — earnings gate disabled. "
            "Install with: pip install yfinance"
        )
        _cache[symbol] = {"earnings_dates": [], "fetched_at": now}
        return []

    try:
        ticker = yf.Ticker(symbol)
        # get_earnings_dates returns upcoming and recent earnings dates
        raw_dates = ticker.get_earnings_dates(limit=8)

        if raw_dates is None or raw_dates.empty:
            logger.info("No earnings dates returned by yfinance for %s", symbol)
            _cache[symbol] = {"earnings_dates": [], "fetched_at": now}
            return []

        # raw_dates index is DatetimeIndex with earnings dates
        earnings_dates = [d.date() for d in raw_dates.index]

        _cache[symbol] = {
            "earnings_dates": earnings_dates,
            "fetched_at": now,
        }
        logger.info("Cached %d earnings dates for %s", len(earnings_dates), symbol)

        return [d for d in earnings_dates if window_start <= d <= window_end]

    except Exception as e:
        logger.warning("yfinance earnings fetch failed for %s: %s — fail open", symbol, e)
        _cache[symbol] = {"earnings_dates": [], "fetched_at": now}
        return []

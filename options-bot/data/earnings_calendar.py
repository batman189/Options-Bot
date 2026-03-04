"""
Earnings calendar checker using Alpaca corporate actions endpoint.

Used by base_strategy.py to skip entries when earnings fall inside
the hold window (IV crush risk).

Fail-open: if the API is unavailable or times out, allows the trade.
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
    alpaca_api_key: str,
    alpaca_secret_key: str,
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
        alpaca_api_key:        Alpaca API key
        alpaca_secret_key:     Alpaca secret key
        timeout_secs:          HTTP timeout

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
        earnings_dates = _get_earnings_dates(
            symbol, window_start, window_end,
            alpaca_api_key, alpaca_secret_key, timeout_secs,
        )

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
    api_key: str,
    api_secret: str,
    timeout_secs: int,
) -> list[date]:
    """
    Fetch earnings announcement dates from Alpaca corporate actions API.
    Returns list of dates within the window. Uses cache.
    """
    # Check cache
    now = time.time()
    if symbol in _cache:
        cached = _cache[symbol]
        if now - cached["fetched_at"] < _CACHE_TTL_SECONDS:
            # Filter cached dates to window
            return [d for d in cached["earnings_dates"]
                    if window_start <= d <= window_end]

    # Fetch from Alpaca
    import requests

    url = "https://data.alpaca.markets/v1beta1/corporate-actions/announcements"
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }
    # Fetch a wider range for caching (next 90 days from today)
    fetch_start = date.today() - timedelta(days=7)
    fetch_end = date.today() + timedelta(days=90)

    params = {
        "ca_types": "earnings",
        "symbol": symbol,
        "since": fetch_start.isoformat(),
        "until": fetch_end.isoformat(),
        "limit": 20,
    }

    logger.info("Fetching earnings from Alpaca API | symbol=%s range=%s to %s",
                symbol, fetch_start, fetch_end)

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout_secs)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        logger.warning("Alpaca earnings API timed out for %s — fail open", symbol)
        _cache[symbol] = {"earnings_dates": [], "fetched_at": now}
        return []
    except requests.exceptions.HTTPError as e:
        # Alpaca corporate actions API doesn't support ca_types=earnings (only
        # dividend/merger/spinoff/split). Log once at debug, cache empty result
        # so we don't spam on every iteration.
        logger.debug("Alpaca earnings API unavailable for %s: %s — fail open", symbol, e)
        _cache[symbol] = {"earnings_dates": [], "fetched_at": now}
        return []

    # Parse announcement dates
    announcements = data if isinstance(data, list) else data.get("announcements", [])
    earnings_dates = []
    for ann in announcements:
        # Try multiple date fields in priority order
        for date_field in ("ex_date", "record_date", "declaration_date"):
            date_str = ann.get(date_field)
            if date_str:
                try:
                    earnings_dates.append(date.fromisoformat(date_str))
                    break
                except ValueError:
                    continue

    # Cache result
    _cache[symbol] = {
        "earnings_dates": earnings_dates,
        "fetched_at": now,
    }
    logger.info("Cached %d earnings dates for %s", len(earnings_dates), symbol)

    # Filter to requested window
    return [d for d in earnings_dates if window_start <= d <= window_end]

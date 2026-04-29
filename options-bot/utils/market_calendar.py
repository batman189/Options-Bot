"""Trading-day arithmetic against the NYSE calendar.

Uses pandas-market-calendars for half-day and irregular-closure handling.
The calendar instance is cached lazily — one fetch per process lifetime
is sufficient because NYSE holidays change rarely and the underlying
library handles the long-tail dates correctly out of the box.

Public API:
    is_trading_day(d)          -> bool
    trading_days_between(s, e) -> int   (exclusive of both endpoints)
    trading_days_since(past)   -> int   (tz-aware datetimes only)

Half-days (e.g. day after Thanksgiving, Christmas Eve when applicable)
count as full trading days for cooldown purposes.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from functools import lru_cache

import pandas_market_calendars as mcal


@lru_cache(maxsize=1)
def _nyse():
    """Cached NYSE calendar instance (one per process)."""
    return mcal.get_calendar("NYSE")


def is_trading_day(d: date) -> bool:
    """True if NYSE is open on date d (regular session or half-day)."""
    cal = _nyse()
    schedule = cal.schedule(start_date=d.isoformat(), end_date=d.isoformat())
    return not schedule.empty


def trading_days_between(start: date, end: date) -> int:
    """Number of NYSE trading days strictly between start and end
    (exclusive of both endpoints).

    If start >= end, returns 0. Half-days count as full trading days.
    """
    if start >= end:
        return 0
    cal = _nyse()
    schedule = cal.schedule(start_date=start.isoformat(), end_date=end.isoformat())
    count = len(schedule)
    if is_trading_day(start):
        count -= 1
    if is_trading_day(end):
        count -= 1
    return max(count, 0)


def trading_days_since(past_dt: datetime, now: datetime | None = None) -> int:
    """Trading days elapsed strictly between past_dt and now (UTC).

    Both datetimes must be timezone-aware. Used for the same-symbol
    cooldown: a return value of 3 means 3 full NYSE trading days have
    completed since the past_dt date.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if past_dt.tzinfo is None or now.tzinfo is None:
        raise ValueError("Both datetimes must be timezone-aware")
    return trading_days_between(past_dt.date(), now.date())

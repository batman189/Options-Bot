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


def _schedule_window(start_date: date, days: int = 8):
    """Schedule rows from start_date through start_date + days, inclusive.

    8 days covers most weekend + holiday + buffer cases. mcal returns
    a DataFrame; iterate with `.iterrows()` and pull market_open /
    market_close as pd.Timestamp (tz-aware UTC).
    """
    from datetime import timedelta
    cal = _nyse()
    return cal.schedule(
        start_date=start_date.isoformat(),
        end_date=(start_date + timedelta(days=days)).isoformat(),
    )


def next_trading_open(from_dt: datetime) -> datetime:
    """Return the next NYSE trading session's open as a tz-aware
    datetime (UTC).

    If from_dt is before today's open, returns today's open. Otherwise
    returns the next trading day's open. Open is 09:30 ET (13:30 or
    14:30 UTC depending on DST). Half-days share the same 09:30 ET open;
    only the close shifts. pandas-market-calendars handles DST and
    irregular schedules.
    """
    if from_dt.tzinfo is None:
        raise ValueError("from_dt must be timezone-aware")
    schedule = _schedule_window(from_dt.date())
    for _, row in schedule.iterrows():
        open_t = row["market_open"].to_pydatetime()
        if from_dt < open_t:
            return open_t
    raise RuntimeError(
        f"No trading open found within window starting {from_dt.date()}"
    )


def current_or_next_trading_close(from_dt: datetime) -> datetime:
    """Return the closest trading session's close as a tz-aware datetime
    (UTC).

    If from_dt is during a trading session OR before today's open on a
    trading day, returns that session's close (i.e. the next close
    strictly after from_dt). If after close on a trading day, returns
    next trading day's close. Half-days return their early close
    (typically 13:00 ET / 18:00 UTC).
    """
    if from_dt.tzinfo is None:
        raise ValueError("from_dt must be timezone-aware")
    schedule = _schedule_window(from_dt.date())
    for _, row in schedule.iterrows():
        close_t = row["market_close"].to_pydatetime()
        if from_dt < close_t:
            return close_t
    raise RuntimeError(
        f"No trading close found within window starting {from_dt.date()}"
    )


def round_to_next_trading_minute(from_dt: datetime) -> datetime:
    """If from_dt falls within a trading session [open, close), return it
    unchanged. Otherwise return next_trading_open(from_dt).

    Used by outcome-window math: a 1h window from a 15:55 ET signal
    would naturally land at 16:55, which is outside RTH; this rolls
    forward to next open.
    """
    if from_dt.tzinfo is None:
        raise ValueError("from_dt must be timezone-aware")
    cal = _nyse()
    today = from_dt.date()
    schedule = cal.schedule(
        start_date=today.isoformat(), end_date=today.isoformat(),
    )
    if not schedule.empty:
        open_t = schedule.iloc[0]["market_open"].to_pydatetime()
        close_t = schedule.iloc[0]["market_close"].to_pydatetime()
        if open_t <= from_dt < close_t:
            return from_dt
    return next_trading_open(from_dt)

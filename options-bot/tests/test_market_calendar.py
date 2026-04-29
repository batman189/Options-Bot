"""Unit tests for utils.market_calendar.

Pure logic — pandas-market-calendars uses local data, no network.
Mirrors the pytest style of the other Phase 1a test files.

Run via:
    python -m pytest tests/test_market_calendar.py -v
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.market_calendar import (  # noqa: E402
    _nyse,
    is_trading_day,
    trading_days_between,
    trading_days_since,
)


# ─────────────────────────────────────────────────────────────────
# is_trading_day
# ─────────────────────────────────────────────────────────────────

def test_is_trading_day_regular_weekday():
    """2026-01-05 is a Monday — NYSE open."""
    assert is_trading_day(date(2026, 1, 5)) is True


def test_is_trading_day_weekend():
    """2026-01-04 is a Sunday — NYSE closed."""
    assert is_trading_day(date(2026, 1, 4)) is False


def test_is_trading_day_holiday():
    """2026-01-01 is New Year's Day — NYSE closed."""
    assert is_trading_day(date(2026, 1, 1)) is False


def test_is_trading_day_half_day_counts_as_open():
    """2025-11-28 is the day after Thanksgiving — half day,
    counts as a trading day for cooldown purposes."""
    assert is_trading_day(date(2025, 11, 28)) is True


# ─────────────────────────────────────────────────────────────────
# trading_days_between
# ─────────────────────────────────────────────────────────────────

def test_trading_days_between_same_date():
    assert trading_days_between(date(2026, 1, 5), date(2026, 1, 5)) == 0


def test_trading_days_between_start_after_end():
    assert trading_days_between(date(2026, 1, 6), date(2026, 1, 5)) == 0


def test_trading_days_between_consecutive_trading_days():
    """Mon -> Tue: both endpoints are trading days, exclusive of both -> 0."""
    assert trading_days_between(date(2026, 2, 2), date(2026, 2, 3)) == 0


def test_trading_days_between_mon_to_fri():
    """Mon 2026-02-02 -> Fri 2026-02-06: schedule has 5 trading days,
    minus the two endpoints = 3 (Tue, Wed, Thu)."""
    assert trading_days_between(date(2026, 2, 2), date(2026, 2, 6)) == 3


def test_trading_days_between_across_weekend():
    """Fri 2026-02-06 -> Mon 2026-02-09: schedule has 2 trading days
    (Fri + Mon), minus both endpoints = 0."""
    assert trading_days_between(date(2026, 2, 6), date(2026, 2, 9)) == 0


# ─────────────────────────────────────────────────────────────────
# trading_days_since
# ─────────────────────────────────────────────────────────────────

def test_trading_days_since_calendar_5_days_spans_weekend():
    """Past = Tue 2026-02-03 12:00 UTC, now = Sun 2026-02-08 12:00 UTC.
    Schedule(Feb 3 -> Feb 8) returns Tue/Wed/Thu/Fri = 4. Subtract 1 for
    Tue (trading), no subtract for Sun (closed) -> 3."""
    past = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
    assert trading_days_since(past, now) == 3


def test_trading_days_since_naive_past_raises():
    naive = datetime(2026, 2, 3, 12, 0)  # no tzinfo
    aware = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="timezone-aware"):
        trading_days_since(naive, aware)


def test_trading_days_since_naive_now_raises():
    aware = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 2, 8, 12, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        trading_days_since(aware, naive)


def test_trading_days_since_default_now_is_aware():
    """When now is omitted, the function defaults to datetime.now(timezone.utc),
    which is tz-aware. Pass any past tz-aware datetime and confirm no
    ValueError is raised."""
    past = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    # Should not raise
    result = trading_days_since(past)
    assert isinstance(result, int)
    assert result >= 0


# ─────────────────────────────────────────────────────────────────
# lru_cache on _nyse
# ─────────────────────────────────────────────────────────────────

def test_nyse_calendar_is_cached():
    """Two calls to _nyse() return the exact same calendar object."""
    a = _nyse()
    b = _nyse()
    assert a is b

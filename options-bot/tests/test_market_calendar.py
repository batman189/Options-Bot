"""Unit tests for utils.market_calendar.

Pure logic — pandas-market-calendars uses local data, no network.
Mirrors the pytest style of the other Phase 1a test files.

Run via:
    python -m pytest tests/test_market_calendar.py -v
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.market_calendar import (  # noqa: E402
    _nyse,
    current_or_next_trading_close,
    is_trading_day,
    next_trading_open,
    round_to_next_trading_minute,
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


# ─────────────────────────────────────────────────────────────────
# next_trading_open
# ─────────────────────────────────────────────────────────────────
#
# Reference dates (DST-aware UTC offsets):
#   May 15 2026 Fri 09:30 ET = 13:30 UTC
#   May 18 2026 Mon 09:30 ET = 13:30 UTC
#   2025-11-28 Black Friday (half-day): open 14:30 UTC, close 18:00 UTC


def test_next_open_from_pre_open_returns_today():
    """8am ET pre-market on a trading day → that day's 09:30 ET open."""
    pre = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)  # 8am ET
    expected = datetime(2026, 5, 15, 13, 30, tzinfo=timezone.utc)
    assert next_trading_open(pre) == expected


def test_next_open_during_rth_returns_next_day():
    """During RTH on Friday → next session is Monday."""
    rth = datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc)  # 10am ET Fri
    expected = datetime(2026, 5, 18, 13, 30, tzinfo=timezone.utc)
    assert next_trading_open(rth) == expected


def test_next_open_from_saturday_returns_monday():
    sat = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    expected = datetime(2026, 5, 18, 13, 30, tzinfo=timezone.utc)
    assert next_trading_open(sat) == expected


def test_next_open_from_holiday_returns_post_holiday():
    """New Year's Day 2026-01-01 (Thursday). Next open is Friday Jan 2."""
    ny = datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc)
    out = next_trading_open(ny)
    assert out.date() == date(2026, 1, 2)


def test_next_open_naive_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        next_trading_open(datetime(2026, 5, 15, 14, 0))


# ─────────────────────────────────────────────────────────────────
# current_or_next_trading_close
# ─────────────────────────────────────────────────────────────────


def test_close_during_rth_returns_today_close():
    """14:00 ET on a Friday → that day's 16:00 ET close."""
    mid = datetime(2026, 5, 15, 18, 0, tzinfo=timezone.utc)  # 14:00 ET
    expected = datetime(2026, 5, 15, 20, 0, tzinfo=timezone.utc)
    assert current_or_next_trading_close(mid) == expected


def test_close_after_close_returns_next_day_close():
    """17:00 ET Friday → Monday's 16:00 ET close."""
    after = datetime(2026, 5, 15, 21, 0, tzinfo=timezone.utc)  # 17:00 ET
    expected = datetime(2026, 5, 18, 20, 0, tzinfo=timezone.utc)
    assert current_or_next_trading_close(after) == expected


def test_close_pre_open_returns_today_close():
    """8am ET pre-market on a trading day → that day's 16:00 ET close
    (the next close strictly > from_dt)."""
    pre = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)  # 8am ET
    expected = datetime(2026, 5, 15, 20, 0, tzinfo=timezone.utc)
    assert current_or_next_trading_close(pre) == expected


def test_close_from_half_day_post_close_rolls_to_next_day():
    """14:00 ET on Black Friday 2025-11-28 (half-day, closed at 13:00 ET).
    14:00 is past close → next trading day's close (Dec 1 16:00 ET)."""
    post = datetime(2025, 11, 28, 19, 0, tzinfo=timezone.utc)  # 14:00 ET
    expected_date = date(2025, 12, 1)
    assert current_or_next_trading_close(post).date() == expected_date


def test_close_naive_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        current_or_next_trading_close(datetime(2026, 5, 15, 18, 0))


# ─────────────────────────────────────────────────────────────────
# round_to_next_trading_minute
# ─────────────────────────────────────────────────────────────────


def test_round_during_rth_unchanged():
    rth = datetime(2026, 5, 15, 16, 0, tzinfo=timezone.utc)  # 12pm ET
    assert round_to_next_trading_minute(rth) == rth


def test_round_post_close_rolls_forward():
    """15:55 ET + 1h = 16:55 ET, post-close → rolls to next open."""
    sig = datetime(2026, 5, 15, 19, 55, tzinfo=timezone.utc)
    one_hour_later = sig + timedelta(hours=1)  # 20:55 UTC = 16:55 ET
    expected = datetime(2026, 5, 18, 13, 30, tzinfo=timezone.utc)
    assert round_to_next_trading_minute(one_hour_later) == expected


def test_round_pre_open_rolls_to_today_open():
    """8am ET pre-market → rolls to today's 09:30 ET open."""
    pre = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    expected = datetime(2026, 5, 15, 13, 30, tzinfo=timezone.utc)
    assert round_to_next_trading_minute(pre) == expected


def test_round_on_weekend_rolls_to_monday():
    sat = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    expected = datetime(2026, 5, 18, 13, 30, tzinfo=timezone.utc)
    assert round_to_next_trading_minute(sat) == expected


def test_round_at_exact_close_rolls_forward():
    """Predicate is open <= dt < close, so dt == close rolls forward."""
    close_t = datetime(2026, 5, 15, 20, 0, tzinfo=timezone.utc)
    expected = datetime(2026, 5, 18, 13, 30, tzinfo=timezone.utc)
    assert round_to_next_trading_minute(close_t) == expected


def test_round_naive_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        round_to_next_trading_minute(datetime(2026, 5, 15, 14, 0))

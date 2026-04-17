"""Expiration selection logic per profile type.
From architecture doc:
  Momentum: 0DTE if before 12 PM ET, next expiration if after. Never 0DTE after 1 PM.
  Mean Reversion: minimum 5 DTE, prefer 7-10 DTE.
  Catalyst: 0DTE or next expiration depending on when catalyst occurs.
"""

from datetime import date, datetime, timedelta
from typing import Optional


def _next_trading_day(from_date: date) -> date:
    """Next weekday after from_date."""
    d = from_date + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _next_friday(from_date: date) -> date:
    """Next Friday on or after from_date (weekly option expirations)."""
    d = from_date
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d


def _et_hour() -> int:
    """Current hour in Eastern Time."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).hour
    except Exception:
        return (datetime.utcnow() - timedelta(hours=4)).hour


def select_expiration(profile_name: str) -> Optional[str]:
    """Return expiration date as 'YYYY-MM-DD' based on profile rules."""
    today = date.today()
    hour = _et_hour()

    if profile_name == "momentum":
        if hour < 12:
            return today.isoformat()       # 0DTE before noon
        else:
            return _next_trading_day(today).isoformat()  # Never 0DTE after 1 PM

    elif profile_name == "mean_reversion":
        # Minimum 5 DTE, prefer 7-10 DTE. Use next weekly Friday.
        # Explicit floor: if the computed Friday is < 5 DTE, skip to the following week.
        target = today + timedelta(days=7)
        friday = _next_friday(target)
        dte = (friday - today).days
        if dte < 5:
            friday = _next_friday(friday + timedelta(days=1))
        return friday.isoformat()

    elif profile_name == "catalyst":
        if hour < 14:
            return today.isoformat()       # 0DTE if before 2 PM
        else:
            return _next_trading_day(today).isoformat()

    elif profile_name == "scalp_0dte":
        return today.isoformat()           # Always 0DTE

    elif profile_name == "swing":
        # 2-5 DTE: target next Friday at least 2 days away
        friday = _next_friday(today)
        dte = (friday - today).days
        if dte < 2:
            friday = _next_friday(friday + timedelta(days=1))
        return friday.isoformat()

    return (today + timedelta(days=7)).isoformat()

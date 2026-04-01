"""EOD force-close check. Extracted from base_strategy.py, kept as-is.

Force closes at 3:45 PM ET ONLY if the position's expiration is TODAY.
Positions expiring on future dates are not affected. This means mean
reversion trades with 7-10 DTE expirations hold overnight normally.
"""

from datetime import date, datetime, timedelta

EOD_CUTOFF_HOUR = 15
EOD_CUTOFF_MINUTE = 45


def should_force_close_eod(expiration: date, now_et: datetime) -> bool:
    """Force close at 3:45 PM ET ONLY if position expires TODAY.
    Positions expiring on future dates are not affected.

    Args:
        expiration: The option contract's expiration date.
        now_et: Current datetime in Eastern Time.

    Returns:
        True if position should be force-closed now.
    """
    # Only applies to positions expiring today
    if expiration != now_et.date():
        return False

    # Check if past 3:45 PM ET
    return (now_et.hour > EOD_CUTOFF_HOUR or
            (now_et.hour == EOD_CUTOFF_HOUR and
             now_et.minute >= EOD_CUTOFF_MINUTE))


def get_et_now() -> datetime:
    """Get current datetime in Eastern Time."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.utcnow() - timedelta(hours=4)

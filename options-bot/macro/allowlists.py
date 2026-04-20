"""Post-validation gates applied in code, not by the LLM.

Rule 4 in play — we don't trust LLM output. Even after Pydantic validation
passes, every row goes through these gates before it gets written:

  - impact_level=HIGH is downgraded to MEDIUM unless the event_type is in
    HIGH_IMPACT_EVENT_TYPES.
  - EARNINGS only keeps HIGH for symbols we trade (TRADABLE_SYMBOLS).
  - Rows with blank or malformed source_url are dropped.
  - Events outside [now, now+7d] are dropped (future skew or past leakage).
  - Catalysts for symbols outside TRADABLE_SYMBOLS are dropped.
    Market-wide events (symbol="*") are always allowed.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from config import HIGH_IMPACT_EVENT_TYPES, TRADABLE_SYMBOLS
from macro.schema import EventItem, CatalystItem


ET = ZoneInfo("America/New_York")
MAX_EVENT_HORIZON_DAYS = 7


def normalize_event(item: EventItem) -> Optional[dict]:
    """Apply gates to an EventItem. Return an insert-ready dict or None if dropped.

    Dropped cases:
      - Event time outside [now, now+7d]
      - EARNINGS for a symbol not in TRADABLE_SYMBOLS (no way to use it)

    Downgraded cases:
      - HIGH impact on an event_type not in HIGH_IMPACT_EVENT_TYPES → MEDIUM
      - HIGH EARNINGS on a non-tradable symbol → MEDIUM (but not dropped if
        symbol is "*" or tradable; this branch only hits when we decide the
        event is market-adjacent not trade-targeted)
    """
    # Timezone sanity: event_time_et must be aware. Pydantic keeps tzinfo if
    # the ISO8601 string included an offset, but we enforce.
    event_time = item.event_time_et
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=ET)
    event_time_et = event_time.astimezone(ET)

    now_et = datetime.now(ET)
    horizon = now_et + timedelta(days=MAX_EVENT_HORIZON_DAYS)
    if event_time_et < now_et or event_time_et > horizon:
        return None

    symbol = item.symbol
    if symbol != "*" and symbol not in TRADABLE_SYMBOLS:
        # Only tradable symbols or market-wide events
        if item.event_type != "EARNINGS":
            # Non-earnings for a non-tradable symbol — treat as market-wide signal
            # only if explicitly tagged "*"; otherwise drop.
            return None
        return None  # Earnings on untracked symbols contribute nothing

    # Impact downgrade
    impact = item.impact_level
    if impact == "HIGH" and item.event_type not in HIGH_IMPACT_EVENT_TYPES:
        impact = "MEDIUM"

    # Source URL already validated by HttpUrl; cast to str for SQLite insert
    source_url = str(item.source_url)
    if not source_url:
        return None

    return {
        "symbol": symbol,
        "event_type": item.event_type,
        "event_time_et": event_time_et.isoformat(),
        "impact_level": impact,
        "source_url": source_url,
    }


def normalize_catalyst(item: CatalystItem, fetched_at_utc: datetime,
                       expiry_hours: int) -> Optional[dict]:
    """Apply gates to a CatalystItem. Return insert-ready dict or None.

    Dropped cases:
      - Symbol not in TRADABLE_SYMBOLS and not "*"
      - Severity outside [0, 1] (already enforced by Pydantic but belt-and-suspenders)
      - Blank summary (already enforced; redundant check)
    """
    symbol = item.symbol
    if symbol != "*" and symbol not in TRADABLE_SYMBOLS:
        return None

    if not (0.0 <= item.severity <= 1.0):
        return None

    summary = item.summary.strip()[:200]
    if not summary:
        return None

    source_url = str(item.source_url)
    if not source_url:
        return None

    expires_at = (fetched_at_utc + timedelta(hours=expiry_hours)).astimezone(timezone.utc)

    return {
        "symbol": symbol,
        "catalyst_type": item.catalyst_type.strip()[:50],
        "direction": item.direction,
        "severity": round(float(item.severity), 4),
        "summary": summary,
        "source_url": source_url,
        "expires_at": expires_at.isoformat(),
    }

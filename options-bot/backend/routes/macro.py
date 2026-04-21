"""Macro state API — read-only endpoint for the System page UI panel.

Mirrors the shape of backend/routes/system.py:get_recent_errors — single
GET returning the full current macro picture. No writes; the worker is
the only writer to the macro_* tables.

Never returns 5xx on missing/empty state. The UI shows what it has and a
"Stale" banner when the regime row is too old or absent.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import aiosqlite
from fastapi import APIRouter, Depends
from zoneinfo import ZoneInfo

from backend.database import get_db
from backend.schemas import (
    MacroCatalystResponse,
    MacroEventResponse,
    MacroRegimeResponse,
    MacroStateResponse,
)
from config import (
    MACRO_DAILY_CALL_CAP,
    MACRO_REGIME_STALE_MINUTES,
)

logger = logging.getLogger("options-bot.routes.macro")
router = APIRouter(prefix="/api/macro", tags=["Macro"])

ET = ZoneInfo("America/New_York")


def _parse_event_time_et(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(ET)


def _parse_utc(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/state", response_model=MacroStateResponse)
async def get_macro_state(db: aiosqlite.Connection = Depends(get_db)):
    """Return the current macro picture: upcoming events (next 24h),
    active catalysts (unexpired), current regime, and today's API usage.

    Never raises — missing rows / stale data are surfaced to the UI, not
    converted to 5xx.
    """
    logger.debug("GET /api/macro/state")
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)

    # Upcoming events — within 24 hours ahead (include a 5-min past window
    # so in-flight events are still shown with negative minutes_until).
    # Filter on event_time_utc so DST offset changes can't corrupt the
    # lexicographic ISO8601 comparison.
    event_horizon_utc = now_utc + timedelta(hours=24)
    event_min_utc = now_utc - timedelta(minutes=5)
    events: list[MacroEventResponse] = []
    try:
        cursor = await db.execute(
            """SELECT symbol, event_type, event_time_et, impact_level,
                      source_url, fetched_at
               FROM macro_events
               WHERE event_time_utc IS NOT NULL
                 AND event_time_utc >= ? AND event_time_utc <= ?
               ORDER BY event_time_utc ASC""",
            (event_min_utc.isoformat(), event_horizon_utc.isoformat()),
        )
        rows = await cursor.fetchall()
        for row in rows:
            try:
                event_time_et = _parse_event_time_et(row["event_time_et"])
            except Exception:
                continue
            delta_min = int((event_time_et - now_et).total_seconds() // 60)
            events.append(MacroEventResponse(
                symbol=row["symbol"],
                event_type=row["event_type"],
                event_time_et=event_time_et.isoformat(),
                impact_level=row["impact_level"],
                source_url=row["source_url"],
                fetched_at=row["fetched_at"],
                minutes_until=delta_min,
            ))
    except Exception as e:
        logger.warning(f"macro_events query failed (returning []): {e}")

    # Catalysts — unexpired only
    catalysts: list[MacroCatalystResponse] = []
    try:
        cursor = await db.execute(
            """SELECT symbol, catalyst_type, direction, severity, summary,
                      source_url, expires_at, fetched_at
               FROM macro_catalysts
               WHERE expires_at >= ?
               ORDER BY fetched_at DESC""",
            (now_utc.isoformat(),),
        )
        rows = await cursor.fetchall()
        for row in rows:
            catalysts.append(MacroCatalystResponse(
                symbol=row["symbol"],
                catalyst_type=row["catalyst_type"],
                direction=row["direction"],
                severity=row["severity"],
                summary=row["summary"],
                source_url=row["source_url"],
                expires_at=row["expires_at"],
                fetched_at=row["fetched_at"],
            ))
    except Exception as e:
        logger.warning(f"macro_catalysts query failed (returning []): {e}")

    # Regime — singleton row
    regime: MacroRegimeResponse | None = None
    try:
        cursor = await db.execute(
            """SELECT risk_tone, vix_context, major_themes_json, fetched_at
               FROM macro_regime WHERE id='current' LIMIT 1"""
        )
        row = await cursor.fetchone()
        if row is not None:
            try:
                fetched_at = _parse_utc(row["fetched_at"])
                age_min = (now_utc - fetched_at).total_seconds() / 60
                is_stale = age_min > MACRO_REGIME_STALE_MINUTES
            except Exception:
                is_stale = True
            try:
                themes = json.loads(row["major_themes_json"] or "[]")
                if not isinstance(themes, list):
                    themes = []
            except Exception:
                themes = []
            regime = MacroRegimeResponse(
                risk_tone=row["risk_tone"],
                vix_context=row["vix_context"],
                major_themes=[str(t)[:100] for t in themes][:10],
                fetched_at=row["fetched_at"],
                is_stale=is_stale,
            )
    except Exception as e:
        logger.warning(f"macro_regime query failed (returning None): {e}")

    # Today's API usage for cost breaker display
    api_calls_today = 0
    try:
        today = now_et.date().isoformat()
        cursor = await db.execute(
            "SELECT call_count FROM macro_api_usage WHERE date_et = ?",
            (today,),
        )
        row = await cursor.fetchone()
        if row is not None:
            api_calls_today = int(row["call_count"])
    except Exception as e:
        logger.warning(f"macro_api_usage query failed: {e}")

    return MacroStateResponse(
        events=events,
        catalysts=catalysts,
        regime=regime,
        api_calls_today=api_calls_today,
        api_cap=MACRO_DAILY_CALL_CAP,
    )

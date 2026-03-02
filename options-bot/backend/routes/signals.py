"""
Signal decision log endpoints.
Phase 4.5: Makes every trading iteration visible from the UI.
Matches PROJECT_ARCHITECTURE.md Section 5b — Signal Log.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
import aiosqlite

from backend.database import get_db
from backend.schemas import SignalLogEntry

logger = logging.getLogger("options-bot.routes.signals")
router = APIRouter(prefix="/api/signals", tags=["Signals"])


def _row_to_signal(row: aiosqlite.Row) -> SignalLogEntry:
    """Convert a database row to a SignalLogEntry."""
    return SignalLogEntry(
        id=row["id"],
        profile_id=row["profile_id"],
        timestamp=row["timestamp"],
        symbol=row["symbol"],
        underlying_price=row["underlying_price"],
        predicted_return=row["predicted_return"],
        predictor_type=row["predictor_type"],
        step_stopped_at=row["step_stopped_at"],
        stop_reason=row["stop_reason"],
        entered=bool(row["entered"]),
        trade_id=row["trade_id"],
    )


# -------------------------------------------------------------------------
# GET /api/signals/{profile_id} — Recent signal log entries
# -------------------------------------------------------------------------
@router.get("/{profile_id}", response_model=list[SignalLogEntry])
async def get_signal_logs(
    profile_id: str,
    limit: int = Query(50, ge=1, le=500, description="Number of entries to return"),
    since: Optional[str] = Query(None, description="ISO datetime — only return entries after this time"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Return recent signal log entries for a profile.
    Default: last 50 entries, newest first.
    Optional: ?limit=N&since=<ISO datetime>
    """
    logger.info(f"GET /api/signals/{profile_id} (limit={limit}, since={since})")

    # Verify profile exists
    cursor = await db.execute("SELECT id FROM profiles WHERE id = ?", (profile_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    where = "WHERE profile_id = ?"
    params: list = [profile_id]

    if since:
        where += " AND timestamp > ?"
        params.append(since)

    params.append(limit)
    cursor = await db.execute(
        f"SELECT * FROM signal_logs {where} ORDER BY timestamp DESC LIMIT ?",
        params,
    )
    rows = await cursor.fetchall()
    return [_row_to_signal(row) for row in rows]

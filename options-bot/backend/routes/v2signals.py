"""V2 Signal logs API — scorer evaluations with full factor breakdown."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
import aiosqlite

from backend.database import get_db

logger = logging.getLogger("options-bot.routes.v2signals")
router = APIRouter(prefix="/api/v2signals", tags=["V2 Signals"])


class V2SignalLogEntry(BaseModel):
    id: int
    timestamp: str
    profile_name: str
    symbol: str
    setup_type: Optional[str] = None
    setup_score: Optional[float] = None
    confidence_score: Optional[float] = None
    raw_score: Optional[float] = None
    regime: Optional[str] = None
    regime_reason: Optional[str] = None
    time_of_day: Optional[str] = None
    signal_clarity: Optional[float] = None
    regime_fit: Optional[float] = None
    ivr: Optional[float] = None
    institutional_flow: Optional[float] = None
    historical_perf: Optional[float] = None
    sentiment: Optional[float] = None
    time_of_day_score: Optional[float] = None
    threshold_label: Optional[str] = None
    entered: bool = False
    trade_id: Optional[str] = None
    block_reason: Optional[str] = None


def _row_to_entry(row: aiosqlite.Row) -> V2SignalLogEntry:
    return V2SignalLogEntry(
        id=row["id"],
        timestamp=row["timestamp"],
        profile_name=row["profile_name"],
        symbol=row["symbol"],
        setup_type=row["setup_type"],
        setup_score=row["setup_score"],
        confidence_score=row["confidence_score"],
        raw_score=row["raw_score"],
        regime=row["regime"],
        regime_reason=row["regime_reason"],
        time_of_day=row["time_of_day"],
        signal_clarity=row["signal_clarity"],
        regime_fit=row["regime_fit"],
        ivr=row["ivr"],
        institutional_flow=row["institutional_flow"],
        historical_perf=row["historical_perf"],
        sentiment=row["sentiment"],
        time_of_day_score=row["time_of_day_score"],
        threshold_label=row["threshold_label"],
        entered=bool(row["entered"]),
        trade_id=row["trade_id"],
        block_reason=row["block_reason"],
    )


@router.get("", response_model=list[V2SignalLogEntry])
async def list_v2_signals(
    profile_name: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    entered: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List V2 signal log entries with optional filters."""
    where = "WHERE 1=1"
    params: list = []
    if profile_name:
        where += " AND profile_name = ?"
        params.append(profile_name)
    if symbol:
        where += " AND symbol = ?"
        params.append(symbol)
    if entered is not None:
        where += " AND entered = ?"
        params.append(entered)

    params.append(limit)
    cursor = await db.execute(
        f"SELECT * FROM v2_signal_logs {where} ORDER BY timestamp DESC LIMIT ?",
        params,
    )
    rows = await cursor.fetchall()
    return [_row_to_entry(row) for row in rows]

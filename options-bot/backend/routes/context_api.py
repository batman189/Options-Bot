"""Market context API endpoint — reads regime from context_snapshots table."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import aiosqlite

from backend.database import get_db

logger = logging.getLogger("options-bot.routes.context")
router = APIRouter(prefix="/api/context", tags=["Context"])


class RegimeResponse(BaseModel):
    regime: Optional[str] = None
    time_of_day: Optional[str] = None
    timestamp: Optional[str] = None
    spy_30min_move_pct: Optional[float] = None
    spy_60min_range_pct: Optional[float] = None
    spy_30min_reversals: Optional[int] = None
    spy_volume_ratio: Optional[float] = None
    vix_level: Optional[float] = None
    vix_intraday_change_pct: Optional[float] = None
    regime_reason: Optional[str] = None
    available: bool = False


@router.get("/regime", response_model=RegimeResponse)
async def get_current_regime(db: aiosqlite.Connection = Depends(get_db)):
    """Read the most recent context snapshot from the database.
    Returns available=false when no snapshots exist."""
    try:
        cursor = await db.execute(
            """SELECT * FROM context_snapshots
               WHERE symbol = 'SPY'
               ORDER BY timestamp DESC LIMIT 1"""
        )
        row = await cursor.fetchone()

        if not row:
            return RegimeResponse(available=False)

        return RegimeResponse(
            regime=row["regime"],
            time_of_day=row["time_of_day"],
            timestamp=row["timestamp"],
            spy_30min_move_pct=row["spy_30min_move_pct"],
            spy_60min_range_pct=row["spy_60min_range_pct"],
            spy_30min_reversals=row["spy_30min_reversals"],
            spy_volume_ratio=row["spy_volume_ratio"],
            vix_level=row["vix_level"],
            vix_intraday_change_pct=row["vix_intraday_change_pct"],
            regime_reason=row["regime_reason"],
            available=True,
        )

    except Exception as e:
        logger.error(f"get_current_regime failed: {e}", exc_info=True)
        return RegimeResponse(available=False)

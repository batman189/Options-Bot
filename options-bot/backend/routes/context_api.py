"""Market context API endpoint — current regime and driving values."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("options-bot.routes.context")
router = APIRouter(prefix="/api/context", tags=["Context"])

# Module-level context instance (set by app startup)
_context_instance = None


def set_context(context):
    """Called by app startup to provide MarketContext reference."""
    global _context_instance
    _context_instance = context


class RegimeResponse(BaseModel):
    regime: str
    time_of_day: str
    timestamp: str
    spy_30min_move_pct: float
    spy_60min_range_pct: float
    spy_30min_reversals: int
    spy_volume_ratio: float
    vix_level: float
    vix_intraday_change_pct: float
    regime_reason: str


@router.get("/regime", response_model=RegimeResponse)
async def get_current_regime():
    """Return current market context snapshot with all driving values."""
    try:
        if _context_instance is None:
            raise HTTPException(
                status_code=503,
                detail="Market context engine not initialized. Bot may not be running.",
            )

        snap = _context_instance.get_snapshot()
        return RegimeResponse(
            regime=snap.regime.value,
            time_of_day=snap.time_of_day.value,
            timestamp=snap.timestamp,
            spy_30min_move_pct=snap.spy_30min_move_pct,
            spy_60min_range_pct=snap.spy_60min_range_pct,
            spy_30min_reversals=snap.spy_30min_reversals,
            spy_volume_ratio=snap.spy_volume_ratio,
            vix_level=snap.vix_level,
            vix_intraday_change_pct=snap.vix_intraday_change_pct,
            regime_reason=snap.regime_reason,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_current_regime failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Context unavailable: {str(e)}")

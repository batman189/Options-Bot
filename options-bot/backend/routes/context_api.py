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
async def get_current_regime():
    """Return current market context snapshot with all driving values.
    Returns available=false with null fields when no trading is active."""
    try:
        if _context_instance is None:
            return RegimeResponse(available=False)

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
            available=True,
        )

    except Exception as e:
        logger.error(f"get_current_regime failed: {e}", exc_info=True)
        return RegimeResponse(available=False)

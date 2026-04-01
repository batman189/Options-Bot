"""Scanner API endpoint — current scanner output."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("options-bot.routes.scanner")
router = APIRouter(prefix="/api/scanner", tags=["Scanner"])

# Module-level scanner instance (set by app startup)
_scanner_instance = None
_context_instance = None


def set_scanner(scanner, context):
    """Called by app startup to provide scanner + context references."""
    global _scanner_instance, _context_instance
    _scanner_instance = scanner
    _context_instance = context


class SetupDetail(BaseModel):
    setup_type: str
    score: float
    direction: str
    reason: str


class SymbolScan(BaseModel):
    symbol: str
    best_setup: str
    best_score: float
    setups: list[SetupDetail]


class ScannerResponse(BaseModel):
    timestamp: Optional[str]
    regime: Optional[str]
    active_setups: list[SymbolScan]


@router.get("/active", response_model=ScannerResponse)
async def get_active_scanner():
    """Return current scanner output with all setup evaluations."""
    try:
        if _scanner_instance is None:
            return ScannerResponse(timestamp=None, regime=None, active_setups=[])

        results = _scanner_instance.scan()
        snap = _context_instance.get_snapshot() if _context_instance else None

        symbols = []
        for r in results:
            setups = []
            for s in r.setups:
                setups.append(SetupDetail(
                    setup_type=s.setup_type, score=round(s.score, 3),
                    direction=s.direction, reason=s.reason[:200],
                ))
            symbols.append(SymbolScan(
                symbol=r.symbol, best_setup=r.best_setup or "none",
                best_score=round(r.best_score, 3), setups=setups,
            ))

        return ScannerResponse(
            timestamp=snap.timestamp if snap else None,
            regime=snap.regime.value if snap else None,
            active_setups=symbols,
        )

    except Exception as e:
        logger.error(f"get_active_scanner failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scanner unavailable: {str(e)}")

"""Scanner API endpoint — reads from scanner_snapshots table."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import aiosqlite

from backend.database import get_db

logger = logging.getLogger("options-bot.routes.scanner")
router = APIRouter(prefix="/api/scanner", tags=["Scanner"])


class SetupDetail(BaseModel):
    setup_type: str
    score: float
    direction: str = ""
    reason: str = ""


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
async def get_active_scanner(db: aiosqlite.Connection = Depends(get_db)):
    """Read the most recent scanner snapshot per symbol from the database."""
    try:
        # Get distinct symbols from the most recent scan cycle
        cursor = await db.execute(
            """SELECT DISTINCT symbol FROM scanner_snapshots
               WHERE timestamp = (SELECT MAX(timestamp) FROM scanner_snapshots)"""
        )
        symbols_rows = await cursor.fetchall()

        if not symbols_rows:
            return ScannerResponse(timestamp=None, regime=None, active_setups=[])

        scans = []
        timestamp = None
        regime = None

        for sym_row in symbols_rows:
            symbol = sym_row["symbol"]
            cursor = await db.execute(
                """SELECT * FROM scanner_snapshots
                   WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1""",
                (symbol,),
            )
            row = await cursor.fetchone()
            if not row:
                continue

            if timestamp is None:
                timestamp = row["timestamp"]
                regime = row["regime"]

            setups = []
            for setup_type, score_col, reason_col in [
                ("momentum", "momentum_score", "momentum_reason"),
                ("mean_reversion", "mean_reversion_score", "mean_reversion_reason"),
                ("compression_breakout", "compression_score", "compression_reason"),
                ("catalyst", "catalyst_score", "catalyst_reason"),
            ]:
                score = row[score_col]
                if score is not None:
                    setups.append(SetupDetail(
                        setup_type=setup_type,
                        score=round(score, 3),
                        reason=(row[reason_col] or "")[:200],
                    ))

            scans.append(SymbolScan(
                symbol=symbol,
                best_setup=row["best_setup"] or "none",
                best_score=round(row["best_score"], 3) if row["best_score"] else 0.0,
                setups=setups,
            ))

        return ScannerResponse(
            timestamp=timestamp,
            regime=regime,
            active_setups=scans,
        )

    except Exception as e:
        logger.error(f"get_active_scanner failed: {e}", exc_info=True)
        return ScannerResponse(timestamp=None, regime=None, active_setups=[])

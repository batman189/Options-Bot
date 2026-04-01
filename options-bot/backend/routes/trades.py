"""
Trade history endpoints.
Phase 1: List, get single, active positions — all work against SQLite.
Phase 2: Stats + export fully functional.
Matches PROJECT_ARCHITECTURE.md Section 5b — Trades.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import aiosqlite
import csv
import io

from backend.database import get_db
from backend.schemas import TradeResponse, TradeStats

logger = logging.getLogger("options-bot.routes.trades")
router = APIRouter(prefix="/api/trades", tags=["Trades"])


def _row_to_trade(row: aiosqlite.Row) -> TradeResponse:
    """Convert a database row to a TradeResponse."""
    return TradeResponse(
        id=row["id"],
        profile_id=row["profile_id"],
        symbol=row["symbol"],
        direction=row["direction"],
        strike=row["strike"],
        expiration=row["expiration"],
        quantity=row["quantity"],
        entry_price=row["entry_price"],
        entry_date=row["entry_date"],
        exit_price=row["exit_price"],
        exit_date=row["exit_date"],
        pnl_dollars=row["pnl_dollars"],
        pnl_pct=row["pnl_pct"],
        predicted_return=row["entry_predicted_return"],
        ev_at_entry=row["entry_ev_pct"],
        entry_model_type=row["entry_model_type"],
        exit_reason=row["exit_reason"],
        hold_days=row["hold_days"],
        unrealized_pnl=row["unrealized_pnl"] if "unrealized_pnl" in row.keys() else None,
        unrealized_pnl_pct=row["unrealized_pnl_pct"] if "unrealized_pnl_pct" in row.keys() else None,
        status=row["status"],
        was_day_trade=bool(row["was_day_trade"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        setup_type=row["setup_type"] if "setup_type" in row.keys() else None,
        confidence_score=row["confidence_score"] if "confidence_score" in row.keys() else None,
        hold_minutes=row["hold_minutes"] if "hold_minutes" in row.keys() else None,
    )


# -------------------------------------------------------------------------
# GET /api/trades/active — List open positions (MUST be before /{id})
# -------------------------------------------------------------------------
@router.get("/active", response_model=list[TradeResponse])
async def list_active_trades(db: aiosqlite.Connection = Depends(get_db)):
    """List all open positions across all profiles."""
    logger.info("GET /api/trades/active")
    cursor = await db.execute(
        "SELECT * FROM trades WHERE status = 'open' ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [_row_to_trade(row) for row in rows]


# -------------------------------------------------------------------------
# GET /api/trades/stats — Aggregated P&L stats (Phase 2 stub)
# -------------------------------------------------------------------------
@router.get("/stats", response_model=TradeStats)
async def get_trade_stats(
    profile_id: Optional[str] = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Aggregated trade statistics. Works against real data in trades table."""
    logger.info(f"GET /api/trades/stats (profile_id={profile_id})")

    where = "WHERE 1=1"
    params = []
    if profile_id:
        where += " AND profile_id = ?"
        params.append(profile_id)

    cursor = await db.execute(f"SELECT * FROM trades {where}", params)
    rows = await cursor.fetchall()

    total = len(rows)
    open_trades = sum(1 for r in rows if r["status"] == "open")
    closed = [r for r in rows if r["status"] == "closed"]
    closed_count = len(closed)

    wins = [r for r in closed if r["pnl_pct"] is not None and r["pnl_pct"] > 0]
    losses = [r for r in closed if r["pnl_pct"] is not None and r["pnl_pct"] <= 0]

    total_pnl = sum(r["pnl_dollars"] for r in closed if r["pnl_dollars"] is not None)
    pnl_pcts = [r["pnl_pct"] for r in closed if r["pnl_pct"] is not None]
    hold_days_list = [r["hold_days"] for r in closed if r["hold_days"] is not None]

    return TradeStats(
        total_trades=total,
        open_trades=open_trades,
        closed_trades=closed_count,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=len(wins) / closed_count if closed_count > 0 else None,
        total_pnl_dollars=total_pnl,
        avg_pnl_pct=sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else None,
        best_trade_pct=max(pnl_pcts) if pnl_pcts else None,
        worst_trade_pct=min(pnl_pcts) if pnl_pcts else None,
        avg_hold_days=sum(hold_days_list) / len(hold_days_list) if hold_days_list else None,
    )


# -------------------------------------------------------------------------
# GET /api/trades/export — CSV export (Phase 2 stub)
# -------------------------------------------------------------------------
@router.get("/export")
async def export_trades(
    profile_id: Optional[str] = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Export trades as CSV."""
    logger.info(f"GET /api/trades/export (profile_id={profile_id})")

    where = "WHERE 1=1"
    params = []
    if profile_id:
        where += " AND profile_id = ?"
        params.append(profile_id)

    cursor = await db.execute(
        f"SELECT * FROM trades {where} ORDER BY created_at DESC", params
    )
    rows = await cursor.fetchall()

    output = io.StringIO()
    if rows:
        columns = rows[0].keys()
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trades_export.csv"},
    )


# -------------------------------------------------------------------------
# GET /api/trades — List trades (filterable)
# -------------------------------------------------------------------------
@router.get("", response_model=list[TradeResponse])
async def list_trades(
    profile_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    setup_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List trades with optional filters."""
    logger.info(f"GET /api/trades (profile={profile_id}, status={status}, symbol={symbol}, setup_type={setup_type})")

    where = "WHERE 1=1"
    params = []
    if profile_id:
        where += " AND profile_id = ?"
        params.append(profile_id)
    if status:
        where += " AND status = ?"
        params.append(status)
    if symbol:
        where += " AND symbol = ?"
        params.append(symbol)
    if setup_type:
        where += " AND setup_type = ?"
        params.append(setup_type)

    params.append(limit)
    cursor = await db.execute(
        f"SELECT * FROM trades {where} ORDER BY created_at DESC LIMIT ?", params
    )
    rows = await cursor.fetchall()
    return [_row_to_trade(row) for row in rows]


# -------------------------------------------------------------------------
# GET /api/trades/{id} — Get single trade
# -------------------------------------------------------------------------
@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single trade with full context."""
    logger.info(f"GET /api/trades/{trade_id}")
    cursor = await db.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    return _row_to_trade(row)

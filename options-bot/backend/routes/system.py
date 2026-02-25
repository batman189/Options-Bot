"""
System health and status endpoints.
Phase 2: errors endpoint reads from training_logs table.
Matches PROJECT_ARCHITECTURE.md Section 5b — System.
"""

import time
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
import aiosqlite

from backend.database import get_db
from backend.schemas import SystemStatus, HealthCheck, PDTStatus, ErrorLogEntry

logger = logging.getLogger("options-bot.routes.system")
router = APIRouter(prefix="/api/system", tags=["System"])

_startup_time = time.time()


# -------------------------------------------------------------------------
# GET /api/system/health — Simple health check
# -------------------------------------------------------------------------
@router.get("/health", response_model=HealthCheck)
async def health_check():
    """Simple health check — always returns OK if the server is running."""
    return HealthCheck(
        status="ok",
        timestamp=datetime.utcnow().isoformat(),
        version="0.1.0",
    )


# -------------------------------------------------------------------------
# GET /api/system/status — All connection statuses
# -------------------------------------------------------------------------
@router.get("/status", response_model=SystemStatus)
async def get_system_status(db: aiosqlite.Connection = Depends(get_db)):
    """Full system status including all connection states."""
    logger.info("GET /api/system/status")

    alpaca_connected = False
    theta_connected = False
    db_connected = False
    portfolio_value = 0.0

    # Test DB connection
    try:
        await db.execute("SELECT 1")
        db_connected = True
    except Exception:
        pass

    # Test Alpaca connection
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER

        if ALPACA_API_KEY and ALPACA_API_KEY != "your_key_here":
            from alpaca.trading.client import TradingClient
            client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)
            account = client.get_account()
            alpaca_connected = True
            portfolio_value = float(account.equity)
    except Exception as e:
        logger.warning(f"Alpaca connection check failed: {e}")

    # Test Theta connection
    try:
        import requests as _requests
        from config import THETA_BASE_URL_V3
        resp = _requests.get(
            f"{THETA_BASE_URL_V3}/stock/list/symbols", timeout=3
        )
        theta_connected = resp.status_code == 200
    except Exception:
        theta_connected = False

    uptime = int(time.time() - _startup_time)

    # Get most recent error from training_logs
    last_error = None
    try:
        cursor = await db.execute(
            """SELECT message FROM training_logs
               WHERE level = 'error'
               ORDER BY timestamp DESC LIMIT 1"""
        )
        row = await cursor.fetchone()
        if row:
            last_error = row["message"][:200]
    except Exception:
        pass

    # Count active profiles and open positions
    active_profiles = 0
    total_open_positions = 0
    try:
        cursor = await db.execute("SELECT COUNT(*) FROM profiles WHERE status IN ('ready', 'training')")
        active_profiles = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM trades WHERE status = 'open'")
        total_open_positions = (await cursor.fetchone())[0]
    except Exception:
        pass

    # PDT info
    pdt_day_trades = 0
    try:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM trades
               WHERE was_day_trade = 1
               AND exit_date >= date('now', '-7 days')
               AND status = 'closed'"""
        )
        pdt_day_trades = (await cursor.fetchone())[0]
    except Exception:
        pass

    pdt_limit = 3 if portfolio_value < 25000 else 999999
    alpaca_subscription = "algo_trader_plus" if alpaca_connected else "unknown"

    return SystemStatus(
        alpaca_connected=alpaca_connected,
        alpaca_subscription=alpaca_subscription,
        theta_terminal_connected=theta_connected,
        active_profiles=active_profiles,
        total_open_positions=total_open_positions,
        pdt_day_trades_5d=pdt_day_trades,
        pdt_limit=pdt_limit,
        portfolio_value=portfolio_value,
        uptime_seconds=uptime,
        last_error=last_error,
    )


# -------------------------------------------------------------------------
# GET /api/system/pdt — PDT day trade count
# -------------------------------------------------------------------------
@router.get("/pdt", response_model=PDTStatus)
async def get_pdt_status(db: aiosqlite.Connection = Depends(get_db)):
    """Get current PDT day trade count from SQLite trades table."""
    logger.info("GET /api/system/pdt")

    cursor = await db.execute(
        """SELECT COUNT(*) FROM trades
           WHERE was_day_trade = 1
           AND exit_date >= date('now', '-7 days')
           AND status = 'closed'"""
    )
    pdt_count = (await cursor.fetchone())[0]

    equity = 0.0
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER

        if ALPACA_API_KEY and ALPACA_API_KEY != "your_key_here":
            from alpaca.trading.client import TradingClient
            client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)
            account = client.get_account()
            equity = float(account.equity)
    except Exception:
        pass

    limit = 3 if equity < 25000 else 999999
    remaining = max(0, limit - pdt_count)

    return PDTStatus(
        day_trades_5d=pdt_count,
        limit=limit,
        remaining=remaining,
        equity=equity,
        is_restricted=equity < 25000,
    )


# -------------------------------------------------------------------------
# GET /api/system/errors — Recent error log
# -------------------------------------------------------------------------
@router.get("/errors", response_model=list[ErrorLogEntry])
async def get_recent_errors(
    limit: int = Query(default=50, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Get recent error and warning entries from the training_logs table.
    Returns entries with level 'error' or 'warning', newest first.
    Returns empty list if no errors have been logged yet.
    """
    logger.info(f"GET /api/system/errors (limit={limit})")

    try:
        cursor = await db.execute(
            """SELECT tl.timestamp, tl.level, tl.message, m.profile_id as source
               FROM training_logs tl
               LEFT JOIN models m ON tl.model_id = m.id
               WHERE tl.level IN ('error', 'warning')
               ORDER BY tl.timestamp DESC
               LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()

        return [
            ErrorLogEntry(
                timestamp=row["timestamp"],
                level=row["level"],
                message=row["message"],
                source=f"training/profile={row['source']}" if row["source"] else "training",
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"get_recent_errors: DB query failed: {e}", exc_info=True)
        return []

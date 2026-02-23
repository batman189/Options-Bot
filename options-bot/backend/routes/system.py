"""
System health and status endpoints.
Phase 1: health + status + pdt all functional.
Phase 2: errors fully functional.
Matches PROJECT_ARCHITECTURE.md Section 5b — System.
"""

import time
import logging
from datetime import datetime

from fastapi import APIRouter, Depends
import aiosqlite

from backend.database import get_db
from backend.schemas import SystemStatus, HealthCheck, PDTStatus, ErrorLogEntry

logger = logging.getLogger("options-bot.routes.system")
router = APIRouter(prefix="/api/system", tags=["System"])

# Track startup time for uptime calculation
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

    # Count active profiles
    cursor = await db.execute("SELECT COUNT(*) FROM profiles WHERE status = 'active'")
    active_profiles = (await cursor.fetchone())[0]

    # Count open positions
    cursor = await db.execute("SELECT COUNT(*) FROM trades WHERE status = 'open'")
    open_positions = (await cursor.fetchone())[0]

    # PDT tracking: count day trades in last 5 business days
    cursor = await db.execute(
        """SELECT COUNT(*) FROM trades
           WHERE was_day_trade = 1
           AND exit_date >= date('now', '-7 days')
           AND status = 'closed'"""
    )
    pdt_count = (await cursor.fetchone())[0]

    # Test Alpaca connection
    alpaca_connected = False
    alpaca_sub = "unknown"
    portfolio_value = 0.0
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
            alpaca_sub = "algo_trader_plus"  # We require this subscription
            portfolio_value = float(account.equity)
    except Exception as e:
        logger.warning(f"Alpaca connection check failed: {e}")

    # Test Theta Terminal connection
    theta_connected = False
    try:
        import requests
        from config import THETA_BASE_URL_V3
        resp = requests.get(f"{THETA_BASE_URL_V3}/stock/list/symbols", timeout=5)
        theta_connected = resp.status_code == 200
    except Exception:
        pass

    # Get last error from system_state
    cursor = await db.execute(
        "SELECT value FROM system_state WHERE key = 'last_error'"
    )
    error_row = await cursor.fetchone()
    last_error = error_row[0] if error_row else None

    pdt_limit = 3 if portfolio_value < 25000 else 999999

    return SystemStatus(
        alpaca_connected=alpaca_connected,
        alpaca_subscription=alpaca_sub,
        theta_terminal_connected=theta_connected,
        active_profiles=active_profiles,
        total_open_positions=open_positions,
        pdt_day_trades_5d=pdt_count,
        pdt_limit=pdt_limit,
        portfolio_value=portfolio_value,
        uptime_seconds=int(time.time() - _startup_time),
        last_error=last_error,
    )


# -------------------------------------------------------------------------
# GET /api/system/pdt — Current PDT day trade count
# -------------------------------------------------------------------------
@router.get("/pdt", response_model=PDTStatus)
async def get_pdt_status(db: aiosqlite.Connection = Depends(get_db)):
    """Get Pattern Day Trader status."""
    logger.info("GET /api/system/pdt")

    cursor = await db.execute(
        """SELECT COUNT(*) FROM trades
           WHERE was_day_trade = 1
           AND exit_date >= date('now', '-7 days')
           AND status = 'closed'"""
    )
    pdt_count = (await cursor.fetchone())[0]

    # Get equity
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
# GET /api/system/errors — Recent error log (Phase 2 stub)
# -------------------------------------------------------------------------
@router.get("/errors", response_model=list[ErrorLogEntry])
async def get_recent_errors(
    limit: int = 50,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get recent errors from system state. Phase 2 — reads from logs when available."""
    logger.info(f"GET /api/system/errors (limit={limit})")

    # For now, return empty list. Phase 2 will populate from log files / system_state
    return []

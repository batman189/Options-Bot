"""
System health and status endpoints.
Phase 2: errors endpoint reads from training_logs table.
Matches PROJECT_ARCHITECTURE.md Section 5b — System.
"""

import asyncio
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
        version="0.2.0",
    )


# -------------------------------------------------------------------------
# GET /api/system/status — All connection statuses
# -------------------------------------------------------------------------
@router.get("/status", response_model=SystemStatus)
async def get_system_status(db: aiosqlite.Connection = Depends(get_db)):
    """
    Return combined system status across all subsystems.
    check_errors accumulates any exceptions from individual checks.
    A non-empty check_errors means the status values may be defaults, not confirmed.
    """
    logger.info("GET /api/system/status")

    check_errors: list[str] = []

    alpaca_connected = False
    alpaca_subscription = "unknown"
    theta_terminal_connected = False
    portfolio_value = 0.0

    # Count active profiles
    active_profiles = 0
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM profiles WHERE status = 'active'"
        )
        active_profiles = (await cursor.fetchone())[0]
    except Exception as e:
        msg = f"Active profiles check failed: {type(e).__name__}: {e}"
        logger.warning(msg)
        check_errors.append(msg)

    # Count open positions
    total_open_positions = 0
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM trades WHERE status = 'open'"
        )
        total_open_positions = (await cursor.fetchone())[0]
    except Exception as e:
        msg = f"Open positions check failed: {type(e).__name__}: {e}"
        logger.warning(msg)
        check_errors.append(msg)

    # PDT count: day trades in last 7 calendar days (covers 5 business days)
    pdt_day_trades_5d = 0
    try:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM trades
               WHERE was_day_trade = 1
               AND entry_date >= date('now', '-7 days')
               AND status = 'closed'"""
        )
        pdt_day_trades_5d = (await cursor.fetchone())[0]
    except Exception as e:
        msg = f"PDT count check failed: {type(e).__name__}: {e}"
        logger.warning(msg)
        check_errors.append(msg)

    # Test Alpaca connection (run in thread to avoid blocking async loop)
    def _check_alpaca():
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER
        if ALPACA_API_KEY and ALPACA_API_KEY != "your_key_here":
            from alpaca.trading.client import TradingClient
            client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)
            account = client.get_account()
            return True, "algo_trader_plus", float(account.equity)
        return False, "unknown", 0.0

    try:
        alpaca_connected, alpaca_subscription, portfolio_value = await asyncio.to_thread(_check_alpaca)
    except Exception as e:
        msg = f"Alpaca check failed: {type(e).__name__}: {e}"
        logger.warning(msg)
        check_errors.append(msg)

    # Test Theta Terminal connection (run in thread to avoid blocking async loop)
    def _check_theta():
        import requests as _requests
        from config import THETA_BASE_URL_V3
        resp = _requests.get(f"{THETA_BASE_URL_V3}/stock/list/symbols", timeout=3)
        return resp.status_code == 200

    try:
        theta_terminal_connected = await asyncio.to_thread(_check_theta)
    except Exception as e:
        msg = f"Theta Terminal check failed: {type(e).__name__}: {e}"
        logger.warning(msg)
        check_errors.append(msg)

    pdt_limit = 3 if portfolio_value < 25000 else 999999
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
    except Exception as e:
        msg = f"Last error check failed: {type(e).__name__}: {e}"
        logger.warning(msg)
        check_errors.append(msg)

    if check_errors:
        logger.warning(
            f"System status completed with {len(check_errors)} check error(s): "
            + "; ".join(check_errors)
        )

    return SystemStatus(
        alpaca_connected=alpaca_connected,
        alpaca_subscription=alpaca_subscription,
        theta_terminal_connected=theta_terminal_connected,
        active_profiles=active_profiles,
        total_open_positions=total_open_positions,
        pdt_day_trades_5d=pdt_day_trades_5d,
        pdt_limit=pdt_limit,
        portfolio_value=portfolio_value,
        uptime_seconds=uptime,
        last_error=last_error,
        check_errors=check_errors,
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
        def _get_equity():
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER
            if ALPACA_API_KEY and ALPACA_API_KEY != "your_key_here":
                from alpaca.trading.client import TradingClient
                client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)
                account = client.get_account()
                return float(account.equity)
            return 0.0
        equity = await asyncio.to_thread(_get_equity)
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
            """SELECT tl.timestamp, tl.level, tl.message,
                      tl.model_id,
                      COALESCE(tl.profile_id, m.profile_id) as profile_id
               FROM training_logs tl
               LEFT JOIN models m ON tl.model_id = m.id
               WHERE tl.level IN ('error', 'warning')
               ORDER BY tl.timestamp DESC
               LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            mid = row["model_id"]
            pid = row["profile_id"]
            if mid == "live":
                source = "live"
            elif pid:
                source = f"training/profile={pid}"
            else:
                source = "training"
            results.append(
                ErrorLogEntry(
                    timestamp=row["timestamp"],
                    level=row["level"],
                    message=row["message"],
                    source=source,
                )
            )
        return results
    except Exception as e:
        logger.error(f"get_recent_errors: DB query failed: {e}", exc_info=True)
        return []

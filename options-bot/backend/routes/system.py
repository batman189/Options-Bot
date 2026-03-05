"""
System health and status endpoints.
Phase 2: errors endpoint reads from training_logs table.
Matches PROJECT_ARCHITECTURE.md Section 5b — System.
"""

import asyncio
import time
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
import aiosqlite

from backend.database import get_db
from backend.schemas import SystemStatus, HealthCheck, PDTStatus, ErrorLogEntry, ModelHealthEntry, ModelHealthResponse, TrainingQueueStatus

logger = logging.getLogger("options-bot.routes.system")
router = APIRouter(prefix="/api/system", tags=["System"])

_startup_time = time.time()


def _read_circuit_states(profile_ids: list[str]) -> dict:
    """Read circuit breaker state files written by trading subprocesses."""
    import json
    from config import LOGS_DIR
    states = {}
    for pid in profile_ids:
        state_file = LOGS_DIR / f"circuit_state_{pid}.json"
        try:
            if state_file.exists():
                data = json.loads(state_file.read_text())
                states[pid] = data
        except Exception:
            pass  # Stale or missing file — not an error
    return states


# -------------------------------------------------------------------------
# GET /api/system/health — Simple health check
# -------------------------------------------------------------------------
@router.get("/health", response_model=HealthCheck)
async def health_check():
    """Simple health check — always returns OK if the server is running."""
    return HealthCheck(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
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
               AND exit_date >= date('now', '-7 days')
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

    # Read circuit breaker state files from running trading subprocesses
    circuit_breaker_states = {}
    try:
        cursor = await db.execute("SELECT id FROM profiles WHERE status IN ('active', 'ready')")
        profile_rows = await cursor.fetchall()
        profile_ids = [r["id"] for r in profile_rows]
        if profile_ids:
            circuit_breaker_states = _read_circuit_states(profile_ids)
    except Exception as e:
        msg = f"Circuit state read failed: {type(e).__name__}: {e}"
        logger.warning(msg)
        check_errors.append(msg)

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
        circuit_breaker_states=circuit_breaker_states,
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


# -------------------------------------------------------------------------
# GET /api/system/model-health — Model health monitoring
# -------------------------------------------------------------------------
@router.get("/model-health", response_model=ModelHealthResponse)
async def get_model_health(db: aiosqlite.Connection = Depends(get_db)):
    """
    Get model health status for all profiles.
    Combines:
      - Rolling prediction accuracy from system_state (written by trading strategies)
      - Model age from models table
      - Profile status from profiles table
    """
    import json as _json
    from config import MODEL_STALE_THRESHOLD_DAYS

    logger.info("GET /api/system/model-health")

    entries = []
    any_degraded = False
    any_stale = False

    # Get all profiles with their current model
    cursor = await db.execute(
        """SELECT p.id, p.name, p.preset, p.status,
                  m.model_type, m.training_completed_at, m.status as model_status
           FROM profiles p
           LEFT JOIN models m ON p.model_id = m.id
           ORDER BY p.name"""
    )
    profiles = await cursor.fetchall()

    for profile in profiles:
        profile_id = profile["id"]
        profile_name = profile["name"]
        model_type = profile["model_type"] or "none"
        trained_at = profile["training_completed_at"]

        # Calculate model age
        model_age_days = None
        is_stale = False
        if trained_at:
            try:
                trained_dt = datetime.fromisoformat(trained_at)
                model_age_days = (datetime.now(timezone.utc) - trained_dt).days
                is_stale = model_age_days > MODEL_STALE_THRESHOLD_DAYS
            except (ValueError, TypeError):
                pass

        # Get live health stats from system_state (written by the trading strategy)
        health_data = None
        try:
            cursor2 = await db.execute(
                "SELECT value, updated_at FROM system_state WHERE key = ?",
                (f"model_health_{profile_id}",),
            )
            row = await cursor2.fetchone()
            if row:
                health_data = _json.loads(row["value"])
        except Exception as e:
            logger.warning(f"Failed to read model health for {profile_id}: {e}")

        # Build entry
        if health_data:
            rolling_acc = health_data.get("rolling_accuracy")
            status = health_data.get("status", "unknown")
            message = health_data.get("message", "")
            total_preds = health_data.get("total_predictions", 0)
            correct_preds = health_data.get("correct_predictions", 0)
            updated_at = health_data.get("updated_at")
        else:
            rolling_acc = None
            total_preds = 0
            correct_preds = 0
            updated_at = None

            if profile["model_status"] == "ready":
                status = "no_data"
                message = "Model trained but no live predictions recorded yet"
            elif profile["status"] == "created":
                status = "no_data"
                message = "No model trained"
            else:
                status = "no_data"
                message = "No health data available"

        # Override status if model is stale
        if is_stale and status not in ("degraded",):
            status = "stale"
            message = f"Model is {model_age_days} days old (threshold: {MODEL_STALE_THRESHOLD_DAYS} days). {message}"
            any_stale = True

        if status == "degraded":
            any_degraded = True

        entries.append(ModelHealthEntry(
            profile_id=profile_id,
            profile_name=profile_name,
            model_type=model_type,
            rolling_accuracy=rolling_acc,
            total_predictions=total_preds,
            correct_predictions=correct_preds,
            status=status,
            message=message,
            model_age_days=model_age_days,
            updated_at=updated_at,
        ))

    # Build summary
    healthy_count = sum(1 for e in entries if e.status == "healthy")
    warning_count = sum(1 for e in entries if e.status in ("warning", "stale"))
    degraded_count = sum(1 for e in entries if e.status == "degraded")
    no_data_count = sum(1 for e in entries if e.status in ("no_data", "insufficient_data"))

    parts = []
    if healthy_count:
        parts.append(f"{healthy_count} healthy")
    if warning_count:
        parts.append(f"{warning_count} warning")
    if degraded_count:
        parts.append(f"{degraded_count} degraded")
    if no_data_count:
        parts.append(f"{no_data_count} no data")
    summary = ", ".join(parts) if parts else "No profiles"

    return ModelHealthResponse(
        profiles=entries,
        any_degraded=any_degraded,
        any_stale=any_stale,
        summary=summary,
    )


# -------------------------------------------------------------------------
# GET /api/system/training-queue — Training queue depth
# -------------------------------------------------------------------------
@router.get("/training-queue", response_model=TrainingQueueStatus)
async def get_training_queue_status(db: aiosqlite.Connection = Depends(get_db)):
    """Get the number of pending training samples in the feedback queue."""
    from config import TRAINING_QUEUE_MIN_SAMPLES

    logger.info("GET /api/system/training-queue")

    pending_count = 0
    oldest_pending_at = None

    try:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM training_queue WHERE consumed = 0"
        )
        pending_count = (await cursor.fetchone())[0]

        if pending_count > 0:
            cursor = await db.execute(
                "SELECT MIN(queued_at) FROM training_queue WHERE consumed = 0"
            )
            row = await cursor.fetchone()
            oldest_pending_at = row[0] if row else None
    except Exception as e:
        logger.warning(f"Training queue query failed: {e}")

    return TrainingQueueStatus(
        pending_count=pending_count,
        min_samples_for_retrain=TRAINING_QUEUE_MIN_SAMPLES,
        ready_for_retrain=pending_count >= TRAINING_QUEUE_MIN_SAMPLES,
        oldest_pending_at=oldest_pending_at,
    )

"""
FastAPI application — entry point for the backend.
Phase 2: Backtest endpoints wired to real implementation.
Registers all route modules, initializes database on startup.
Swagger docs available at /docs.
"""

import json
import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import aiosqlite

from backend.database import init_db, get_db
from backend.routes import profiles, models, trades, system
from backend.schemas import BacktestRequest, BacktestResult

logger = logging.getLogger("options-bot.backend")

# Tracks profile IDs with an active backtest job
_active_backtests: set = set()
_active_backtests_lock = threading.Lock()


# =============================================================================
# Backtest background job
# =============================================================================

def _store_backtest_result(profile_id: str, result_dict: dict):
    """Store backtest result in system_state table synchronously."""
    import asyncio
    import aiosqlite as _aiosqlite

    async def _save():
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from config import DB_PATH
            async with _aiosqlite.connect(str(DB_PATH)) as db:
                now = datetime.utcnow().isoformat()
                await db.execute(
                    """INSERT OR REPLACE INTO system_state (key, value, updated_at)
                       VALUES (?, ?, ?)""",
                    (f"backtest_{profile_id}", json.dumps(result_dict), now),
                )
                await db.commit()
                logger.info(f"_store_backtest_result: stored for profile={profile_id}")
        except Exception as e:
            logger.error(f"_store_backtest_result: failed: {e}", exc_info=True)

    try:
        asyncio.run(_save())
    except Exception as e:
        logger.error(f"_store_backtest_result: asyncio.run failed: {e}")


def _backtest_job(
    profile_id: str,
    model_path: str,
    symbol: str,
    preset: str,
    start_date: str,
    end_date: str,
    budget: float,
):
    """
    Background thread: run Lumibot backtest and store results.
    Requires ThetaData Terminal running at localhost:25503.
    """
    logger.info(
        f"_backtest_job: starting profile={profile_id} "
        f"symbol={symbol} {start_date}→{end_date} budget={budget}"
    )

    # Store "running" status immediately
    _store_backtest_result(profile_id, {
        "profile_id": profile_id,
        "status": "running",
        "start_date": start_date,
        "end_date": end_date,
        "message": "Backtest in progress. This may take 5–30 minutes.",
    })

    try:
        from datetime import datetime as _datetime
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.backtest import run_backtest

        start_dt = _datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = _datetime.strptime(end_date, "%Y-%m-%d")

        result = run_backtest(
            model_path=model_path,
            symbol=symbol,
            preset=preset,
            start_date=start_dt,
            end_date=end_dt,
            budget=budget,
        )

        # Extract metrics from Lumibot result dict
        total_trades = None
        sharpe = None
        max_dd = None
        total_return = None
        win_rate = None

        if isinstance(result, dict):
            # Lumibot result keys vary by version — try common field names
            total_trades = (
                result.get("Total Trades") or
                result.get("total_trades") or
                result.get("Trades")
            )
            sharpe = (
                result.get("Sharpe Ratio") or
                result.get("sharpe_ratio") or
                result.get("Sharpe")
            )
            max_dd = (
                result.get("Max Drawdown") or
                result.get("max_drawdown") or
                result.get("Max Drawdown [%]")
            )
            total_return = (
                result.get("Total Return") or
                result.get("total_return") or
                result.get("Total Return [%]")
            )
            win_rate = (
                result.get("Win Rate") or
                result.get("win_rate") or
                result.get("Win Rate [%]")
            )

            # Convert percentages if stored as decimals
            if max_dd is not None and abs(float(max_dd)) <= 1.0:
                max_dd = float(max_dd) * 100
            if total_return is not None and abs(float(total_return)) <= 1.0:
                total_return = float(total_return) * 100
            if win_rate is not None and abs(float(win_rate)) <= 1.0:
                win_rate = float(win_rate) * 100

        completed_result = {
            "profile_id": profile_id,
            "status": "completed",
            "start_date": start_date,
            "end_date": end_date,
            "total_trades": int(total_trades) if total_trades is not None else None,
            "sharpe_ratio": float(sharpe) if sharpe is not None else None,
            "max_drawdown_pct": float(max_dd) if max_dd is not None else None,
            "total_return_pct": float(total_return) if total_return is not None else None,
            "win_rate": float(win_rate) if win_rate is not None else None,
            "message": "Backtest completed successfully.",
        }
        _store_backtest_result(profile_id, completed_result)
        logger.info(
            f"_backtest_job: completed profile={profile_id} "
            f"trades={total_trades} sharpe={sharpe} dd={max_dd}"
        )

    except Exception as e:
        logger.error(f"_backtest_job: failed for profile={profile_id}: {e}", exc_info=True)
        _store_backtest_result(profile_id, {
            "profile_id": profile_id,
            "status": "failed",
            "start_date": start_date,
            "end_date": end_date,
            "message": f"Backtest failed: {str(e)[:300]}",
        })
    finally:
        with _active_backtests_lock:
            _active_backtests.discard(profile_id)
        logger.info(f"_backtest_job: job slot released for profile={profile_id}")


# =============================================================================
# App setup
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Backend starting up...")
    await init_db()
    logger.info("Database initialized. Backend ready.")
    yield
    logger.info("Backend shutting down.")


app = FastAPI(
    title="Options Bot API",
    description=(
        "ML-driven options trading bot API. "
        "Manages profiles, models, trades, and system status. "
        "See PROJECT_ARCHITECTURE.md Section 5 for the full API contract."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles.router)
app.include_router(models.router)
app.include_router(trades.router)
app.include_router(system.router)


# =============================================================================
# Backtest routes
# =============================================================================

backtest_router = APIRouter(prefix="/api/backtest", tags=["Backtesting"])


@backtest_router.post("/{profile_id}", response_model=BacktestResult)
async def run_backtest_endpoint(
    profile_id: str,
    body: BacktestRequest,
):
    """
    Trigger a backtest for a profile.
    Requires ThetaData Terminal running at localhost:25503.
    Runs in a background thread — returns immediately with status='running'.
    Poll GET /api/backtest/{profile_id}/results for completion.
    """
    logger.info(
        f"POST /api/backtest/{profile_id} "
        f"start={body.start_date} end={body.end_date} capital={body.initial_capital}"
    )

    # Validate profile exists and has a model
    from config import DB_PATH
    import aiosqlite as _aiosqlite

    profile_row = None
    model_path = None

    async with _aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = _aiosqlite.Row
        cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
        profile_row = await cursor.fetchone()
        if not profile_row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

        if not profile_row["model_id"]:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Profile {profile_id} has no trained model. Run /api/models/{profile_id}/train first.",
            )

        # Get model file path
        cursor2 = await db.execute(
            "SELECT file_path FROM models WHERE id = ?", (profile_row["model_id"],)
        )
        model_row = await cursor2.fetchone()
        if model_row:
            model_path = model_row["file_path"]

    if not model_path:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Model file path not found for profile {profile_id}.",
        )

    # Check for duplicate backtest
    with _active_backtests_lock:
        if profile_id in _active_backtests:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail=f"Backtest already running for profile {profile_id}. Poll /results.",
            )
        _active_backtests.add(profile_id)

    import json as _json
    symbols = _json.loads(profile_row["symbols"])
    symbol = symbols[0] if symbols else "TSLA"
    preset = profile_row["preset"]

    thread = threading.Thread(
        target=_backtest_job,
        args=(
            profile_id, model_path, symbol, preset,
            body.start_date, body.end_date, body.initial_capital,
        ),
        daemon=True,
        name=f"backtest-{profile_id[:8]}",
    )
    thread.start()

    return BacktestResult(
        profile_id=profile_id,
        status="running",
        start_date=body.start_date,
        end_date=body.end_date,
        message=(
            f"Backtest started for {symbol} ({preset}). "
            f"Requires ThetaData Terminal running at localhost:25503. "
            f"Poll GET /api/backtest/{profile_id}/results for completion."
        ),
    )


@backtest_router.get("/{profile_id}/results", response_model=BacktestResult)
async def get_backtest_results(profile_id: str):
    """
    Get backtest results for a profile.
    Returns the most recent backtest status and metrics.
    Returns status='not_run' if no backtest has been triggered yet.
    """
    logger.info(f"GET /api/backtest/{profile_id}/results")

    from config import DB_PATH
    import aiosqlite as _aiosqlite

    async with _aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = _aiosqlite.Row
        cursor = await db.execute(
            "SELECT value FROM system_state WHERE key = ?",
            (f"backtest_{profile_id}",),
        )
        row = await cursor.fetchone()

    if not row:
        return BacktestResult(
            profile_id=profile_id,
            status="not_run",
            message="No backtest has been run for this profile. POST /api/backtest/{id} to start.",
        )

    try:
        data = json.loads(row["value"])
        return BacktestResult(
            profile_id=data.get("profile_id", profile_id),
            status=data.get("status", "unknown"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            total_trades=data.get("total_trades"),
            sharpe_ratio=data.get("sharpe_ratio"),
            max_drawdown_pct=data.get("max_drawdown_pct"),
            total_return_pct=data.get("total_return_pct"),
            win_rate=data.get("win_rate"),
            message=data.get("message"),
        )
    except Exception as e:
        logger.error(f"get_backtest_results: failed to parse stored result: {e}")
        return BacktestResult(
            profile_id=profile_id,
            status="error",
            message=f"Failed to parse stored result: {e}",
        )


app.include_router(backtest_router)

"""
FastAPI application — entry point for the backend.
Phase 2: Backtest endpoints wired to real implementation.
Registers all route modules, initializes database on startup.
Swagger docs available at /docs.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import aiosqlite

from backend import outcome_resolver
from backend.database import init_db
from backend.routes import profiles, trades, system, trading
from config import VERSION

logger = logging.getLogger("options-bot.backend")







# =============================================================================
# App setup
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Backend starting up...")
    await init_db()

    # Restore any trading processes that survived a backend restart
    from config import DB_PATH
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        await trading.restore_process_registry(db)

        # Clean stale profiles: marked 'active' or 'error' in DB but no running process
        cursor = await db.execute(
            "SELECT id, name, status FROM profiles WHERE status IN ('active', 'error')"
        )
        stale_rows = await cursor.fetchall()
        for row in stale_rows:
            pid_entry = trading._processes.get(row["id"])
            if not pid_entry:
                logger.warning(
                    f"Stale profile '{row['name']}' ({row['id']}) — "
                    f"marked {row['status']} but no running process. Setting to 'ready'."
                )
                await db.execute(
                    "UPDATE profiles SET status = 'ready' WHERE id = ?",
                    (row["id"],),
                )
        await db.commit()

    # BUG-002 fix: clean up orphaned model records pointing to missing files
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, profile_id, file_path, status FROM models")
        model_rows = await cursor.fetchall()
        orphaned = 0
        for mrow in model_rows:
            fp = mrow["file_path"]
            if fp and not Path(fp).exists():
                await db.execute(
                    "UPDATE models SET status = 'orphaned' WHERE id = ?",
                    (mrow["id"],),
                )
                logger.warning(
                    f"Orphaned model {mrow['id'][:8]} — file missing: {fp}"
                )
                orphaned += 1
        if orphaned:
            await db.commit()
            logger.info(f"Marked {orphaned} orphaned model record(s)")

    # Start the process watchdog
    trading.start_watchdog()

    # Spawn the macro/catalyst awareness worker. Skipped if MACRO_ENABLED is
    # False or PERPLEXITY_API_KEY is unset — trading continues in either case.
    try:
        trading.spawn_macro_worker()
    except Exception as e:
        logger.error(f"Macro worker spawn raised (trading unaffected): {e}")

    # Start the outcome resolver loop. Falls back to no-op if
    # UnifiedDataClient health check fails — outcomes accumulate
    # until the next restart with a healthy client.
    try:
        outcome_resolver.start_outcome_resolver_loop()
    except Exception as e:
        logger.error(
            f"outcome resolver start raised (FastAPI continues): {e}",
        )

    logger.info("Database initialized. Backend ready.")
    yield

    # Stop the outcome resolver loop before the watchdog (no actual
    # ordering dependency, but matches lifespan-symmetry conventions).
    outcome_resolver.stop_outcome_resolver_loop()

    # Shutdown: stop the watchdog
    trading.stop_watchdog()
    logger.info("Backend shutting down.")


app = FastAPI(
    title="Options Bot API",
    description=(
        "ML-driven options trading bot API. "
        "Manages profiles, models, trades, and system status. "
        "See PROJECT_ARCHITECTURE.md Section 5 for the full API contract."
    ),
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:8000", "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles.router)
app.include_router(trades.router)
app.include_router(system.router)
app.include_router(trading.router)

# V2 endpoints
from backend.routes.learning import router as learning_router
from backend.routes.scanner_api import router as scanner_router
from backend.routes.context_api import router as context_router
from backend.routes.v2signals import router as v2signals_router
from backend.routes.macro import router as macro_router
from backend.routes.meta import router as meta_router   # Prompt 27 Commit A
from backend.routes.execution import router as execution_router   # Shadow Mode
app.include_router(learning_router)
app.include_router(scanner_router)
app.include_router(context_router)
app.include_router(v2signals_router)
app.include_router(macro_router)
app.include_router(meta_router)
app.include_router(execution_router)


# =============================================================================
# Static file serving — serve the built React frontend from ui/dist/
# =============================================================================

_UI_DIST = Path(__file__).parent.parent / "ui" / "dist"

if _UI_DIST.is_dir():
    # Serve static assets (JS, CSS, images) at /assets/
    app.mount(
        "/assets",
        StaticFiles(directory=str(_UI_DIST / "assets")),
        name="static-assets",
    )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve index.html for all non-API routes (SPA client-side routing)."""
        # Try to serve the exact file first (e.g. favicon.ico)
        file_path = _UI_DIST / full_path
        if full_path and file_path.is_file():
            return FileResponse(str(file_path))
        # Fall back to index.html for SPA routing — no-cache so browser
        # always picks up new builds (hashed JS/CSS assets are long-cached by Vite)
        return FileResponse(
            str(_UI_DIST / "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
else:
    logger.warning(
        f"UI dist directory not found at {_UI_DIST}. "
        f"Run 'npm run build' in ui/ to build the frontend."
    )

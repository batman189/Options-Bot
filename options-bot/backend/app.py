"""
FastAPI application — entry point for the backend.
Registers all route modules, initializes database on startup.
Swagger docs available at /docs.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routes import profiles, models, trades, system

logger = logging.getLogger("options-bot.backend")


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
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow local frontend (Phase 3)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(profiles.router)
app.include_router(models.router)
app.include_router(trades.router)
app.include_router(system.router)


# Backtest routes — Phase 2 stub
from fastapi import APIRouter
backtest_router = APIRouter(prefix="/api/backtest", tags=["Backtesting"])


@backtest_router.post("/{profile_id}")
async def run_backtest(profile_id: str):
    """Trigger backtest for a profile. Phase 2 — stubbed."""
    return {
        "profile_id": profile_id,
        "status": "not_implemented",
        "message": "Backtesting endpoint available in Phase 2.",
    }


@backtest_router.get("/{profile_id}/results")
async def get_backtest_results(profile_id: str):
    """Get backtest results. Phase 2 — stubbed."""
    return {
        "profile_id": profile_id,
        "status": "not_implemented",
        "message": "Backtesting results available in Phase 2.",
    }


app.include_router(backtest_router)

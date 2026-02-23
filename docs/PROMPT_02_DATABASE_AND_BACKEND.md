# CLAUDE CODE PROMPT 02 — SQLite Database + FastAPI Backend (All Endpoints Stubbed)

## TASK
Create the SQLite database schema and FastAPI backend with ALL API endpoints defined, Pydantic schemas enforced, and Swagger docs live at localhost:8000/docs. This is Phase 1, Steps 2-4 from the architecture.

Phase 1 endpoints return real data where possible (profile CRUD works against the real database). Phase 2 endpoints are stubbed with correct schemas but return placeholder responses. The key outcome: every endpoint the UI will ever need exists RIGHT NOW with enforced schemas, so Phase 3 (UI) connects to a tested API with zero surprises.

**CRITICAL**: Before writing ANY code, read this ENTIRE prompt. Every file, every function, every schema is specified completely. Build exactly what is here.

---

## FILES TO CREATE

1. `options-bot/backend/__init__.py` — empty
2. `options-bot/backend/routes/__init__.py` — empty
3. `options-bot/backend/database.py` — SQLite connection + schema creation
4. `options-bot/backend/schemas.py` — ALL Pydantic request/response models
5. `options-bot/backend/routes/profiles.py` — Profile CRUD endpoints
6. `options-bot/backend/routes/models.py` — Model training/status endpoints
7. `options-bot/backend/routes/trades.py` — Trade history endpoints
8. `options-bot/backend/routes/system.py` — System health endpoints
9. `options-bot/backend/app.py` — FastAPI application + lifespan + router registration

---

## FILE 1: `options-bot/backend/__init__.py`

```python
```

(Empty file — makes backend a Python package)

---

## FILE 2: `options-bot/backend/routes/__init__.py`

```python
```

(Empty file — makes routes a Python package)

---

## FILE 3: `options-bot/backend/database.py`

```python
"""
SQLite database connection and schema management.
Schema matches PROJECT_ARCHITECTURE.md Section 5a exactly.
"""

import aiosqlite
import logging
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH

logger = logging.getLogger("options-bot.database")

# SQL schema — matches PROJECT_ARCHITECTURE.md Section 5a EXACTLY
SCHEMA_SQL = """
-- Profiles table
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    preset TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    symbols TEXT NOT NULL,
    config TEXT NOT NULL,
    model_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Models table
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    model_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    status TEXT NOT NULL,
    training_started_at TEXT,
    training_completed_at TEXT,
    data_start_date TEXT,
    data_end_date TEXT,
    metrics TEXT,
    feature_names TEXT,
    hyperparameters TEXT,
    created_at TEXT NOT NULL
);

-- Trades table
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    strike REAL NOT NULL,
    expiration TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price REAL,
    entry_date TEXT,
    entry_underlying_price REAL,
    entry_predicted_return REAL,
    entry_ev_pct REAL,
    entry_features TEXT,
    entry_greeks TEXT,
    entry_model_type TEXT,
    exit_price REAL,
    exit_date TEXT,
    exit_underlying_price REAL,
    exit_reason TEXT,
    exit_features TEXT,
    exit_greeks TEXT,
    pnl_dollars REAL,
    pnl_pct REAL,
    actual_return_pct REAL,
    hold_days INTEGER,
    was_day_trade INTEGER DEFAULT 0,
    market_vix REAL,
    market_regime TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- System state table
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Training logs
CREATE TABLE IF NOT EXISTS training_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


async def get_db() -> aiosqlite.Connection:
    """Get a database connection. Used as a FastAPI dependency."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """Initialize the database schema. Called once at startup."""
    logger.info(f"Initializing database at {DB_PATH}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()

    # Verify tables were created
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        logger.info(f"Database initialized. Tables: {tables}")

        expected_tables = {"models", "profiles", "system_state", "trades", "training_logs"}
        missing = expected_tables - set(tables)
        if missing:
            logger.error(f"MISSING TABLES: {missing}")
            raise RuntimeError(f"Database initialization failed. Missing tables: {missing}")

    logger.info("Database schema verified — all tables present.")
```

---

## FILE 4: `options-bot/backend/schemas.py`

```python
"""
Pydantic request/response schemas.
These define the API contract. Matches PROJECT_ARCHITECTURE.md Section 5c.

RULE: If the UI needs a field, it MUST be defined here FIRST.
If this file needs to change during Phase 3, that is a Phase 1 defect.
"""

from pydantic import BaseModel
from typing import Optional


# =============================================================================
# Profile Schemas
# =============================================================================

class ProfileCreate(BaseModel):
    name: str
    preset: str  # 'swing', 'general', 'scalp'
    symbols: list[str]
    config_overrides: dict = {}

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    symbols: Optional[list[str]] = None
    config_overrides: Optional[dict] = None

class ModelSummary(BaseModel):
    id: str
    model_type: str
    status: str
    trained_at: Optional[str] = None
    data_range: str
    metrics: dict
    age_days: int

class ProfileResponse(BaseModel):
    id: str
    name: str
    preset: str
    status: str
    symbols: list[str]
    config: dict
    model_summary: Optional[ModelSummary] = None
    active_positions: int
    total_pnl: float
    created_at: str
    updated_at: str


# =============================================================================
# Model Schemas
# =============================================================================

class ModelResponse(BaseModel):
    id: str
    profile_id: str
    model_type: str
    file_path: str
    status: str
    training_started_at: Optional[str] = None
    training_completed_at: Optional[str] = None
    data_start_date: Optional[str] = None
    data_end_date: Optional[str] = None
    metrics: Optional[dict] = None
    feature_names: Optional[list[str]] = None
    hyperparameters: Optional[dict] = None
    created_at: str

class TrainRequest(BaseModel):
    """Optional overrides for training parameters."""
    force_full_retrain: bool = False

class TrainingStatus(BaseModel):
    model_id: Optional[str] = None
    profile_id: str
    status: str  # 'idle', 'training', 'completed', 'failed'
    progress_pct: Optional[float] = None
    message: Optional[str] = None

class ModelMetrics(BaseModel):
    model_id: str
    profile_id: str
    model_type: str
    mae: Optional[float] = None
    rmse: Optional[float] = None
    r2: Optional[float] = None
    directional_accuracy: Optional[float] = None
    training_samples: Optional[int] = None
    feature_count: Optional[int] = None
    cv_folds: Optional[int] = None

class TrainingLogEntry(BaseModel):
    id: int
    model_id: str
    timestamp: str
    level: str
    message: str


# =============================================================================
# Trade Schemas
# =============================================================================

class TradeResponse(BaseModel):
    id: str
    profile_id: str
    symbol: str
    direction: str
    strike: float
    expiration: str
    quantity: int
    entry_price: Optional[float] = None
    entry_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    pnl_dollars: Optional[float] = None
    pnl_pct: Optional[float] = None
    predicted_return: Optional[float] = None
    ev_at_entry: Optional[float] = None
    exit_reason: Optional[str] = None
    hold_days: Optional[int] = None
    status: str
    was_day_trade: bool
    created_at: str
    updated_at: str

class TradeStats(BaseModel):
    total_trades: int
    open_trades: int
    closed_trades: int
    win_count: int
    loss_count: int
    win_rate: Optional[float] = None
    total_pnl_dollars: float
    avg_pnl_pct: Optional[float] = None
    best_trade_pct: Optional[float] = None
    worst_trade_pct: Optional[float] = None
    avg_hold_days: Optional[float] = None


# =============================================================================
# System Schemas
# =============================================================================

class SystemStatus(BaseModel):
    alpaca_connected: bool
    alpaca_subscription: str
    theta_terminal_connected: bool
    active_profiles: int
    total_open_positions: int
    pdt_day_trades_5d: int
    pdt_limit: int
    portfolio_value: float
    uptime_seconds: int
    last_error: Optional[str] = None

class HealthCheck(BaseModel):
    status: str
    timestamp: str
    version: str

class PDTStatus(BaseModel):
    day_trades_5d: int
    limit: int
    remaining: int
    equity: float
    is_restricted: bool

class ErrorLogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    source: Optional[str] = None


# =============================================================================
# Backtest Schemas (Phase 2 — stubbed)
# =============================================================================

class BacktestRequest(BaseModel):
    start_date: str
    end_date: str
    initial_capital: float = 25000.0

class BacktestResult(BaseModel):
    profile_id: str
    status: str  # 'pending', 'running', 'completed', 'failed'
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_trades: Optional[int] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    total_return_pct: Optional[float] = None
    win_rate: Optional[float] = None
    message: Optional[str] = None
```

---

## FILE 5: `options-bot/backend/routes/profiles.py`

```python
"""
Profile CRUD endpoints.
Phase 1: All endpoints fully functional against SQLite.
Matches PROJECT_ARCHITECTURE.md Section 5b — Profiles.
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import PRESET_DEFAULTS

from backend.database import get_db
from backend.schemas import ProfileCreate, ProfileUpdate, ProfileResponse, ModelSummary

logger = logging.getLogger("options-bot.routes.profiles")
router = APIRouter(prefix="/api/profiles", tags=["Profiles"])


def _build_profile_response(row: aiosqlite.Row, model_row=None) -> ProfileResponse:
    """Convert a database row to a ProfileResponse."""
    model_summary = None
    if model_row and model_row["id"]:
        trained_at = model_row["training_completed_at"]
        data_start = model_row["data_start_date"] or "unknown"
        data_end = model_row["data_end_date"] or "unknown"
        metrics_raw = model_row["metrics"]
        metrics = json.loads(metrics_raw) if metrics_raw else {}

        age_days = 0
        if trained_at:
            try:
                trained_dt = datetime.fromisoformat(trained_at)
                age_days = (datetime.utcnow() - trained_dt).days
            except (ValueError, TypeError):
                age_days = 0

        model_summary = ModelSummary(
            id=model_row["id"],
            model_type=model_row["model_type"],
            status=model_row["status"],
            trained_at=trained_at,
            data_range=f"{data_start} to {data_end}",
            metrics=metrics,
            age_days=age_days,
        )

    return ProfileResponse(
        id=row["id"],
        name=row["name"],
        preset=row["preset"],
        status=row["status"],
        symbols=json.loads(row["symbols"]),
        config=json.loads(row["config"]),
        model_summary=model_summary,
        active_positions=0,  # Will be populated when trading is active
        total_pnl=0.0,       # Will be calculated from trades table
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# -------------------------------------------------------------------------
# GET /api/profiles — List all profiles
# -------------------------------------------------------------------------
@router.get("", response_model=list[ProfileResponse])
async def list_profiles(db: aiosqlite.Connection = Depends(get_db)):
    """List all profiles with model summaries."""
    logger.info("GET /api/profiles — listing all profiles")
    cursor = await db.execute("SELECT * FROM profiles ORDER BY created_at DESC")
    rows = await cursor.fetchall()

    responses = []
    for row in rows:
        model_row = None
        if row["model_id"]:
            mcursor = await db.execute("SELECT * FROM models WHERE id = ?", (row["model_id"],))
            model_row = await mcursor.fetchone()
        responses.append(_build_profile_response(row, model_row))

    logger.info(f"Returning {len(responses)} profiles")
    return responses


# -------------------------------------------------------------------------
# GET /api/profiles/{id} — Get single profile
# -------------------------------------------------------------------------
@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single profile with full model info."""
    logger.info(f"GET /api/profiles/{profile_id}")
    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    model_row = None
    if row["model_id"]:
        mcursor = await db.execute("SELECT * FROM models WHERE id = ?", (row["model_id"],))
        model_row = await mcursor.fetchone()

    return _build_profile_response(row, model_row)


# -------------------------------------------------------------------------
# POST /api/profiles — Create new profile
# -------------------------------------------------------------------------
@router.post("", response_model=ProfileResponse, status_code=201)
async def create_profile(body: ProfileCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new profile with preset defaults."""
    logger.info(f"POST /api/profiles — creating profile: {body.name} ({body.preset})")

    # Validate preset
    if body.preset not in PRESET_DEFAULTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preset '{body.preset}'. Must be one of: {list(PRESET_DEFAULTS.keys())}"
        )

    # Validate symbols
    if not body.symbols or len(body.symbols) == 0:
        raise HTTPException(status_code=400, detail="At least one symbol is required")

    # Build config from preset defaults + overrides
    config = dict(PRESET_DEFAULTS[body.preset])
    config.update(body.config_overrides)

    now = datetime.utcnow().isoformat()
    profile_id = str(uuid.uuid4())

    await db.execute(
        """INSERT INTO profiles (id, name, preset, status, symbols, config, model_id, created_at, updated_at)
           VALUES (?, ?, ?, 'created', ?, ?, NULL, ?, ?)""",
        (profile_id, body.name, body.preset, json.dumps(body.symbols), json.dumps(config), now, now),
    )
    await db.commit()

    logger.info(f"Profile created: {profile_id} ({body.name})")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    return _build_profile_response(row)


# -------------------------------------------------------------------------
# PUT /api/profiles/{id} — Update profile config
# -------------------------------------------------------------------------
@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    body: ProfileUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update profile settings."""
    logger.info(f"PUT /api/profiles/{profile_id}")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    now = datetime.utcnow().isoformat()
    updates = {"updated_at": now}

    if body.name is not None:
        updates["name"] = body.name
    if body.symbols is not None:
        updates["symbols"] = json.dumps(body.symbols)
    if body.config_overrides is not None:
        current_config = json.loads(row["config"])
        current_config.update(body.config_overrides)
        updates["config"] = json.dumps(current_config)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [profile_id]
    await db.execute(f"UPDATE profiles SET {set_clause} WHERE id = ?", values)
    await db.commit()

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    return _build_profile_response(row)


# -------------------------------------------------------------------------
# DELETE /api/profiles/{id} — Delete profile + model files
# -------------------------------------------------------------------------
@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a profile and associated model files."""
    logger.info(f"DELETE /api/profiles/{profile_id}")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    # Delete associated models
    await db.execute("DELETE FROM models WHERE profile_id = ?", (profile_id,))
    # Delete associated trades
    await db.execute("DELETE FROM trades WHERE profile_id = ?", (profile_id,))
    # Delete associated training logs
    await db.execute(
        "DELETE FROM training_logs WHERE model_id IN (SELECT id FROM models WHERE profile_id = ?)",
        (profile_id,),
    )
    # Delete the profile
    await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    await db.commit()

    logger.info(f"Profile deleted: {profile_id}")
    # 204 No Content — no response body


# -------------------------------------------------------------------------
# POST /api/profiles/{id}/activate — Phase 2 stub
# -------------------------------------------------------------------------
@router.post("/{profile_id}/activate", response_model=ProfileResponse)
async def activate_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Start trading this profile. Phase 2 — currently updates status only."""
    logger.info(f"POST /api/profiles/{profile_id}/activate")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    if row["status"] not in ("ready", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"Profile must be in 'ready' or 'paused' status to activate. Current: {row['status']}"
        )

    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE profiles SET status = 'active', updated_at = ? WHERE id = ?",
        (now, profile_id),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    return _build_profile_response(row)


# -------------------------------------------------------------------------
# POST /api/profiles/{id}/pause — Phase 2 stub
# -------------------------------------------------------------------------
@router.post("/{profile_id}/pause", response_model=ProfileResponse)
async def pause_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Pause trading this profile. Phase 2 — currently updates status only."""
    logger.info(f"POST /api/profiles/{profile_id}/pause")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    if row["status"] != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Profile must be 'active' to pause. Current: {row['status']}"
        )

    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE profiles SET status = 'paused', updated_at = ? WHERE id = ?",
        (now, profile_id),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    return _build_profile_response(row)
```

---

## FILE 6: `options-bot/backend/routes/models.py`

```python
"""
Model training and status endpoints.
Phase 1: train + status + metrics work (once trainer is built).
         For now, train is stubbed to return 'not implemented yet'.
Phase 2: retrain + logs fully functional.
Matches PROJECT_ARCHITECTURE.md Section 5b — Models.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import aiosqlite

from backend.database import get_db
from backend.schemas import (
    ModelResponse, TrainRequest, TrainingStatus,
    ModelMetrics, TrainingLogEntry,
)

logger = logging.getLogger("options-bot.routes.models")
router = APIRouter(prefix="/api/models", tags=["Models"])


# -------------------------------------------------------------------------
# GET /api/models/{profile_id} — Get model info for a profile
# -------------------------------------------------------------------------
@router.get("/{profile_id}", response_model=Optional[ModelResponse])
async def get_model(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get model info for a profile."""
    logger.info(f"GET /api/models/{profile_id}")

    cursor = await db.execute(
        "SELECT * FROM models WHERE profile_id = ? ORDER BY created_at DESC LIMIT 1",
        (profile_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None

    return ModelResponse(
        id=row["id"],
        profile_id=row["profile_id"],
        model_type=row["model_type"],
        file_path=row["file_path"],
        status=row["status"],
        training_started_at=row["training_started_at"],
        training_completed_at=row["training_completed_at"],
        data_start_date=row["data_start_date"],
        data_end_date=row["data_end_date"],
        metrics=json.loads(row["metrics"]) if row["metrics"] else None,
        feature_names=json.loads(row["feature_names"]) if row["feature_names"] else None,
        hyperparameters=json.loads(row["hyperparameters"]) if row["hyperparameters"] else None,
        created_at=row["created_at"],
    )


# -------------------------------------------------------------------------
# POST /api/models/{profile_id}/train — Trigger full training
# -------------------------------------------------------------------------
@router.post("/{profile_id}/train", response_model=TrainingStatus)
async def train_model(
    profile_id: str,
    body: TrainRequest = TrainRequest(),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Trigger full model training for a profile.
    Currently returns stub — will connect to ml/trainer.py in a later prompt."""
    logger.info(f"POST /api/models/{profile_id}/train (force_full={body.force_full_retrain})")

    # Verify profile exists
    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    # STUB: Training pipeline not yet connected
    return TrainingStatus(
        model_id=None,
        profile_id=profile_id,
        status="idle",
        progress_pct=0.0,
        message="Training pipeline not yet implemented. Will be connected in Prompt 04.",
    )


# -------------------------------------------------------------------------
# POST /api/models/{profile_id}/retrain — Phase 2 stub
# -------------------------------------------------------------------------
@router.post("/{profile_id}/retrain", response_model=TrainingStatus)
async def retrain_model(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Trigger incremental retraining. Phase 2 — stubbed."""
    logger.info(f"POST /api/models/{profile_id}/retrain")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    return TrainingStatus(
        model_id=None,
        profile_id=profile_id,
        status="idle",
        progress_pct=0.0,
        message="Incremental retraining not yet implemented (Phase 2).",
    )


# -------------------------------------------------------------------------
# GET /api/models/{profile_id}/status — Training progress
# -------------------------------------------------------------------------
@router.get("/{profile_id}/status", response_model=TrainingStatus)
async def get_training_status(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get current training status for a profile."""
    logger.info(f"GET /api/models/{profile_id}/status")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    # Check if there's an active model
    mcursor = await db.execute(
        "SELECT * FROM models WHERE profile_id = ? ORDER BY created_at DESC LIMIT 1",
        (profile_id,),
    )
    model_row = await mcursor.fetchone()

    if model_row:
        return TrainingStatus(
            model_id=model_row["id"],
            profile_id=profile_id,
            status=model_row["status"],
            progress_pct=100.0 if model_row["status"] == "ready" else 0.0,
            message=f"Model status: {model_row['status']}",
        )

    return TrainingStatus(
        model_id=None,
        profile_id=profile_id,
        status="idle",
        progress_pct=0.0,
        message="No model trained yet.",
    )


# -------------------------------------------------------------------------
# GET /api/models/{profile_id}/metrics — Model performance metrics
# -------------------------------------------------------------------------
@router.get("/{profile_id}/metrics", response_model=ModelMetrics)
async def get_model_metrics(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get model performance metrics."""
    logger.info(f"GET /api/models/{profile_id}/metrics")

    cursor = await db.execute(
        "SELECT * FROM models WHERE profile_id = ? ORDER BY created_at DESC LIMIT 1",
        (profile_id,),
    )
    model_row = await cursor.fetchone()
    if not model_row:
        raise HTTPException(status_code=404, detail=f"No model found for profile {profile_id}")

    metrics = json.loads(model_row["metrics"]) if model_row["metrics"] else {}
    features = json.loads(model_row["feature_names"]) if model_row["feature_names"] else []

    return ModelMetrics(
        model_id=model_row["id"],
        profile_id=profile_id,
        model_type=model_row["model_type"],
        mae=metrics.get("mae"),
        rmse=metrics.get("rmse"),
        r2=metrics.get("r2"),
        directional_accuracy=metrics.get("dir_acc"),
        training_samples=metrics.get("training_samples"),
        feature_count=len(features),
        cv_folds=metrics.get("cv_folds"),
    )


# -------------------------------------------------------------------------
# GET /api/models/{profile_id}/logs — Training log stream (Phase 2 stub)
# -------------------------------------------------------------------------
@router.get("/{profile_id}/logs", response_model=list[TrainingLogEntry])
async def get_training_logs(
    profile_id: str,
    limit: int = 100,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get training logs for a profile's model. Phase 2 — returns real data from training_logs table."""
    logger.info(f"GET /api/models/{profile_id}/logs (limit={limit})")

    cursor = await db.execute(
        """SELECT tl.* FROM training_logs tl
           JOIN models m ON tl.model_id = m.id
           WHERE m.profile_id = ?
           ORDER BY tl.timestamp DESC LIMIT ?""",
        (profile_id, limit),
    )
    rows = await cursor.fetchall()

    return [
        TrainingLogEntry(
            id=row["id"],
            model_id=row["model_id"],
            timestamp=row["timestamp"],
            level=row["level"],
            message=row["message"],
        )
        for row in rows
    ]
```

---

## FILE 7: `options-bot/backend/routes/trades.py`

```python
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
        exit_reason=row["exit_reason"],
        hold_days=row["hold_days"],
        status=row["status"],
        was_day_trade=bool(row["was_day_trade"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
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
    limit: int = Query(100, ge=1, le=1000),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List trades with optional filters."""
    logger.info(f"GET /api/trades (profile={profile_id}, status={status}, symbol={symbol})")

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
```

---

## FILE 8: `options-bot/backend/routes/system.py`

```python
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
```

---

## FILE 9: `options-bot/backend/app.py`

```python
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
```

---

## STEP 7: Update main.py to start the backend

Replace the placeholder `options-bot/main.py` with:

```python
"""
Options Bot — Entry Point
Starts the FastAPI backend server.
Trading strategies will be added in later prompts.
"""

import logging
import uvicorn
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from config import API_HOST, API_PORT, LOG_LEVEL, LOG_FORMAT

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("options-bot")


def main():
    logger.info("Options Bot — Starting backend server...")
    logger.info(f"API will be available at http://{API_HOST}:{API_PORT}")
    logger.info(f"Swagger docs at http://{API_HOST}:{API_PORT}/docs")

    uvicorn.run(
        "backend.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
```

---

## VERIFICATION

After creating all files, run these commands IN ORDER:

```bash
cd options-bot

# 1. Verify all files exist
echo "=== Checking files ==="
for f in \
    backend/__init__.py \
    backend/routes/__init__.py \
    backend/database.py \
    backend/schemas.py \
    backend/routes/profiles.py \
    backend/routes/models.py \
    backend/routes/trades.py \
    backend/routes/system.py \
    backend/app.py \
    main.py; do
    if [ -f "$f" ]; then echo "  ✅ $f"; else echo "  ❌ MISSING: $f"; fi
done

# 2. Verify Python imports work
echo ""
echo "=== Testing imports ==="
python -c "from backend.database import init_db; print('  ✅ database.py imports OK')"
python -c "from backend.schemas import ProfileCreate, ProfileResponse, SystemStatus, TradeResponse; print('  ✅ schemas.py imports OK')"
python -c "from backend.app import app; print(f'  ✅ app.py imports OK — {len(app.routes)} routes registered')"

# 3. Start the server and test
echo ""
echo "=== Starting server ==="
python main.py &
SERVER_PID=$!
sleep 3

# 4. Test endpoints
echo ""
echo "=== Testing endpoints ==="

# Health check
curl -s http://127.0.0.1:8000/api/system/health | python -m json.tool
echo ""

# List profiles (should be empty)
curl -s http://127.0.0.1:8000/api/profiles | python -m json.tool
echo ""

# Create a profile
curl -s -X POST http://127.0.0.1:8000/api/profiles \
    -H "Content-Type: application/json" \
    -d '{"name": "TSLA Swing Test", "preset": "swing", "symbols": ["TSLA"]}' | python -m json.tool
echo ""

# List profiles again (should have one)
curl -s http://127.0.0.1:8000/api/profiles | python -m json.tool
echo ""

# Test Swagger docs exist
curl -s -o /dev/null -w "Swagger docs HTTP status: %{http_code}\n" http://127.0.0.1:8000/docs
echo ""

# 5. Cleanup
kill $SERVER_PID 2>/dev/null
echo "=== Server stopped ==="
echo ""
echo "If all tests passed: Swagger docs are at http://localhost:8000/docs"
echo "Open that URL in your browser to see and test all endpoints."
```

## WHAT SUCCESS LOOKS LIKE

1. Server starts without errors
2. `/api/system/health` returns `{"status": "ok", ...}`
3. `/api/profiles` returns `[]` (empty list)
4. POST to `/api/profiles` creates a profile and returns it with all fields populated
5. GET `/api/profiles` returns the created profile
6. Swagger docs at `/docs` show ALL endpoint groups: Profiles, Models, Trades, System, Backtesting
7. SQLite database file created at `db/options_bot.db` with all 5 tables
8. Every endpoint responds (even if stubbed) — no 404s on defined routes

## WHAT FAILURE LOOKS LIKE

- Import errors on startup
- Missing routes in Swagger
- Profile CRUD returns errors
- Database file not created
- Any endpoint returns 500

## DO NOT

- Do NOT install any new dependencies (everything needed is in requirements.txt from Prompt 01)
- Do NOT create any files not listed in this prompt
- Do NOT modify files from Prompt 01 (except main.py which is explicitly replaced)
- Do NOT add endpoints not defined in PROJECT_ARCHITECTURE.md Section 5b
- Do NOT add trading logic, ML logic, or data provider logic — those come in later prompts

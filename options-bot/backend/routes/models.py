"""
Model training and status endpoints.
Phase 2: train + retrain both wired to real ML pipelines via background threads.
Matches PROJECT_ARCHITECTURE.md Section 5b — Models.
"""

import json
import logging
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import aiosqlite

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import get_db
from backend.schemas import (
    ModelResponse, TrainRequest, TrainingStatus,
    ModelMetrics, TrainingLogEntry,
)

logger = logging.getLogger("options-bot.routes.models")
router = APIRouter(prefix="/api/models", tags=["Models"])

# Tracks profile IDs that currently have a training job running.
# Prevents duplicate concurrent training for the same profile.
_active_jobs: set = set()
_active_jobs_lock = threading.Lock()


# =============================================================================
# Background training jobs
# =============================================================================

def _set_profile_status(profile_id: str, status: str):
    """Synchronously update profile status in the database."""
    import asyncio
    import aiosqlite as _aiosqlite

    async def _update():
        from config import DB_PATH
        try:
            async with _aiosqlite.connect(str(DB_PATH)) as db:
                now = datetime.utcnow().isoformat()
                await db.execute(
                    "UPDATE profiles SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, profile_id),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"_set_profile_status: failed to set {profile_id} → {status}: {e}")

    try:
        asyncio.run(_update())
    except Exception as e:
        logger.error(f"_set_profile_status: asyncio.run failed: {e}")


def _full_train_job(profile_id: str, symbol: str, preset: str, horizon: str, years: int):
    """
    Background thread: run full training pipeline.
    Sets profile status to 'training' at start, 'ready' on success,
    or restores previous status on failure.
    """
    logger.info(
        f"_full_train_job: starting for profile={profile_id} "
        f"symbol={symbol} preset={preset} horizon={horizon} years={years}"
    )
    _set_profile_status(profile_id, "training")

    try:
        from ml.trainer import train_model
        result = train_model(
            profile_id=profile_id,
            symbol=symbol,
            preset=preset,
            prediction_horizon=horizon,
            years_of_data=years,
        )
        if result.get("status") == "ready":
            logger.info(
                f"_full_train_job: completed for profile={profile_id} "
                f"model_id={result.get('model_id')} "
                f"dir_acc={result.get('metrics', {}).get('dir_acc', 'N/A')}"
            )
            # train_model() already updates profile status to 'ready' in DB
        else:
            logger.error(
                f"_full_train_job: train_model returned unexpected status: {result}"
            )
            _set_profile_status(profile_id, "created")
    except Exception as e:
        logger.error(
            f"_full_train_job: exception for profile={profile_id}: {e}",
            exc_info=True,
        )
        _set_profile_status(profile_id, "created")
    finally:
        with _active_jobs_lock:
            _active_jobs.discard(profile_id)
        logger.info(f"_full_train_job: job slot released for profile={profile_id}")


def _incremental_retrain_job(profile_id: str, symbol: str, preset: str, horizon: str):
    """
    Background thread: run incremental retraining.
    Sets profile status to 'training' at start, restores 'ready' on completion
    (retrain_incremental handles its own DB update on success).
    """
    logger.info(
        f"_incremental_retrain_job: starting for profile={profile_id} "
        f"symbol={symbol} preset={preset} horizon={horizon}"
    )
    _set_profile_status(profile_id, "training")

    try:
        from ml.incremental_trainer import retrain_incremental
        result = retrain_incremental(
            profile_id=profile_id,
            symbol=symbol,
            preset=preset,
            prediction_horizon=horizon,
        )
        status = result.get("status")
        if status == "updated":
            logger.info(
                f"_incremental_retrain_job: completed for profile={profile_id} "
                f"new_model={result.get('new_model_id')} "
                f"new_samples={result.get('new_samples')}"
            )
            # retrain_incremental() already updates profile model_id and status='ready'
        elif status == "skipped":
            logger.info(
                f"_incremental_retrain_job: skipped for profile={profile_id}: "
                f"{result.get('message')}"
            )
            _set_profile_status(profile_id, "ready")
        else:
            logger.error(
                f"_incremental_retrain_job: error for profile={profile_id}: "
                f"{result.get('message')}"
            )
            _set_profile_status(profile_id, "ready")
    except Exception as e:
        logger.error(
            f"_incremental_retrain_job: exception for profile={profile_id}: {e}",
            exc_info=True,
        )
        _set_profile_status(profile_id, "ready")
    finally:
        with _active_jobs_lock:
            _active_jobs.discard(profile_id)
        logger.info(f"_incremental_retrain_job: job slot released for profile={profile_id}")


# =============================================================================
# Endpoints
# =============================================================================

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
async def train_model_endpoint(
    profile_id: str,
    body: TrainRequest = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Trigger full model training for a profile.
    Runs in a background thread — returns immediately.
    Poll GET /api/models/{profile_id}/status to track progress.
    """
    if body is None:
        body = TrainRequest()

    logger.info(
        f"POST /api/models/{profile_id}/train "
        f"years={getattr(body, 'years_of_data', None)} force={body.force_full_retrain}"
    )

    # Verify profile exists
    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    # Check for duplicate job
    with _active_jobs_lock:
        if profile_id in _active_jobs:
            raise HTTPException(
                status_code=409,
                detail=f"Training already in progress for profile {profile_id}. Poll /status to track.",
            )
        _active_jobs.add(profile_id)

    # Extract training params from profile
    import json as _json
    symbols = _json.loads(row["symbols"])
    symbol = symbols[0] if symbols else "TSLA"
    preset = row["preset"]

    from config import PRESET_DEFAULTS
    horizon = PRESET_DEFAULTS.get(preset, {}).get("prediction_horizon", "5d")
    years = getattr(body, "years_of_data", None) or 6

    logger.info(
        f"Spawning training thread: profile={profile_id} "
        f"symbol={symbol} preset={preset} horizon={horizon} years={years}"
    )

    thread = threading.Thread(
        target=_full_train_job,
        args=(profile_id, symbol, preset, horizon, years),
        daemon=True,
        name=f"train-{profile_id[:8]}",
    )
    thread.start()

    return TrainingStatus(
        model_id=None,
        profile_id=profile_id,
        status="training",
        progress_pct=0.0,
        message=(
            f"Training started for {symbol} ({preset}, {years}yr). "
            f"Poll GET /api/models/{profile_id}/status for updates. "
            f"Typical duration: 5–15 minutes."
        ),
    )


# -------------------------------------------------------------------------
# POST /api/models/{profile_id}/retrain — Incremental retraining
# -------------------------------------------------------------------------
@router.post("/{profile_id}/retrain", response_model=TrainingStatus)
async def retrain_model(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """
    Trigger incremental retraining for a profile.
    Requires an existing trained model. Runs in a background thread.
    Poll GET /api/models/{profile_id}/status to track progress.
    """
    logger.info(f"POST /api/models/{profile_id}/retrain")

    # Verify profile exists and has a model
    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    if not row["model_id"]:
        raise HTTPException(
            status_code=400,
            detail=f"Profile {profile_id} has no trained model. Run /train first.",
        )

    # Check for duplicate job
    with _active_jobs_lock:
        if profile_id in _active_jobs:
            raise HTTPException(
                status_code=409,
                detail=f"Training already in progress for profile {profile_id}. Poll /status to track.",
            )
        _active_jobs.add(profile_id)

    import json as _json
    symbols = _json.loads(row["symbols"])
    symbol = symbols[0] if symbols else "TSLA"
    preset = row["preset"]

    from config import PRESET_DEFAULTS
    horizon = PRESET_DEFAULTS.get(preset, {}).get("prediction_horizon", "5d")

    logger.info(
        f"Spawning retrain thread: profile={profile_id} "
        f"symbol={symbol} preset={preset} horizon={horizon}"
    )

    thread = threading.Thread(
        target=_incremental_retrain_job,
        args=(profile_id, symbol, preset, horizon),
        daemon=True,
        name=f"retrain-{profile_id[:8]}",
    )
    thread.start()

    return TrainingStatus(
        model_id=row["model_id"],
        profile_id=profile_id,
        status="training",
        progress_pct=0.0,
        message=(
            f"Incremental retraining started for {symbol} ({preset}). "
            f"Poll GET /api/models/{profile_id}/status for updates. "
            f"Typical duration: 1–3 minutes."
        ),
    )


# -------------------------------------------------------------------------
# GET /api/models/{profile_id}/status — Training progress
# -------------------------------------------------------------------------
@router.get("/{profile_id}/status", response_model=TrainingStatus)
async def get_training_status(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """
    Get current training status for a profile.
    Returns 'training' if a job is active, 'ready' if model is trained, 'idle' otherwise.
    """
    logger.info(f"GET /api/models/{profile_id}/status")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    # Check in-memory job tracker first (authoritative for in-progress jobs)
    with _active_jobs_lock:
        is_active = profile_id in _active_jobs

    if is_active:
        return TrainingStatus(
            model_id=row["model_id"],
            profile_id=profile_id,
            status="training",
            progress_pct=50.0,  # No fine-grained progress available
            message="Training in progress. This may take several minutes.",
        )

    # Check model record
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
        message="No model trained yet. POST /train to start.",
    )


# -------------------------------------------------------------------------
# GET /api/models/{profile_id}/metrics — Model performance metrics
# -------------------------------------------------------------------------
@router.get("/{profile_id}/metrics", response_model=ModelMetrics)
async def get_model_metrics(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get model performance metrics for a profile."""
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
# GET /api/models/{profile_id}/logs — Training log stream
# -------------------------------------------------------------------------
@router.get("/{profile_id}/logs", response_model=list[TrainingLogEntry])
async def get_training_logs(
    profile_id: str,
    limit: int = 100,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Get training log entries for a profile's most recent model.
    Reads from the training_logs table.
    Returns empty list if no logs exist yet.
    """
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

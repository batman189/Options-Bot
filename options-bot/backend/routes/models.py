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

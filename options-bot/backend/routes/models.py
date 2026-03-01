"""
Model training and status endpoints.
Phase 2: train + retrain both wired to real ML pipelines via background threads.
Matches PROJECT_ARCHITECTURE.md Section 5b — Models.
"""

import asyncio
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
# Training log capture
# =============================================================================

def _install_training_logger(profile_id: str):
    """Install a thread-filtered log handler that captures training output to DB."""
    from config import DB_PATH
    from backend.db_log_handler import TrainingLogHandler

    handler = TrainingLogHandler(str(DB_PATH), profile_id)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("options-bot").addHandler(handler)
    return handler


def _remove_training_logger(handler):
    """Remove a previously installed training log handler."""
    logging.getLogger("options-bot").removeHandler(handler)


# =============================================================================
# Theta Terminal pre-check
# =============================================================================

def _check_theta_or_raise():
    """
    Test Theta Terminal connectivity. Raises HTTPException(503) if unreachable.
    Called before spawning training threads for fast user feedback.
    """
    import requests as _requests
    from config import THETA_BASE_URL_V3

    try:
        resp = _requests.get(
            f"{THETA_BASE_URL_V3}/stock/list/symbols",
            timeout=5,
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Theta Terminal returned status {resp.status_code}. "
                    "Start Theta Terminal and try again."
                ),
            )
    except HTTPException:
        raise
    except _requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot connect to Theta Terminal. "
                "Start Theta Terminal before training — "
                "options data is required."
            ),
        )
    except _requests.exceptions.Timeout:
        raise HTTPException(
            status_code=503,
            detail=(
                "Theta Terminal connection timed out. "
                "Ensure Theta Terminal is running and responsive."
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Theta Terminal check failed: {e}",
        )


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


def _extract_and_persist_importance(model_id: str, model_type: str, model_path: str):
    """
    Load the trained model from disk, extract feature importance, and merge it
    into the metrics JSON already stored in the DB.

    Called from each training job after the trainer saves its DB record.
    Non-fatal: logs warning on failure, does not raise.

    Args:
        model_id: UUID of the model record to update
        model_type: 'xgboost', 'tft', or 'ensemble'
        model_path: Path to the model file or directory
    """
    import asyncio as _asyncio
    import aiosqlite as _aiosqlite
    import json as _json
    from config import DB_PATH as _DB_PATH

    try:
        importance = {}

        if model_type == "xgboost":
            from ml.xgboost_predictor import XGBoostPredictor
            p = XGBoostPredictor(model_path)
            importance = p.get_feature_importance()

        elif model_type == "tft":
            from ml.tft_predictor import TFTPredictor
            p = TFTPredictor(model_path)
            importance = p.get_feature_importance()

        elif model_type == "ensemble":
            from ml.ensemble_predictor import EnsemblePredictor
            p = EnsemblePredictor(model_path)
            importance = p.get_feature_importance()

        if not importance:
            logger.warning(
                f"_extract_and_persist_importance: empty importance for "
                f"model_id={model_id} type={model_type}"
            )
            return

        # Take top 30 by importance score to keep DB record manageable
        top_importance = dict(
            sorted(importance.items(), key=lambda x: x[1], reverse=True)[:30]
        )

        async def _update():
            async with _aiosqlite.connect(str(_DB_PATH)) as db:
                db.row_factory = _aiosqlite.Row
                cursor = await db.execute(
                    "SELECT metrics FROM models WHERE id = ?", (model_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    return
                existing = _json.loads(row["metrics"]) if row["metrics"] else {}
                existing["feature_importance"] = top_importance
                await db.execute(
                    "UPDATE models SET metrics = ? WHERE id = ?",
                    (_json.dumps(existing), model_id),
                )
                await db.commit()
                logger.info(
                    f"_extract_and_persist_importance: stored top {len(top_importance)} "
                    f"features for model_id={model_id}"
                )

        _asyncio.run(_update())

    except Exception as e:
        logger.warning(
            f"_extract_and_persist_importance: failed for model_id={model_id}: {e}",
            exc_info=True,
        )


def _full_train_job(profile_id: str, symbol: str, preset: str, horizon: str, years: int):
    """
    Background thread: run full training pipeline.
    Sets profile status to 'training' at start, 'ready' on success,
    or restores previous status on failure.
    """
    log_handler = _install_training_logger(profile_id)
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
            _extract_and_persist_importance(
                model_id=result["model_id"],
                model_type="xgboost",
                model_path=result["model_path"],
            )
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
        _remove_training_logger(log_handler)
        with _active_jobs_lock:
            _active_jobs.discard(profile_id)
        logger.info(f"_full_train_job: job slot released for profile={profile_id}")


def _incremental_retrain_job(profile_id: str, symbol: str, preset: str, horizon: str):
    """
    Background thread: run incremental retraining.
    Sets profile status to 'training' at start, restores 'ready' on completion
    (retrain_incremental handles its own DB update on success).
    """
    log_handler = _install_training_logger(profile_id)
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
        _remove_training_logger(log_handler)
        with _active_jobs_lock:
            _active_jobs.discard(profile_id)
        logger.info(f"_incremental_retrain_job: job slot released for profile={profile_id}")


def _tft_train_job(profile_id: str, symbol: str, preset: str, horizon: str, years: int):
    """
    Background thread: run TFT training pipeline.
    Sets profile status to 'training' at start, 'ready' on success.
    """
    log_handler = _install_training_logger(profile_id)
    logger.info(
        f"_tft_train_job: starting for profile={profile_id} "
        f"symbol={symbol} preset={preset}"
    )
    _set_profile_status(profile_id, "training")

    try:
        from ml.tft_trainer import train_tft_model
        result = train_tft_model(
            profile_id=profile_id,
            symbol=symbol,
            preset=preset,
            prediction_horizon=horizon,
            years_of_data=years,
        )
        if result.get("status") == "ready":
            logger.info(
                f"_tft_train_job: completed for profile={profile_id} "
                f"model_id={result.get('model_id')} "
                f"dir_acc={result.get('metrics', {}).get('dir_acc', 'N/A')}"
            )
            _extract_and_persist_importance(
                model_id=result["model_id"],
                model_type="tft",
                model_path=result["model_dir"],
            )
        else:
            logger.error(f"_tft_train_job: unexpected result: {result}")
            _set_profile_status(profile_id, "created")
    except Exception as e:
        logger.error(
            f"_tft_train_job: exception for profile={profile_id}: {e}",
            exc_info=True,
        )
        _set_profile_status(profile_id, "created")
    finally:
        _remove_training_logger(log_handler)
        with _active_jobs_lock:
            _active_jobs.discard(profile_id)
        logger.info(f"_tft_train_job: job slot released for profile={profile_id}")


def _ensemble_train_job(profile_id: str, symbol: str, preset: str, horizon: str, years: int):
    """
    Background thread: train ensemble meta-learner.

    Requires that BOTH an xgboost model AND a tft model already exist for this
    profile. Finds the most recent of each type from the models table.

    If either is missing, logs an error and sets status back to 'ready'.
    """
    import asyncio as _asyncio
    import aiosqlite as _aio
    import json as _json
    from config import DB_PATH as _DB_PATH

    log_handler = _install_training_logger(profile_id)
    logger.info(
        f"_ensemble_train_job: starting for profile={profile_id} "
        f"symbol={symbol} preset={preset}"
    )
    _set_profile_status(profile_id, "training")

    try:
        # Find the most recent xgboost and tft models for this profile
        async def _find_sub_models():
            async with _aio.connect(str(_DB_PATH)) as db:
                db.row_factory = _aio.Row

                xgb_cursor = await db.execute(
                    """SELECT file_path FROM models
                       WHERE profile_id = ? AND model_type = 'xgboost' AND status = 'ready'
                       ORDER BY created_at DESC LIMIT 1""",
                    (profile_id,),
                )
                xgb_row = await xgb_cursor.fetchone()

                tft_cursor = await db.execute(
                    """SELECT file_path FROM models
                       WHERE profile_id = ? AND model_type = 'tft' AND status = 'ready'
                       ORDER BY created_at DESC LIMIT 1""",
                    (profile_id,),
                )
                tft_row = await tft_cursor.fetchone()

                return (
                    xgb_row["file_path"] if xgb_row else None,
                    tft_row["file_path"] if tft_row else None,
                )

        xgb_path, tft_dir = _asyncio.run(_find_sub_models())

        if not xgb_path:
            msg = (
                f"_ensemble_train_job: no trained xgboost model found for profile "
                f"{profile_id}. Train xgboost first."
            )
            logger.error(msg)
            _set_profile_status(profile_id, "ready")
            with _active_jobs_lock:
                _active_jobs.discard(profile_id)
            return

        if not tft_dir:
            msg = (
                f"_ensemble_train_job: no trained TFT model found for profile "
                f"{profile_id}. Train TFT first."
            )
            logger.error(msg)
            _set_profile_status(profile_id, "ready")
            with _active_jobs_lock:
                _active_jobs.discard(profile_id)
            return

        logger.info(f"  XGBoost model: {xgb_path}")
        logger.info(f"  TFT model dir: {tft_dir}")

        from ml.ensemble_predictor import EnsemblePredictor
        predictor = EnsemblePredictor()
        result = predictor.train_meta_learner(
            profile_id=profile_id,
            symbol=symbol,
            preset=preset,
            xgb_model_path=xgb_path,
            tft_model_dir=tft_dir,
            prediction_horizon=horizon,
            years_of_data=years,
        )

        if result.get("status") == "ready":
            xgb_w = result.get("xgb_weight")
            tft_w = result.get("tft_weight")
            logger.info(
                f"_ensemble_train_job: completed for profile={profile_id} "
                f"model_id={result.get('model_id')} "
                f"xgb_weight={f'{xgb_w:.3f}' if isinstance(xgb_w, (int, float)) else 'N/A'} "
                f"tft_weight={f'{tft_w:.3f}' if isinstance(tft_w, (int, float)) else 'N/A'}"
            )
            _extract_and_persist_importance(
                model_id=result["model_id"],
                model_type="ensemble",
                model_path=result["model_path"],
            )
        else:
            logger.error(f"_ensemble_train_job: unexpected result: {result}")
            _set_profile_status(profile_id, "ready")  # Restore ready (sub-models still exist)

    except Exception as e:
        logger.error(
            f"_ensemble_train_job: exception for profile={profile_id}: {e}",
            exc_info=True,
        )
        _set_profile_status(profile_id, "ready")
    finally:
        _remove_training_logger(log_handler)
        with _active_jobs_lock:
            _active_jobs.discard(profile_id)
        logger.info(f"_ensemble_train_job: job slot released for profile={profile_id}")


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

    # Extract training params from profile
    import json as _json
    symbols = _json.loads(row["symbols"])
    symbol = symbols[0] if symbols else "TSLA"
    preset = row["preset"]

    from config import PRESET_DEFAULTS
    horizon = PRESET_DEFAULTS.get(preset, {}).get("prediction_horizon", "5d")
    years = body.years_of_data or 6

    # Validate model_type BEFORE claiming the job slot
    model_type = (body.model_type or "xgboost").lower()
    if model_type not in ("xgboost", "tft", "ensemble"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model_type '{model_type}'. Must be 'xgboost', 'tft', or 'ensemble'.",
        )

    # Verify Theta Terminal is reachable (fast fail before spawning thread)
    await asyncio.to_thread(_check_theta_or_raise)

    # Check for and claim job slot AFTER validation passes
    with _active_jobs_lock:
        if profile_id in _active_jobs:
            raise HTTPException(
                status_code=409,
                detail=f"Training already in progress for profile {profile_id}. Poll /status to track.",
            )
        _active_jobs.add(profile_id)

    # Select training job based on model type
    job_targets = {
        "xgboost":  (_full_train_job,      f"train-{profile_id[:8]}"),
        "tft":      (_tft_train_job,       f"tft-{profile_id[:8]}"),
        "ensemble": (_ensemble_train_job,  f"ens-{profile_id[:8]}"),
    }
    job_fn, thread_name = job_targets[model_type]

    logger.info(
        f"Spawning {model_type} training thread: profile={profile_id} "
        f"symbol={symbol} preset={preset} horizon={horizon} years={years}"
    )

    thread = threading.Thread(
        target=job_fn,
        args=(profile_id, symbol, preset, horizon, years),
        daemon=True,
        name=thread_name,
    )
    thread.start()

    type_durations = {
        "xgboost": "5-15 minutes",
        "tft": "20-60 minutes",
        "ensemble": "30-90 minutes (requires existing XGBoost + TFT models)",
    }

    return TrainingStatus(
        model_id=None,
        profile_id=profile_id,
        status="training",
        progress_pct=0.0,
        message=(
            f"{model_type.upper()} training started for {symbol} ({preset}, {years}yr). "
            f"Poll GET /api/models/{profile_id}/status for updates. "
            f"Typical duration: {type_durations[model_type]}."
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

    # Verify Theta Terminal is reachable (fast fail before spawning thread)
    await asyncio.to_thread(_check_theta_or_raise)

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
        feature_importance=metrics.get("feature_importance"),
    )


# -------------------------------------------------------------------------
# GET /api/models/{profile_id}/importance — Feature importance
# -------------------------------------------------------------------------
@router.get("/{profile_id}/importance")
async def get_feature_importance(
    profile_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Get feature importance for a profile's most recent model.

    Returns the top features by importance score, stored in the metrics JSON
    during training. Does NOT load the model file — reads from DB only.

    Returns:
        Dict with keys:
            model_id: str
            model_type: str
            feature_importance: dict (feature_name -> score, top 30)
        Or 404 if no model exists.
        Or empty feature_importance dict if importance not yet extracted.
    """
    logger.info(f"GET /api/models/{profile_id}/importance")

    cursor = await db.execute(
        "SELECT id, model_type, metrics FROM models "
        "WHERE profile_id = ? AND status = 'ready' "
        "ORDER BY created_at DESC LIMIT 1",
        (profile_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No ready model found for profile {profile_id}",
        )

    metrics = json.loads(row["metrics"]) if row["metrics"] else {}
    importance = metrics.get("feature_importance", {})

    return {
        "model_id": row["id"],
        "model_type": row["model_type"],
        "feature_importance": importance,
    }


# -------------------------------------------------------------------------
# GET /api/models/{profile_id}/logs — Training log stream
# -------------------------------------------------------------------------
@router.delete("/{profile_id}/logs")
async def clear_training_logs(
    profile_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Clear all training log entries for a profile."""
    logger.info(f"DELETE /api/models/{profile_id}/logs")
    await db.execute(
        "DELETE FROM training_logs WHERE profile_id = ?",
        (profile_id,),
    )
    await db.commit()
    return {"status": "ok", "message": "Training logs cleared"}


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
        """SELECT * FROM training_logs
           WHERE profile_id = ?
           ORDER BY timestamp DESC LIMIT ?""",
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

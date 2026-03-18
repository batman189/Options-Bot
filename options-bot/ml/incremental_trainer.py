"""
Incremental model retraining — update an existing model with new data only.
Matches PROJECT_ARCHITECTURE.md Section 13 Phase 2, item 4.

How it works:
    1. Load the existing model and its metadata from the database
    2. Determine the last training date from the model record
    3. Fetch only new data since that date (plus a lookback buffer for features)
    4. Compute features on the new data
    5. Continue training the existing XGBoost booster using xgb_model warm-start
    6. Save as a new versioned model file (original is never overwritten)
    7. Update the database: new model record + link profile to new model

XGBoost warm-start note:
    XGBRegressor.fit(X, y, xgb_model=existing_booster) continues adding trees
    to the existing booster rather than restarting from scratch. The number of
    new trees added is controlled by n_estimators in the new fit call.
    This is much faster than full retraining and preserves learned patterns.

Minimum new data requirement:
    At least MIN_NEW_SAMPLES daily observations are required to retrain.
    If insufficient new data is available, the function returns early with
    status="skipped" and a clear reason message.
"""

import json
import uuid
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, accuracy_score
from xgboost import XGBRegressor, XGBClassifier
import joblib
import aiosqlite
import asyncio

import sys
# Add project root to sys.path — no setup.py/pyproject.toml in this project
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MODELS_DIR, DB_PATH, PRESET_DEFAULTS
from ml.xgboost_predictor import XGBoostPredictor
from ml.trainer import (
    _get_feature_names,
    _compute_all_features,
    _calculate_target,
    _prediction_horizon_to_bars,
)

logger = logging.getLogger("options-bot.ml.incremental_trainer")

# Minimum new daily observations required to proceed with retraining
MIN_NEW_SAMPLES = 30

# Number of lookback days to fetch before the new data start date.
# Required so rolling-window features (e.g., 20-day SMA) are fully populated
# at the start of the new data window.
LOOKBACK_BUFFER_DAYS = 60

# Number of new trees to add during incremental update
INCREMENTAL_N_ESTIMATORS = 100


def _run_async(coro):
    """Run an async coroutine synchronously."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # If there's already a running loop (e.g., called from background thread),
        # use a thread pool to run in a fresh loop
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=60)
        except Exception as e:
            logger.error(f"_run_async fallback failed: {e}", exc_info=True)
            return None
    except Exception as e:
        logger.error(f"_run_async failed: {e}", exc_info=True)
        return None


def _load_model_record(model_id: str, db_path: str) -> Optional[dict]:
    """
    Load a model record from the database.

    Returns a dict with keys: id, profile_id, file_path, metrics,
    feature_names, hyperparameters, data_end_date, or None if not found.
    """
    logger.info(f"_load_model_record: loading model {model_id}")

    async def _load():
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM models WHERE id = ?", (model_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    logger.error(f"_load_model_record: model {model_id} not found")
                    return None
                return dict(row)
        except Exception as e:
            logger.error(f"_load_model_record DB error: {e}", exc_info=True)
            return None

    return _run_async(_load())


def _get_profile_model_id(profile_id: str, db_path: str) -> Optional[str]:
    """
    Get the current model_id for a profile from the database.
    Returns None if the profile has no model.
    """
    logger.info(f"_get_profile_model_id: profile_id={profile_id}")

    async def _load():
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT model_id FROM profiles WHERE id = ?", (profile_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    logger.error(f"_get_profile_model_id: profile {profile_id} not found")
                    return None
                model_id = row["model_id"]
                logger.info(f"_get_profile_model_id: model_id={model_id}")
                return model_id
        except Exception as e:
            logger.error(f"_get_profile_model_id DB error: {e}", exc_info=True)
            return None

    return _run_async(_load())


def _save_incremental_model_to_db(
    new_model_id: str,
    profile_id: str,
    model_path: str,
    preset: str,
    symbol: str,
    data_start_date: str,
    data_end_date: str,
    metrics: dict,
    feature_names: list,
    hyperparams: dict,
    started_at: str,
    db_path: str,
    model_type: str = "xgboost",
):
    """
    Insert a new model record and update the profile to point to it.
    The old model record is left in place for audit history.
    """
    logger.info(
        f"_save_incremental_model_to_db: new_model_id={new_model_id} "
        f"profile_id={profile_id}"
    )

    async def _save():
        try:
            now = datetime.now(timezone.utc).isoformat()
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    """INSERT INTO models
                       (id, profile_id, model_type, file_path, status,
                        training_started_at, training_completed_at,
                        data_start_date, data_end_date,
                        metrics, feature_names, hyperparameters, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        new_model_id, profile_id, model_type, model_path,
                        "ready", started_at, now,
                        data_start_date, data_end_date,
                        json.dumps(metrics),
                        json.dumps(feature_names),
                        json.dumps(hyperparams),
                        now,
                    ),
                )
                # Update profile to point to the new model
                await db.execute(
                    "UPDATE profiles SET model_id = ?, status = 'ready', updated_at = ? WHERE id = ?",
                    (new_model_id, now, profile_id),
                )
                await db.commit()
                logger.info(
                    f"_save_incremental_model_to_db: committed "
                    f"model={new_model_id} profile={profile_id}"
                )
                return True  # Distinguish success from _run_async failure (which returns None)
        except Exception as e:
            logger.error(
                f"_save_incremental_model_to_db DB error: {e}", exc_info=True
            )
            raise

    db_result = _run_async(_save())
    if db_result is None:
        logger.error(
            f"_save_incremental_model_to_db: async save returned None — "
            f"model file exists at {model_path} but has no DB record. "
            f"Profile status may be stuck at 'training'. Attempting synchronous fallback..."
        )
        # Synchronous fallback using sqlite3 to prevent orphaned state
        try:
            import sqlite3
            now = datetime.now(timezone.utc).isoformat()
            conn = sqlite3.connect(db_path, timeout=10)
            conn.execute(
                """INSERT INTO models
                   (id, profile_id, model_type, file_path, status,
                    training_started_at, training_completed_at,
                    data_start_date, data_end_date,
                    metrics, feature_names, hyperparameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_model_id, profile_id, "xgboost", model_path,
                    "ready", started_at, now,
                    data_start_date, data_end_date,
                    json.dumps(metrics),
                    json.dumps(feature_names),
                    json.dumps(hyperparams),
                    now,
                ),
            )
            conn.execute(
                "UPDATE profiles SET model_id = ?, status = 'ready', updated_at = ? WHERE id = ?",
                (new_model_id, now, profile_id),
            )
            conn.commit()
            conn.close()
            logger.info("  Synchronous DB fallback succeeded")
        except Exception as fallback_err:
            logger.error(f"  Synchronous DB fallback also failed: {fallback_err}", exc_info=True)


def retrain_incremental(
    profile_id: str,
    symbol: str,
    preset: str,
    prediction_horizon: str = "5d",
    db_path: str = None,
) -> dict:
    """
    Incrementally update an existing model with new data since its last training date.

    Args:
        profile_id: UUID of the profile whose model to update.
        symbol: Ticker symbol (e.g., "TSLA").
        preset: Trading preset ("swing" or "general").
        prediction_horizon: Forward return horizon string (e.g., "5d").
        db_path: Override DB path (for testing).

    Returns:
        Dict with keys:
            status: "updated", "skipped", or "error"
            message: Human-readable reason
            new_model_id: UUID of new model (only if status="updated")
            new_model_path: Path to new model file (only if status="updated")
            metrics: Evaluation metrics on new data (only if status="updated")
            new_samples: Number of new daily observations used
    """
    started_at = datetime.now(timezone.utc).isoformat()
    pipeline_start = time.time()
    db_path = db_path or str(DB_PATH)

    logger.info("=" * 70)
    logger.info("INCREMENTAL RETRAINING START")
    logger.info(f"  Profile:  {profile_id}")
    logger.info(f"  Symbol:   {symbol}")
    logger.info(f"  Preset:   {preset}")
    logger.info(f"  Horizon:  {prediction_horizon}")
    logger.info("=" * 70)

    # =========================================================================
    # STEP 1: Load current model metadata from DB
    # =========================================================================
    logger.info("")
    logger.info("STEP 1: Loading current model metadata from database")
    logger.info("-" * 50)

    model_id = _get_profile_model_id(profile_id, db_path)
    if not model_id:
        msg = f"Profile {profile_id} has no model. Run full training first."
        logger.error(msg)
        return {"status": "error", "message": msg}

    model_record = _load_model_record(model_id, db_path)
    if not model_record:
        msg = f"Model record {model_id} not found in database."
        logger.error(msg)
        return {"status": "error", "message": msg}

    existing_model_path = model_record["file_path"]
    last_data_end = model_record.get("data_end_date")
    model_type = model_record.get("model_type", "xgboost")
    is_classifier = model_type in ("xgb_classifier", "xgb_swing_classifier", "lgbm_classifier")
    is_lgbm = model_type == "lgbm_classifier"

    logger.info(f"  Existing model: {existing_model_path}")
    logger.info(f"  Model type: {model_type} (classifier={is_classifier})")
    logger.info(f"  Last training data end: {last_data_end}")

    if not last_data_end:
        msg = "Model record has no data_end_date. Cannot determine new data window."
        logger.error(msg)
        return {"status": "error", "message": msg}

    if not Path(existing_model_path).exists():
        msg = f"Model file not found on disk: {existing_model_path}"
        logger.error(msg)
        return {"status": "error", "message": msg}

    # =========================================================================
    # STEP 2: Determine new data date range
    # =========================================================================
    logger.info("")
    logger.info("STEP 2: Determining new data date range")
    logger.info("-" * 50)

    try:
        last_end_dt = datetime.strptime(last_data_end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        # Handle ISO datetime format if stored that way
        parsed = datetime.fromisoformat(last_data_end.split("T")[0])
        last_end_dt = parsed.replace(tzinfo=timezone.utc)

    # New data starts the day after the last training date
    new_data_start = last_end_dt + timedelta(days=1)
    new_data_end = datetime.now(timezone.utc) - timedelta(hours=1)

    if new_data_start >= new_data_end:
        msg = (
            f"No new data available. Last training ended {last_data_end}, "
            f"which is already current."
        )
        logger.info(msg)
        return {"status": "skipped", "message": msg, "new_samples": 0}

    # Fetch with lookback buffer so rolling features are populated at window start
    fetch_start = new_data_start - timedelta(days=LOOKBACK_BUFFER_DAYS)

    logger.info(f"  New data window: {new_data_start.date()} to {new_data_end.date()}")
    logger.info(f"  Fetch start (with {LOOKBACK_BUFFER_DAYS}d buffer): {fetch_start.date()}")

    # =========================================================================
    # STEP 3: Fetch new bars from Alpaca
    # =========================================================================
    logger.info("")
    logger.info("STEP 3: Fetching new bars from Alpaca")
    logger.info("-" * 50)

    try:
        from data.alpaca_provider import AlpacaStockProvider
        provider = AlpacaStockProvider()
        bars_df = provider.get_historical_bars(
            symbol, fetch_start, new_data_end, timeframe="5min"
        )
    except Exception as e:
        msg = f"Failed to fetch bars from Alpaca: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    if bars_df is None or bars_df.empty:
        msg = f"No bars returned from Alpaca for {symbol} since {fetch_start.date()}"
        logger.warning(msg)
        return {"status": "skipped", "message": msg, "new_samples": 0}

    # Tag bars_df with symbol so options fetcher can use it
    bars_df.attrs["symbol"] = symbol

    logger.info(f"  Fetched {len(bars_df)} bars")

    # =========================================================================
    # STEP 4: Compute features
    # =========================================================================
    logger.info("")
    logger.info("STEP 4: Computing features")
    logger.info("-" * 50)

    try:
        featured_df = _compute_all_features(bars_df.copy(), preset)
        logger.info(
            f"  Features computed: {len(featured_df)} rows, "
            f"{len(featured_df.columns)} columns"
        )
    except Exception as e:
        msg = f"Feature computation failed: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    # =========================================================================
    # STEP 5: Calculate forward return target
    # =========================================================================
    logger.info("")
    logger.info("STEP 5: Calculating forward return target")
    logger.info("-" * 50)

    preset_config = PRESET_DEFAULTS.get(preset, {})
    bar_granularity = preset_config.get("bar_granularity", "5min")
    horizon_bars = _prediction_horizon_to_bars(prediction_horizon, bar_granularity=bar_granularity)

    # Use feature names from the existing model record (not from code) to ensure
    # the incremental training uses the same feature set as the original model.
    # This prevents column mismatch if feature engineering code has changed.
    model_feature_names = model_record.get("feature_names")
    if model_feature_names and isinstance(model_feature_names, str):
        feature_names = json.loads(model_feature_names)
    elif model_feature_names and isinstance(model_feature_names, list):
        feature_names = model_feature_names
    else:
        logger.warning("  Model record has no feature_names, falling back to code definition")
        feature_names = _get_feature_names(preset)

    try:
        if is_classifier:
            # Classifier models need binary labels (0=DOWN, 1=UP).
            # Pull neutral_band_pct from the stored hyperparameters so we use
            # exactly the same band the original full training used.
            hp = model_record.get("hyperparameters") or {}
            if isinstance(hp, str):
                import json as _json
                hp = _json.loads(hp)
            neutral_band_pct = float(hp.get("neutral_band_pct", 0.30))
            stored_horizon_bars = int(hp.get("horizon_bars", horizon_bars))

            future_close = featured_df["close"].shift(-stored_horizon_bars)
            forward_return_pct = ((future_close / featured_df["close"]) - 1) * 100
            target = pd.Series(np.nan, index=featured_df.index)
            target[forward_return_pct < -neutral_band_pct] = 0  # DOWN
            target[forward_return_pct > neutral_band_pct] = 1   # UP
            featured_df["_target"] = target
            logger.info(
                f"  Classifier target: binary (neutral_band=±{neutral_band_pct}%, "
                f"horizon={stored_horizon_bars} bars, {int((target == 0).sum())} DOWN, "
                f"{int((target == 1).sum())} UP, {int(target.isna().sum())} neutral dropped)"
            )
        else:
            target = _calculate_target(featured_df, horizon_bars)
            featured_df["_target"] = target
    except Exception as e:
        msg = f"Target calculation failed: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    # =========================================================================
    # STEP 6: Filter to new data only + drop NaN
    # =========================================================================
    logger.info("")
    logger.info("STEP 6: Preparing training data")
    logger.info("-" * 50)

    logger.info(f"  Total bars with features: {len(featured_df)}")

    # Filter to only rows AFTER the lookback buffer window
    # (buffer rows were only needed to warm up rolling features)
    try:
        ts = pd.Timestamp(new_data_start)
        if featured_df.index.tz is not None:
            if ts.tz is not None:
                new_data_start_tz = ts.tz_convert(featured_df.index.tz)
            else:
                new_data_start_tz = ts.tz_localize(featured_df.index.tz)
        else:
            new_data_start_tz = ts

        new_only_df = featured_df[featured_df.index >= new_data_start_tz]
        logger.info(
            f"  After filtering to new data only: {len(new_only_df)} observations "
            f"(removed {len(featured_df) - len(new_only_df)} lookback buffer rows)"
        )
    except Exception as e:
        logger.warning(
            f"  Date filtering failed ({e}), using all rows"
        )
        new_only_df = featured_df

    # Drop rows with NaN target. For features, only drop rows where ALL features
    # are NaN (same logic as full trainer). XGBoost handles individual NaN features
    # natively via default split directions, so partial NaN (e.g. options features
    # when Theta Terminal is down) is acceptable.
    cols_needed = feature_names + ["_target"]
    existing_cols = [c for c in cols_needed if c in new_only_df.columns]
    new_only_df = new_only_df[existing_cols].dropna(subset=["_target"])
    feat_cols_present = [c for c in feature_names if c in new_only_df.columns]
    if feat_cols_present:
        all_nan_mask = new_only_df[feat_cols_present].isna().all(axis=1)
        new_only_df = new_only_df[~all_nan_mask]

    logger.info(f"  After dropping NaN: {len(new_only_df)} usable observations")

    if len(new_only_df) < MIN_NEW_SAMPLES:
        msg = (
            f"Insufficient new data: {len(new_only_df)} observations "
            f"(minimum required: {MIN_NEW_SAMPLES}). "
            f"Try again after more trading days have passed."
        )
        logger.info(msg)
        return {
            "status": "skipped",
            "message": msg,
            "new_samples": len(new_only_df),
        }

    # Build X and y
    X_new = new_only_df.reindex(columns=feature_names)
    y_new = new_only_df["_target"]

    actual_data_start = str(new_only_df.index.min().date())
    actual_data_end = str(new_only_df.index.max().date())

    logger.info(
        f"  Training window: {actual_data_start} to {actual_data_end} "
        f"({len(X_new)} samples)"
    )

    # =========================================================================
    # STEP 7: Load existing model and continue training (warm start)
    # =========================================================================
    logger.info("")
    logger.info("STEP 7: Loading existing model and continuing training")
    logger.info("-" * 50)

    try:
        existing_data = joblib.load(existing_model_path)
        existing_model_obj = existing_data["model"]
        logger.info(
            f"  Loaded existing model from {existing_model_path} "
            f"(type: {type(existing_model_obj).__name__})"
        )
    except Exception as e:
        msg = f"Failed to load existing model from disk: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    # Split holdout BEFORE training to avoid evaluating on in-sample data (H5 fix)
    holdout_size = max(1, int(len(X_new) * 0.2))
    X_train_split = X_new.iloc[:-holdout_size]
    y_train_split = y_new.iloc[:-holdout_size]
    X_holdout = X_new.iloc[-holdout_size:]
    y_holdout = y_new.iloc[-holdout_size:]

    logger.info(
        f"  Train/holdout split: {len(X_train_split)} train, {holdout_size} holdout"
    )

    try:
        if is_lgbm:
            # LightGBM warm-start: pass existing booster via init_model parameter.
            # LGBMClassifier.fit(init_model=...) continues from the existing booster.
            from lightgbm import LGBMClassifier
            existing_lgbm_booster = (
                existing_model_obj.booster_
                if hasattr(existing_model_obj, "booster_")
                else existing_model_obj
            )
            # Copy hyperparams from existing model so we don't drift
            params = existing_model_obj.get_params() if hasattr(existing_model_obj, "get_params") else {}
            params["n_estimators"] = INCREMENTAL_N_ESTIMATORS
            incremental_model = LGBMClassifier(**params)
            incremental_model.fit(
                X_train_split, y_train_split,
                init_model=existing_lgbm_booster,
            )
            logger.info(
                f"  LightGBM warm-start complete: added {INCREMENTAL_N_ESTIMATORS} new trees"
            )

        elif is_classifier:
            # XGBoost classifier warm-start (xgb_classifier / xgb_swing_classifier)
            if hasattr(existing_model_obj, "get_booster"):
                existing_booster = existing_model_obj.get_booster()
            else:
                existing_booster = existing_model_obj
            incremental_model = XGBClassifier(
                n_estimators=INCREMENTAL_N_ESTIMATORS,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=5,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                n_jobs=-1,
                verbosity=0,
                use_label_encoder=False,
                eval_metric="logloss",
            )
            incremental_model.fit(
                X_train_split, y_train_split,
                xgb_model=existing_booster,
                verbose=False,
            )
            logger.info(
                f"  XGBClassifier warm-start complete: added {INCREMENTAL_N_ESTIMATORS} new trees"
            )

        else:
            # XGBoost regression warm-start (original path)
            if hasattr(existing_model_obj, "get_booster"):
                existing_booster = existing_model_obj.get_booster()
            else:
                existing_booster = existing_model_obj
            incremental_model = XGBRegressor(
                n_estimators=INCREMENTAL_N_ESTIMATORS,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=5,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            )
            incremental_model.fit(
                X_train_split, y_train_split,
                xgb_model=existing_booster,
                verbose=False,
            )
            logger.info(
                f"  XGBRegressor warm-start complete: added {INCREMENTAL_N_ESTIMATORS} new trees"
            )

    except Exception as e:
        msg = f"Incremental training failed: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    # =========================================================================
    # STEP 8: Evaluate on holdout portion of new data (out-of-sample)
    # =========================================================================
    logger.info("")
    logger.info("STEP 8: Evaluating updated model on holdout data (out-of-sample)")
    logger.info("-" * 50)

    try:
        if is_classifier:
            # Classifier evaluation: accuracy and directional accuracy
            preds_class = incremental_model.predict(X_holdout.values)
            acc = float(accuracy_score(y_holdout, preds_class))
            dir_acc = acc  # For binary classifiers these are the same
            metrics = {
                "accuracy": acc,
                "dir_acc": dir_acc,
                "training_samples": len(X_train_split),
                "holdout_samples": holdout_size,
                "incremental": True,
                "trees_added": INCREMENTAL_N_ESTIMATORS,
            }
            logger.info(f"  Accuracy={acc:.4f} on holdout")
            if acc < 0.50:
                logger.warning(
                    f"  Accuracy {acc:.4f} < 0.50 on new data — "
                    f"model may be degrading. Review before deploying."
                )
            else:
                logger.info(f"  Accuracy {acc:.4f} >= 0.50 on new data. OK.")
        else:
            # Regression evaluation: MAE, RMSE, R2, directional accuracy
            preds = incremental_model.predict(X_holdout.values)
            mae = float(mean_absolute_error(y_holdout, preds))
            rmse = float(np.sqrt(mean_squared_error(y_holdout, preds)))
            r2 = float(r2_score(y_holdout, preds))
            dir_acc = float(((y_holdout > 0) == (preds > 0)).mean())
            metrics = {
                "mae": mae,
                "rmse": rmse,
                "r2": r2,
                "dir_acc": dir_acc,
                "training_samples": len(X_train_split),
                "holdout_samples": holdout_size,
                "incremental": True,
                "trees_added": INCREMENTAL_N_ESTIMATORS,
            }
            logger.info(
                f"  MAE={mae:.4f}, RMSE={rmse:.4f}, "
                f"R2={r2:.4f}, DirAcc={dir_acc:.4f}"
            )
            if dir_acc < 0.50:
                logger.warning(
                    f"  DirAcc {dir_acc:.4f} < 0.50 on new data — "
                    f"model may be degrading. Review before deploying."
                )
            else:
                logger.info(f"  DirAcc {dir_acc:.4f} >= 0.50 on new data. OK.")
    except Exception as e:
        msg = f"Evaluation failed: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    # =========================================================================
    # STEP 9: Save updated model as new versioned file
    # =========================================================================
    logger.info("")
    logger.info("STEP 9: Saving updated model to disk")
    logger.info("-" * 50)

    new_model_id = str(uuid.uuid4())
    new_model_filename = (
        f"{profile_id}_{preset}_{symbol}_{new_model_id[:8]}_incremental.joblib"
    )
    new_model_path = str(MODELS_DIR / new_model_filename)

    try:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        if is_lgbm:
            from ml.lgbm_predictor import LightGBMPredictor
            predictor = LightGBMPredictor()
            predictor.set_model(incremental_model, feature_names)
            predictor.save(new_model_path, feature_names)
        elif model_type == "xgb_swing_classifier":
            from ml.swing_classifier_predictor import SwingClassifierPredictor
            predictor = SwingClassifierPredictor()
            predictor.set_model(incremental_model, feature_names)
            predictor.save(new_model_path, feature_names)
        elif model_type == "xgb_classifier":
            from ml.scalp_predictor import ScalpPredictor
            predictor = ScalpPredictor()
            predictor.set_model(incremental_model, feature_names)
            predictor.save(new_model_path, feature_names)
        else:
            predictor = XGBoostPredictor()
            predictor.set_model(incremental_model, feature_names)
            predictor.save(new_model_path, feature_names)
        logger.info(f"  Saved to: {new_model_path} (predictor: {type(predictor).__name__})")
    except Exception as e:
        msg = f"Failed to save updated model: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    # =========================================================================
    # STEP 10: Save to database and update profile
    # =========================================================================
    logger.info("")
    logger.info("STEP 10: Saving to database")
    logger.info("-" * 50)

    hyperparams = {
        "n_estimators_added": INCREMENTAL_N_ESTIMATORS,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "prediction_horizon": prediction_horizon,
        "horizon_bars": horizon_bars,
        "incremental": True,
        "previous_model_id": model_id,
    }

    try:
        _save_incremental_model_to_db(
            new_model_id=new_model_id,
            profile_id=profile_id,
            model_path=new_model_path,
            preset=preset,
            symbol=symbol,
            data_start_date=actual_data_start,
            data_end_date=actual_data_end,
            metrics=metrics,
            feature_names=feature_names,
            hyperparams=hyperparams,
            started_at=started_at,
            db_path=db_path,
            model_type=model_record.get("model_type", "xgboost"),
        )
        logger.info(f"  Database updated: new model_id={new_model_id}")

        # Mark training queue items as consumed now that the retrain succeeded
        try:
            from ml.feedback_queue import consume_pending_samples
            consumed = consume_pending_samples(db_path, profile_id)
            logger.info(f"  Consumed {len(consumed)} training queue sample(s)")
        except Exception as eq:
            logger.warning(f"  Failed to consume training queue (non-fatal): {eq}")

    except Exception as e:
        msg = f"Failed to save model to database: {e}"
        logger.error(msg, exc_info=True)
        # Model file exists on disk — return partial success so caller can
        # decide whether to retry the DB write
        return {
            "status": "error",
            "message": msg,
            "new_model_id": new_model_id,
            "new_model_path": new_model_path,
        }

    # =========================================================================
    # SUMMARY
    # =========================================================================
    total_elapsed = time.time() - pipeline_start

    logger.info("")
    logger.info("=" * 70)
    logger.info("INCREMENTAL RETRAINING COMPLETE")
    logger.info("=" * 70)
    logger.info(f"  New Model ID:  {new_model_id}")
    logger.info(f"  New Model:     {new_model_path}")
    logger.info(f"  Previous:      {existing_model_path}")
    logger.info(f"  New Samples:   {len(X_new)}")
    logger.info(f"  Data Range:    {actual_data_start} to {actual_data_end}")
    logger.info(f"  Trees Added:   {INCREMENTAL_N_ESTIMATORS}")
    logger.info(f"  DirAcc:        {dir_acc:.4f}")
    if not is_classifier:
        logger.info(f"  MAE:           {mae:.4f}")
    logger.info(f"  Total Time:    {total_elapsed:.1f}s")
    logger.info("=" * 70)

    return {
        "status": "updated",
        "message": (
            f"Model updated with {len(X_new)} new observations "
            f"({actual_data_start} to {actual_data_end}). "
            f"Added {INCREMENTAL_N_ESTIMATORS} trees. DirAcc={dir_acc:.4f}."
        ),
        "new_model_id": new_model_id,
        "new_model_path": new_model_path,
        "previous_model_id": model_id,
        "metrics": metrics,
        "new_samples": len(X_new),
        "data_range": f"{actual_data_start} to {actual_data_end}",
        "total_time_seconds": total_elapsed,
    }

"""
LightGBM training pipeline.
Phase C — ML Accuracy Improvements.

Same pipeline structure as trainer.py (XGBoost) but trains a LightGBM model.
Reuses data fetching, feature engineering, and CV from the XGBoost trainer.
"""

import json
import uuid
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

import sys
# Add project root to sys.path — no setup.py/pyproject.toml in this project
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MODELS_DIR, PRESET_DEFAULTS, DB_PATH
from ml.lgbm_predictor import LightGBMPredictor
from ml.trainer import (
    _prediction_horizon_to_bars,
    _get_feature_names,
    _compute_all_features,
    _calculate_target,
    MIN_TRAINING_SAMPLES,
    CV_FOLDS,
)

logger = logging.getLogger("options-bot.ml.lgbm_trainer")


def _walk_forward_cv_lgbm(X: pd.DataFrame, y: pd.Series) -> dict:
    """Walk-forward cross-validation using LightGBM."""
    try:
        import lightgbm as lgb
    except ImportError:
        logger.error("lightgbm not installed. pip install lightgbm>=4.0.0")
        return {}

    n = len(X)
    fold_size = n // (CV_FOLDS + 1)
    if fold_size < 50:
        logger.warning(f"Very small fold size: {fold_size}")

    all_mae, all_rmse, all_r2, all_dir = [], [], [], []
    fold_details = []

    for fold in range(CV_FOLDS):
        train_end = fold_size * (fold + 1)
        test_start = train_end
        test_end = min(train_end + fold_size, n)

        if test_end <= test_start:
            continue

        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]
        X_test = X.iloc[test_start:test_end]
        y_test = y.iloc[test_start:test_end]

        model = lgb.LGBMRegressor(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_samples=20,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        model.fit(X_train, y_train)

        preds = model.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
        r2 = r2_score(y_test, preds)
        dir_acc = float(((y_test > 0) == (preds > 0)).mean())

        all_mae.append(mae)
        all_rmse.append(rmse)
        all_r2.append(r2)
        all_dir.append(dir_acc)

        fold_details.append({
            "fold": fold + 1,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "r2": round(r2, 4),
            "dir_acc": round(dir_acc, 4),
        })
        logger.info(
            f"  Fold {fold+1}/{CV_FOLDS}: "
            f"train={len(X_train)} test={len(X_test)} "
            f"MAE={mae:.4f} RMSE={rmse:.4f} R²={r2:.4f} DirAcc={dir_acc:.4f}"
        )

    if not all_mae:
        return {}

    return {
        "mae": round(float(np.mean(all_mae)), 4),
        "rmse": round(float(np.mean(all_rmse)), 4),
        "r2": round(float(np.mean(all_r2)), 4),
        "dir_acc": round(float(np.mean(all_dir)), 4),
        "cv_folds": CV_FOLDS,
        "fold_details": fold_details,
    }


def train_lgbm_model(
    profile_id: str,
    symbol: str,
    preset: str = "swing",
    prediction_horizon: str = "5d",
    years_of_data: int = 6,
    db_path: str = None,
    data_end_override: datetime = None,
) -> dict:
    """
    Full LightGBM training pipeline.

    Same structure as train_model() in trainer.py but uses LightGBM.

    Returns:
        dict with status, model_id, model_path, metrics, etc.
    """
    try:
        import lightgbm as lgb
    except ImportError:
        return {"status": "failed", "message": "lightgbm not installed. pip install lightgbm>=4.0.0"}

    pipeline_start = time.time()
    db_path = db_path or str(DB_PATH)
    model_id = str(uuid.uuid4())
    model_filename = f"{profile_id}_lgbm_{symbol}_{model_id[:8]}.joblib"
    model_path = str(MODELS_DIR / model_filename)

    logger.info("=" * 70)
    logger.info("LIGHTGBM TRAINING PIPELINE START")
    logger.info(f"  Profile: {profile_id}")
    logger.info(f"  Symbol: {symbol}")
    logger.info(f"  Preset: {preset}")
    logger.info(f"  Horizon: {prediction_horizon}")
    logger.info(f"  Years: {years_of_data}")
    logger.info(f"  Model ID: {model_id}")
    logger.info("=" * 70)

    preset_config = PRESET_DEFAULTS.get(preset, {})
    bar_granularity = preset_config.get("bar_granularity", "5min")
    horizon_bars = _prediction_horizon_to_bars(prediction_horizon, bar_granularity=bar_granularity)
    feature_names = _get_feature_names(preset)

    # STEP 1: Fetch historical stock bars
    logger.info("")
    logger.info("STEP 1: Fetching historical stock bars from Alpaca")
    logger.info("-" * 50)

    from data.alpaca_provider import AlpacaStockProvider
    stock_provider = AlpacaStockProvider()

    end_date = data_end_override if data_end_override else (datetime.now(timezone.utc) - timedelta(hours=1))
    start_date = end_date - timedelta(days=years_of_data * 365 + 30)

    step_start = time.time()
    bars_df = stock_provider.get_historical_bars(symbol, start_date, end_date, bar_granularity)
    step_elapsed = time.time() - step_start

    if bars_df.empty:
        logger.error("FATAL: No bars returned from Alpaca")
        return {"status": "failed", "message": "No stock data available"}

    logger.info(
        f"Step 1 complete: {len(bars_df)} bars in {step_elapsed:.0f}s "
        f"({bars_df.index[0]} to {bars_df.index[-1]})"
    )

    bars_df.attrs["symbol"] = symbol
    data_start_date = bars_df.index[0].strftime("%Y-%m-%d")
    data_end_date = bars_df.index[-1].strftime("%Y-%m-%d")

    # STEP 2: Compute features
    logger.info("")
    logger.info("STEP 2: Computing features")
    logger.info("-" * 50)

    step_start = time.time()
    featured_df = _compute_all_features(bars_df, preset)
    step_elapsed = time.time() - step_start
    logger.info(f"Step 2 complete: features computed in {step_elapsed:.0f}s")

    # STEP 3: Calculate target
    logger.info("")
    logger.info("STEP 3: Calculating forward return target")
    logger.info("-" * 50)

    featured_df["target"] = _calculate_target(featured_df, horizon_bars)
    total_bars = len(featured_df)
    has_target = featured_df["target"].notna().sum()
    logger.info(f"Target calculated: {has_target}/{total_bars} bars have valid targets")

    # STEP 4: Prepare training data
    logger.info("")
    logger.info("STEP 4: Preparing training data")
    logger.info("-" * 50)

    train_df = featured_df.dropna(subset=["target"])

    missing_features = [f for f in feature_names if f not in train_df.columns]
    if missing_features:
        logger.warning(f"Missing features (will be NaN): {missing_features}")
        train_df = train_df.copy()
        for f in missing_features:
            train_df[f] = np.nan

    X = train_df[feature_names].copy()
    y = train_df["target"].copy()

    valid_mask = X.notna().any(axis=1)
    X = X[valid_mask]
    y = y[valid_mask]

    logger.info(f"Training dataset: {len(X)} samples, {len(feature_names)} features")
    logger.info(f"Target stats: mean={y.mean():.4f}%, std={y.std():.4f}%")

    if len(X) < MIN_TRAINING_SAMPLES:
        logger.error(f"FATAL: Only {len(X)} training samples. Need at least {MIN_TRAINING_SAMPLES}.")
        return {"status": "failed", "message": f"Insufficient training data: {len(X)} samples"}

    # STEP 5: Walk-forward cross-validation
    logger.info("")
    logger.info("STEP 5: Walk-forward cross-validation (LightGBM)")
    logger.info("-" * 50)

    step_start = time.time()
    cv_metrics = _walk_forward_cv_lgbm(X, y)
    step_elapsed = time.time() - step_start
    logger.info(f"Step 5 complete: CV in {step_elapsed:.0f}s")

    if not cv_metrics:
        return {"status": "failed", "message": "Cross-validation failed"}

    dir_acc = cv_metrics.get("dir_acc", 0)
    logger.info(f"CHECKPOINT: Directional Accuracy = {dir_acc:.4f}")

    # STEP 6: Train final model
    logger.info("")
    logger.info("STEP 6: Training final LightGBM model on all data")
    logger.info("-" * 50)

    step_start = time.time()
    final_model = lgb.LGBMRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=20,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    final_model.fit(X, y)
    step_elapsed = time.time() - step_start
    logger.info(f"Step 6 complete: final LightGBM trained in {step_elapsed:.0f}s")

    # STEP 7: Save model
    logger.info("")
    logger.info("STEP 7: Saving LightGBM model to disk")
    logger.info("-" * 50)

    predictor = LightGBMPredictor()
    predictor.set_model(final_model, feature_names)
    predictor.save(model_path, feature_names)

    importance = predictor.get_feature_importance()
    top_10 = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
    logger.info("Top 10 features by importance:")
    for name, imp in top_10:
        logger.info(f"  {name}: {imp:.4f}")

    # STEP 8: Save to database
    logger.info("")
    logger.info("STEP 8: Saving metrics to database")
    logger.info("-" * 50)

    import aiosqlite
    import asyncio
    import concurrent.futures

    def _run_async(coro):
        try:
            return asyncio.run(coro)
        except RuntimeError:
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, coro).result(timeout=60)
            except Exception as e:
                logger.error(f"_run_async fallback failed: {e}", exc_info=True)
                return None
        except Exception as e:
            logger.error(f"_run_async failed: {e}", exc_info=True)
            return None

    cv_metrics["training_samples"] = len(X)
    fold_details = cv_metrics.pop("fold_details", [])

    hyperparams = {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_samples": 20,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "prediction_horizon": prediction_horizon,
        "horizon_bars": horizon_bars,
    }

    now = datetime.now(timezone.utc).isoformat()
    pipeline_start_iso = datetime.fromtimestamp(pipeline_start, tz=timezone.utc).isoformat()

    async def _save_to_db():
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO models
                   (id, profile_id, model_type, file_path, status,
                    training_started_at, training_completed_at,
                    data_start_date, data_end_date,
                    metrics, feature_names, hyperparameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    model_id, profile_id, "lightgbm", model_path, "ready",
                    pipeline_start_iso, now,
                    data_start_date, data_end_date,
                    json.dumps(cv_metrics),
                    json.dumps(feature_names),
                    json.dumps(hyperparams),
                    now,
                ),
            )
            await db.execute(
                "UPDATE profiles SET model_id = ?, status = 'ready', updated_at = ? WHERE id = ?",
                (model_id, now, profile_id),
            )
            await db.commit()
            logger.info("Model and profile updated in database")
            return True  # Distinguish success from _run_async failure (which returns None)

    db_result = _run_async(_save_to_db())
    if db_result is None:
        logger.error(
            "STEP 8 FAILED: Database save returned None — model file exists "
            f"at {model_path} but has no DB record. Profile status may be stuck "
            "at 'training'. Attempting synchronous fallback..."
        )
        # Synchronous fallback using sqlite3 to prevent orphaned state
        try:
            import sqlite3
            conn = sqlite3.connect(db_path, timeout=10)
            conn.execute(
                """INSERT INTO models
                   (id, profile_id, model_type, file_path, status,
                    training_started_at, training_completed_at,
                    data_start_date, data_end_date,
                    metrics, feature_names, hyperparameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    model_id, profile_id, "lightgbm", model_path, "ready",
                    pipeline_start_iso, now,
                    data_start_date, data_end_date,
                    json.dumps(cv_metrics),
                    json.dumps(feature_names),
                    json.dumps(hyperparams),
                    now,
                ),
            )
            conn.execute(
                "UPDATE profiles SET model_id = ?, status = 'ready', updated_at = ? WHERE id = ?",
                (model_id, now, profile_id),
            )
            conn.commit()
            conn.close()
            logger.info("  Synchronous DB fallback succeeded")
        except Exception as fallback_err:
            logger.error(f"  Synchronous DB fallback also failed: {fallback_err}", exc_info=True)

    # SUMMARY
    total_elapsed = time.time() - pipeline_start

    logger.info("")
    logger.info("=" * 70)
    logger.info("LIGHTGBM TRAINING PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"  Model ID:     {model_id}")
    logger.info(f"  Model Path:   {model_path}")
    logger.info(f"  Symbol:       {symbol}")
    logger.info(f"  Preset:       {preset}")
    logger.info(f"  Data Range:   {data_start_date} to {data_end_date}")
    logger.info(f"  Training Samples: {len(X)}")
    logger.info(f"  Features:     {len(feature_names)}")
    logger.info(f"  MAE:          {cv_metrics['mae']:.4f}")
    logger.info(f"  RMSE:         {cv_metrics['rmse']:.4f}")
    logger.info(f"  R\u00b2:           {cv_metrics['r2']:.4f}")
    logger.info(f"  Dir Accuracy: {cv_metrics['dir_acc']:.4f}")
    logger.info(f"  Total Time:   {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")
    logger.info("=" * 70)

    return {
        "status": "ready",
        "model_id": model_id,
        "model_path": model_path,
        "metrics": cv_metrics,
        "feature_names": feature_names,
        "data_range": f"{data_start_date} to {data_end_date}",
        "training_samples": len(X),
        "total_time_seconds": total_elapsed,
    }

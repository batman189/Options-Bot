"""
XGBoost training pipeline.
Matches PROJECT_ARCHITECTURE.md Section 7 — Phase 1-3.

Full pipeline:
    1. Fetch historical stock bars from Alpaca
    2. Compute features (base + style-specific)
    3. Calculate forward return target
    4. Walk-forward cross-validation (5-fold expanding window)
    5. Train final model on all data
    6. Save model + metrics + feature names to DB
    7. Update profile status
"""

import json
import uuid
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MODELS_DIR, PRESET_DEFAULTS, DB_PATH
from ml.xgboost_predictor import XGBoostPredictor
from ml.feature_engineering.base_features import compute_base_features, get_base_feature_names
from ml.feature_engineering.swing_features import compute_swing_features, get_swing_feature_names
from ml.feature_engineering.general_features import compute_general_features, get_general_feature_names
from ml.feature_engineering.scalp_features import compute_scalp_features, get_scalp_feature_names

logger = logging.getLogger("options-bot.ml.trainer")

# Walk-forward CV folds
CV_FOLDS = 5

# Minimum samples required to train
MIN_TRAINING_SAMPLES = 200


def _prediction_horizon_to_bars(horizon: str, bar_granularity: str = "5min") -> int:
    """Convert prediction horizon string to number of bars.

    Args:
        horizon: Prediction horizon string (e.g., "5d", "30min")
        bar_granularity: Bar size — "1min" or "5min" (default)
    """
    if bar_granularity == "1min":
        bars_per_day = 390
        mapping = {
            "30min": 30,
            "1d": bars_per_day,
            "3d": bars_per_day * 3,
            "5d": bars_per_day * 5,
            "7d": bars_per_day * 7,
            "10d": bars_per_day * 10,
        }
    else:
        bars_per_day = 78
        mapping = {
            "30min": 6,
            "1d": bars_per_day,
            "3d": bars_per_day * 3,
            "5d": bars_per_day * 5,
            "7d": bars_per_day * 7,
            "10d": bars_per_day * 10,
        }
    if horizon not in mapping:
        raise ValueError(f"Unknown prediction horizon: {horizon}. Supported: {list(mapping.keys())}")
    return mapping[horizon]


def _get_feature_names(preset: str) -> list[str]:
    """Get the full list of feature names for a preset."""
    base = get_base_feature_names()
    if preset == "swing":
        return base + get_swing_feature_names()
    elif preset == "general":
        return base + get_general_feature_names()
    elif preset == "scalp":
        return base + get_scalp_feature_names()
    else:
        return base


def _compute_all_features(bars_df: pd.DataFrame, preset: str) -> pd.DataFrame:
    """Compute base + style-specific features, including options data from Theta."""
    logger.info(f"Computing all features for preset '{preset}'")
    start = time.time()

    # Fetch options data from Theta Terminal (if available)
    options_daily_df = None
    try:
        from data.options_data_fetcher import fetch_options_for_training
        preset_config = PRESET_DEFAULTS.get(preset, {})
        options_daily_df = fetch_options_for_training(
            symbol=bars_df.attrs.get("symbol", ""),
            bars_df=bars_df,
            min_dte=preset_config.get("min_dte", 7),
            max_dte=preset_config.get("max_dte", 45),
        )
    except Exception as e:
        raise RuntimeError(
            f"Options data fetch failed: {e}. "
            "Theta Terminal must be running for training."
        ) from e

    if options_daily_df is None:
        raise RuntimeError(
            "Theta Terminal is not reachable — cannot fetch options data. "
            "Start Theta Terminal and retry training."
        )

    # Fetch VIX daily bars (VIXY + VIXM) for VIX features
    vix_daily_df = None
    try:
        from data.vix_provider import fetch_vix_daily_bars
        bar_start = bars_df.index.min().to_pydatetime()
        bar_end = bars_df.index.max().to_pydatetime()
        vix_daily_df = fetch_vix_daily_bars(bar_start, bar_end)
    except Exception as e:
        logger.warning(f"VIX daily bars fetch failed (continuing without): {e}")

    # Base features (stock + options + VIX)
    # Scalp uses 1-min bars: 390 bars/day. Swing/general use 5-min: 78 bars/day.
    bars_per_day = 390 if preset == "scalp" else 78
    df = compute_base_features(bars_df.copy(), options_daily_df=options_daily_df, vix_daily_df=vix_daily_df, bars_per_day=bars_per_day)

    # Style-specific features
    if preset == "swing":
        df = compute_swing_features(df)
    elif preset == "general":
        df = compute_general_features(df)
    elif preset == "scalp":
        df = compute_scalp_features(df)

    elapsed = time.time() - start
    feature_cols = _get_feature_names(preset)
    present = [c for c in feature_cols if c in df.columns]
    logger.info(
        f"Features computed in {elapsed:.1f}s: "
        f"{len(present)}/{len(feature_cols)} features present"
    )
    return df


def _calculate_target(df: pd.DataFrame, horizon_bars: int) -> pd.Series:
    """
    Calculate forward return target.
    target = (close at T+horizon) / close at T - 1, expressed as percentage.
    """
    future_close = df["close"].shift(-horizon_bars)
    target = ((future_close / df["close"]) - 1) * 100  # Percentage
    return target


def _optuna_optimize(
    X: pd.DataFrame,
    y: pd.Series,
    n_trials: int = 30,
    timeout_seconds: int = 300,
) -> dict:
    """
    Optuna hyperparameter optimization for XGBoost.

    Runs a Bayesian search over key hyperparameters using walk-forward CV
    as the objective. Falls back to fixed defaults if Optuna fails or is
    not installed.

    Args:
        X: Feature matrix
        y: Target series
        n_trials: Max Optuna trials (default 30)
        timeout_seconds: Max optimization time in seconds (default 300)

    Returns:
        Dict of best hyperparameters for XGBRegressor
    """
    # Default params (same as old fixed values) — used as fallback
    default_params = {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
    }

    try:
        import optuna
        from sklearn.metrics import mean_absolute_error

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 200, 800, step=100),
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "reg_alpha": trial.suggest_float("reg_alpha", 0.001, 1.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 5.0, log=True),
            }

            # Simple time-series split (last 20% as validation)
            split_idx = int(len(X) * 0.8)
            X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
            y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

            model = XGBRegressor(
                **params,
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            )
            model.fit(X_train, y_train, verbose=False)
            preds = model.predict(X_val)
            mae = mean_absolute_error(y_val, preds)
            return mae

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, timeout=timeout_seconds)

        best = study.best_params
        logger.info(
            f"Optuna: {len(study.trials)} trials, best MAE={study.best_value:.4f}"
        )
        return best

    except ImportError:
        logger.warning("Optuna not installed — using default hyperparameters")
        return default_params
    except Exception as e:
        logger.warning(f"Optuna optimization failed — using defaults: {e}")
        return default_params


def _walk_forward_cv(
    X: pd.DataFrame,
    y: pd.Series,
    n_folds: int = CV_FOLDS,
) -> dict:
    """
    Walk-forward cross-validation with expanding window.

    Splits data chronologically:
        Fold 1: Train on first 1/6, test on 2nd 1/6
        Fold 2: Train on first 2/6, test on 3rd 1/6
        ...
        Fold 5: Train on first 5/6, test on last 1/6

    Returns dict with aggregate metrics.
    """
    logger.info(f"Running {n_folds}-fold walk-forward CV on {len(X)} samples")

    n = len(X)
    fold_size = n // (n_folds + 1)  # +1 so we have room for first train set

    all_actuals = []
    all_preds = []
    fold_metrics = []

    for fold in range(n_folds):
        train_end = fold_size * (fold + 1)
        test_start = train_end
        test_end = min(train_end + fold_size, n)

        if test_end <= test_start:
            logger.warning(f"Fold {fold+1}: not enough data, skipping")
            continue

        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]
        X_test = X.iloc[test_start:test_end]
        y_test = y.iloc[test_start:test_end]

        logger.info(
            f"  Fold {fold+1}/{n_folds}: "
            f"train={len(X_train)} samples, test={len(X_test)} samples"
        )

        model = XGBRegressor(
            n_estimators=500,
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
            early_stopping_rounds=50,
        )

        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        preds = model.predict(X_test)

        mae = mean_absolute_error(y_test, preds)
        rmse = np.sqrt(mean_squared_error(y_test, preds))
        r2 = r2_score(y_test, preds)

        # Directional accuracy: did we predict the right direction (+ or -)?
        actual_dir = (y_test > 0).astype(int)
        pred_dir = (preds > 0).astype(int)
        dir_acc = (actual_dir == pred_dir).mean()

        fold_metrics.append({
            "fold": fold + 1,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "mae": mae,
            "rmse": rmse,
            "r2": r2,
            "dir_acc": dir_acc,
        })

        all_actuals.extend(y_test.tolist())
        all_preds.extend(preds.tolist())

        logger.info(
            f"  Fold {fold+1} results: MAE={mae:.4f}, RMSE={rmse:.4f}, "
            f"R\u00b2={r2:.4f}, DirAcc={dir_acc:.4f}"
        )

    # Aggregate metrics
    if not fold_metrics:
        logger.error("No fold metrics computed!")
        return {}

    all_actuals = np.array(all_actuals)
    all_preds = np.array(all_preds)

    agg_metrics = {
        "mae": float(mean_absolute_error(all_actuals, all_preds)),
        "rmse": float(np.sqrt(mean_squared_error(all_actuals, all_preds))),
        "r2": float(r2_score(all_actuals, all_preds)),
        "dir_acc": float(((all_actuals > 0) == (all_preds > 0)).mean()),
        "cv_folds": len(fold_metrics),
        "fold_details": fold_metrics,
    }

    logger.info(
        f"CV Results \u2014 MAE: {agg_metrics['mae']:.4f}, "
        f"RMSE: {agg_metrics['rmse']:.4f}, "
        f"R\u00b2: {agg_metrics['r2']:.4f}, "
        f"DirAcc: {agg_metrics['dir_acc']:.4f}"
    )
    return agg_metrics


def train_model(
    profile_id: str,
    symbol: str,
    preset: str,
    prediction_horizon: str = "5d",
    years_of_data: int = 6,
    db_path: str = None,
) -> dict:
    """
    Full training pipeline. Returns dict with model_id, metrics, and model_path.

    Args:
        profile_id: UUID of the profile
        symbol: Ticker symbol (e.g., "TSLA")
        preset: Trading preset ("swing" or "general")
        prediction_horizon: Forward return horizon (e.g., "5d")
        years_of_data: How many years of history to fetch
        db_path: Override DB path (for testing)

    Returns:
        Dict with keys: model_id, model_path, metrics, feature_names, status
    """
    pipeline_start = time.time()
    db_path = db_path or str(DB_PATH)
    model_id = str(uuid.uuid4())
    model_filename = f"{profile_id}_{preset}_{symbol}_{model_id[:8]}.joblib"
    model_path = str(MODELS_DIR / model_filename)

    logger.info("=" * 70)
    logger.info(f"TRAINING PIPELINE START")
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

    # =====================================================================
    # STEP 1: Fetch historical stock bars
    # =====================================================================
    logger.info("")
    logger.info("STEP 1: Fetching historical stock bars from Alpaca")
    logger.info("-" * 50)

    from data.alpaca_provider import AlpacaStockProvider
    stock_provider = AlpacaStockProvider()

    end_date = datetime.now() - timedelta(hours=1)
    start_date = end_date - timedelta(days=years_of_data * 365 + 30)

    step_start = time.time()
    bars_df = stock_provider.get_historical_bars(symbol, start_date, end_date, "5min")
    step_elapsed = time.time() - step_start

    if bars_df.empty:
        logger.error("FATAL: No bars returned from Alpaca")
        return {"status": "failed", "message": "No stock data available"}

    logger.info(
        f"Step 1 complete: {len(bars_df)} bars in {step_elapsed:.0f}s "
        f"({bars_df.index[0]} to {bars_df.index[-1]})"
    )

    # Tag bars_df with symbol so options fetcher can use it
    bars_df.attrs["symbol"] = symbol

    data_start_date = bars_df.index[0].strftime("%Y-%m-%d")
    data_end_date = bars_df.index[-1].strftime("%Y-%m-%d")

    # =====================================================================
    # STEP 2: Compute features
    # =====================================================================
    logger.info("")
    logger.info("STEP 2: Computing features")
    logger.info("-" * 50)

    step_start = time.time()
    featured_df = _compute_all_features(bars_df, preset)
    step_elapsed = time.time() - step_start
    logger.info(f"Step 2 complete: features computed in {step_elapsed:.0f}s")

    # =====================================================================
    # STEP 3: Calculate target (forward return)
    # =====================================================================
    logger.info("")
    logger.info("STEP 3: Calculating forward return target")
    logger.info("-" * 50)

    featured_df["target"] = _calculate_target(featured_df, horizon_bars)

    total_bars = len(featured_df)
    has_target = featured_df["target"].notna().sum()
    logger.info(
        f"Target calculated: {has_target}/{total_bars} bars have valid targets "
        f"({total_bars - has_target} bars at end excluded \u2014 no future data)"
    )

    # =====================================================================
    # STEP 4: Prepare training data
    # =====================================================================
    logger.info("")
    logger.info("STEP 4: Preparing training data")
    logger.info("-" * 50)

    # Drop rows where target is NaN (end of dataset — no future data)
    train_df = featured_df.dropna(subset=["target"])

    # Keep only feature columns + target
    missing_features = [f for f in feature_names if f not in train_df.columns]
    if missing_features:
        logger.warning(f"Missing features (will be NaN): {missing_features}")
        for f in missing_features:
            train_df[f] = np.nan

    X = train_df[feature_names].copy()
    y = train_df["target"].copy()

    # Drop rows where ALL features are NaN (very start of dataset — rolling warmup)
    valid_mask = X.notna().any(axis=1)
    X = X[valid_mask]
    y = y[valid_mask]

    logger.info(
        f"Training dataset: {len(X)} samples, {len(feature_names)} features"
    )
    logger.info(f"Target stats: mean={y.mean():.4f}%, std={y.std():.4f}%, "
                f"min={y.min():.4f}%, max={y.max():.4f}%")

    if len(X) < MIN_TRAINING_SAMPLES:
        logger.error(
            f"FATAL: Only {len(X)} training samples. "
            f"Need at least {MIN_TRAINING_SAMPLES}."
        )
        return {
            "status": "failed",
            "message": f"Insufficient training data: {len(X)} samples",
        }

    # =====================================================================
    # STEP 5: Walk-forward cross-validation
    # =====================================================================
    logger.info("")
    logger.info("STEP 5: Walk-forward cross-validation")
    logger.info("-" * 50)

    step_start = time.time()
    cv_metrics = _walk_forward_cv(X, y)
    step_elapsed = time.time() - step_start
    logger.info(f"Step 5 complete: CV in {step_elapsed:.0f}s")

    if not cv_metrics:
        return {"status": "failed", "message": "Cross-validation failed"}

    # CHECKPOINT: Check directional accuracy
    dir_acc = cv_metrics.get("dir_acc", 0)
    logger.info("")
    logger.info("=" * 50)
    logger.info(f"CHECKPOINT: Directional Accuracy = {dir_acc:.4f}")
    if dir_acc < 0.52:
        logger.warning(
            f"DirAcc {dir_acc:.4f} < 0.52 threshold. "
            f"Model may not be predictive enough. "
            f"Training will continue but review metrics carefully."
        )
    else:
        logger.info(f"DirAcc {dir_acc:.4f} >= 0.52 threshold. Looking good!")
    logger.info("=" * 50)

    # =====================================================================
    # STEP 5.5: Optuna hyperparameter optimization (Phase C)
    # =====================================================================
    logger.info("")
    logger.info("STEP 5.5: Optuna hyperparameter optimization")
    logger.info("-" * 50)

    best_params = _optuna_optimize(X, y)
    logger.info(f"  Best params: {best_params}")

    # =====================================================================
    # STEP 6: Train final model on all data (using Optuna best params)
    # =====================================================================
    logger.info("")
    logger.info("STEP 6: Training final model on all data")
    logger.info("-" * 50)

    step_start = time.time()
    final_model = XGBRegressor(
        n_estimators=best_params.get("n_estimators", 500),
        max_depth=best_params.get("max_depth", 6),
        learning_rate=best_params.get("learning_rate", 0.05),
        subsample=best_params.get("subsample", 0.8),
        colsample_bytree=best_params.get("colsample_bytree", 0.8),
        min_child_weight=best_params.get("min_child_weight", 5),
        reg_alpha=best_params.get("reg_alpha", 0.1),
        reg_lambda=best_params.get("reg_lambda", 1.0),
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    final_model.fit(X, y, verbose=False)
    step_elapsed = time.time() - step_start
    logger.info(f"Step 6 complete: final model trained in {step_elapsed:.0f}s")

    # =====================================================================
    # STEP 7: Save model
    # =====================================================================
    logger.info("")
    logger.info("STEP 7: Saving model to disk")
    logger.info("-" * 50)

    predictor = XGBoostPredictor()
    predictor.set_model(final_model, feature_names)
    predictor.save(model_path, feature_names)

    # Feature importance
    importance = predictor.get_feature_importance()
    top_10 = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
    logger.info("Top 10 features by importance:")
    for name, imp in top_10:
        logger.info(f"  {name}: {imp:.4f}")

    # =====================================================================
    # STEP 8: Save to database
    # =====================================================================
    logger.info("")
    logger.info("STEP 8: Saving metrics to database")
    logger.info("-" * 50)

    import aiosqlite
    import asyncio
    import concurrent.futures

    def _run_async(coro):
        """Run async coroutine with fallback for existing event loops (background threads)."""
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

    # Add training_samples count to metrics
    cv_metrics["training_samples"] = len(X)
    # Remove fold_details from what we store (too verbose for DB)
    fold_details = cv_metrics.pop("fold_details", [])

    hyperparams = {
        "n_estimators": best_params.get("n_estimators", 500),
        "max_depth": best_params.get("max_depth", 6),
        "learning_rate": best_params.get("learning_rate", 0.05),
        "subsample": best_params.get("subsample", 0.8),
        "colsample_bytree": best_params.get("colsample_bytree", 0.8),
        "min_child_weight": best_params.get("min_child_weight", 5),
        "reg_alpha": best_params.get("reg_alpha", 0.1),
        "reg_lambda": best_params.get("reg_lambda", 1.0),
        "prediction_horizon": prediction_horizon,
        "horizon_bars": horizon_bars,
    }

    now = datetime.utcnow().isoformat()
    pipeline_start_iso = datetime.utcfromtimestamp(pipeline_start).isoformat()

    async def _save_to_db():
        async with aiosqlite.connect(db_path) as db:
            # Insert model record
            await db.execute(
                """INSERT INTO models
                   (id, profile_id, model_type, file_path, status,
                    training_started_at, training_completed_at,
                    data_start_date, data_end_date,
                    metrics, feature_names, hyperparameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    model_id, profile_id, "xgboost", model_path, "ready",
                    pipeline_start_iso, now,
                    data_start_date, data_end_date,
                    json.dumps(cv_metrics),
                    json.dumps(feature_names),
                    json.dumps(hyperparams),
                    now,
                ),
            )

            # Update profile: set model_id and status
            await db.execute(
                "UPDATE profiles SET model_id = ?, status = 'ready', updated_at = ? WHERE id = ?",
                (model_id, now, profile_id),
            )

            await db.commit()
            logger.info("Model and profile updated in database")

    _run_async(_save_to_db())

    # =====================================================================
    # STEP 9: Post-training feature validation
    # =====================================================================
    logger.info("")
    logger.info("STEP 9: Feature validation")
    logger.info("-" * 50)

    expected_features = _get_feature_names(preset)
    missing_features = [f for f in expected_features if f not in feature_names]
    extra_features = [f for f in feature_names if f not in expected_features]
    zero_importance = [f for f, imp in importance.items() if imp == 0.0]

    # Options features specifically
    options_features = [f for f in expected_features if f.startswith(("atm_", "iv_", "rv_iv", "put_call", "theta_delta", "gamma_theta", "vega_theta"))]
    options_present = [f for f in options_features if f in feature_names]
    options_missing = [f for f in options_features if f not in feature_names]
    options_zero_imp = [f for f in options_present if importance.get(f, 0.0) == 0.0]

    logger.info(f"  Expected features: {len(expected_features)}")
    logger.info(f"  Model features:    {len(feature_names)}")
    logger.info(f"  Missing features:  {len(missing_features)}")
    if missing_features:
        logger.warning(f"  MISSING: {missing_features}")
    logger.info(f"  Options features:  {len(options_present)}/{len(options_features)} present")
    if options_missing:
        logger.warning(f"  OPTIONS MISSING: {options_missing}")
    logger.info(f"  Zero-importance:   {len(zero_importance)}/{len(feature_names)}")
    if options_zero_imp:
        logger.warning(f"  OPTIONS ZERO IMPORTANCE: {options_zero_imp}")

    # Check NaN coverage in training data
    nan_counts = train_df[feature_names].isna().sum()
    total_rows = len(train_df)
    high_nan_features = [(f, int(c), f"{c/total_rows*100:.0f}%") for f, c in nan_counts.items() if c > total_rows * 0.5]
    if high_nan_features:
        logger.warning(f"  Features >50% NaN in training data:")
        for fname, count, pct in high_nan_features:
            logger.warning(f"    {fname}: {count}/{total_rows} ({pct})")
    else:
        logger.info(f"  All features <50% NaN in training data")

    # =====================================================================
    # SUMMARY
    # =====================================================================
    total_elapsed = time.time() - pipeline_start

    logger.info("")
    logger.info("=" * 70)
    logger.info("TRAINING PIPELINE COMPLETE")
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

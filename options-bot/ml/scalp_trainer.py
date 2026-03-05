"""
Scalp XGBClassifier training pipeline.
Matches PROJECT_ARCHITECTURE.md Section 7 — Phase 5.

Full pipeline:
    1. Fetch historical 1-min stock bars from Alpaca
    2. Compute features (base at 1-min resolution + scalp-specific)
    3. Calculate 3-class target from 30-min forward return
    4. Subsample every 30 bars (non-overlapping targets, reduce autocorrelation)
    5. Walk-forward cross-validation (5-fold expanding window)
    6. Train final classifier on all data
    7. Save model + metrics + feature names to DB
    8. Update profile status

Target classes:
    0 = DOWN:    30-min return < -0.05%
    1 = NEUTRAL: 30-min return in [-0.05%, +0.05%]
    2 = UP:      30-min return > +0.05%
"""

import json
import uuid
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

import sys
# Add project root to sys.path — no setup.py/pyproject.toml in this project
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MODELS_DIR, PRESET_DEFAULTS, DB_PATH, OPTUNA_N_TRIALS, OPTUNA_TIMEOUT_SECONDS
from ml.scalp_predictor import ScalpPredictor
from ml.feature_engineering.base_features import compute_base_features, get_base_feature_names
from ml.feature_engineering.scalp_features import compute_scalp_features, get_scalp_feature_names

logger = logging.getLogger("options-bot.ml.scalp_trainer")

# Training constants
CV_FOLDS = 5
MIN_TRAINING_SAMPLES = 500
NEUTRAL_BAND_PCT = 0.12  # ±0.12% threshold for neutral class (widened from 0.05 — SPY noise floor)
HORIZON_BARS = 30  # 30 bars of 1-min = 30 minutes
SUBSAMPLE_STRIDE = 30  # Sample every 30th bar (non-overlapping targets)
SCALP_BARS_PER_DAY = 390  # 6.5 hours × 60 min


def _get_feature_names() -> list[str]:
    """Get full feature list for scalp preset."""
    return get_base_feature_names() + get_scalp_feature_names()


def _compute_all_features(bars_df: pd.DataFrame) -> pd.DataFrame:
    """Compute base (at 1-min resolution) + scalp features, including options from Theta."""
    logger.info("Computing all features for scalp preset (1-min bars)")
    start = time.time()

    # Fetch options data from Theta Terminal
    options_daily_df = None
    try:
        from data.options_data_fetcher import fetch_options_for_training
        preset_config = PRESET_DEFAULTS.get("scalp", {})
        options_daily_df = fetch_options_for_training(
            symbol=bars_df.attrs.get("symbol", ""),
            bars_df=bars_df,
            min_dte=preset_config.get("min_dte", 0),
            max_dte=preset_config.get("max_dte", 1),
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

    # Fetch VIX daily bars for VIX features
    vix_daily_df = None
    try:
        from data.vix_provider import fetch_vix_daily_bars
        bar_start = bars_df.index.min().to_pydatetime()
        bar_end = bars_df.index.max().to_pydatetime()
        vix_daily_df = fetch_vix_daily_bars(bar_start, bar_end)
    except Exception as e:
        logger.warning(f"VIX daily bars fetch failed (continuing without): {e}")

    # Base features with 1-min resolution
    df = compute_base_features(bars_df.copy(), options_daily_df=options_daily_df,
                               vix_daily_df=vix_daily_df, bars_per_day=SCALP_BARS_PER_DAY)
    # Scalp-specific features
    df = compute_scalp_features(df)

    elapsed = time.time() - start
    feature_names = _get_feature_names()
    present = [c for c in feature_names if c in df.columns]
    logger.info(
        f"Features computed in {elapsed:.1f}s: "
        f"{len(present)}/{len(feature_names)} features present"
    )
    return df


def _calculate_class_target(df: pd.DataFrame) -> pd.Series:
    """
    Calculate 3-class target from 30-min forward return.

    Returns:
        Series with values 0 (DOWN), 1 (NEUTRAL), 2 (UP).
        NaN where forward return cannot be computed (last 30 bars).
    """
    future_close = df["close"].shift(-HORIZON_BARS)
    forward_return_pct = ((future_close / df["close"]) - 1) * 100

    # Classify
    target = pd.Series(np.nan, index=df.index)
    target[forward_return_pct < -NEUTRAL_BAND_PCT] = 0  # DOWN
    target[forward_return_pct.abs() <= NEUTRAL_BAND_PCT] = 1  # NEUTRAL
    target[forward_return_pct > NEUTRAL_BAND_PCT] = 2  # UP

    return target


def _subsample_strided(df: pd.DataFrame) -> pd.DataFrame:
    """
    Subsample every SUBSAMPLE_STRIDE bars to avoid overlapping targets
    and reduce autocorrelation.

    For 30-bar horizon with stride=30, each sample's target window
    does not overlap with its neighbors.
    """
    logger.info(f"Subsampling {len(df)} bars with stride={SUBSAMPLE_STRIDE}...")
    result = df.iloc[::SUBSAMPLE_STRIDE].copy()
    logger.info(f"Subsampled to {len(result)} observations")
    return result


def _optuna_optimize_classifier(
    X: pd.DataFrame,
    y: pd.Series,
    n_trials: int = 30,
    timeout_seconds: int = 300,
) -> dict:
    """
    Optuna hyperparameter optimization for XGBClassifier.

    Uses a simple time-series split (last 20% as validation) with early stopping.
    Falls back to fixed defaults if Optuna fails or is not installed.
    """
    default_params = {
        "n_estimators": 500,
        "max_depth": 5,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
    }

    try:
        import optuna
        from sklearn.metrics import log_loss

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        split_idx = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]
        sw_train = compute_sample_weight("balanced", y_train)

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

            model = XGBClassifier(
                **params,
                num_class=3,
                objective="multi:softprob",
                eval_metric="mlogloss",
                early_stopping_rounds=30,
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            )
            model.fit(
                X_train, y_train,
                sample_weight=sw_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
            proba = model.predict_proba(X_val)
            return log_loss(y_val, proba)

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, timeout=timeout_seconds)

        best = study.best_params
        logger.info(
            f"Optuna: {len(study.trials)} trials, best logloss={study.best_value:.4f}"
        )
        return best

    except ImportError:
        logger.warning("Optuna not installed — using default hyperparameters")
        return default_params
    except Exception as e:
        logger.warning(f"Optuna optimization failed — using defaults: {e}")
        return default_params


def _walk_forward_cv_classifier(
    X: pd.DataFrame,
    y: pd.Series,
    n_folds: int = CV_FOLDS,
    xgb_params: dict = None,
) -> dict:
    """
    Walk-forward cross-validation for classifier with expanding window.

    Primary metric: directional accuracy on UP/DOWN classes only
    (excludes NEUTRAL from accuracy calculation since NEUTRAL = no-trade).

    Uses early stopping and balanced class weighting.

    Splits data chronologically (same pattern as trainer.py):
        Fold k: Train on first (k+1)/(n_folds+1), test on next chunk
    """
    n = len(X)
    fold_size = n // (n_folds + 1)

    if fold_size < 50:
        logger.warning(f"Fold size {fold_size} is very small — results may be noisy")

    all_actuals = []
    all_preds = []
    fold_metrics = []

    for fold in range(n_folds):
        train_end = fold_size * (fold + 1)
        val_start = train_end
        val_end = min(train_end + fold_size, n)

        if val_end <= val_start:
            logger.warning(f"Fold {fold+1}: no validation data, skipping")
            continue

        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]
        X_val = X.iloc[val_start:val_end]
        y_val = y.iloc[val_start:val_end]

        # Balanced class weighting so UP/DOWN aren't drowned out by NEUTRAL
        sw_train = compute_sample_weight("balanced", y_train)

        logger.info(
            f"  Fold {fold+1}/{n_folds}: train={len(X_train)}, val={len(X_val)}"
        )

        params = xgb_params or {}
        model = XGBClassifier(
            n_estimators=params.get("n_estimators", 500),
            max_depth=params.get("max_depth", 5),
            learning_rate=params.get("learning_rate", 0.05),
            subsample=params.get("subsample", 0.8),
            colsample_bytree=params.get("colsample_bytree", 0.8),
            min_child_weight=params.get("min_child_weight", 5),
            reg_alpha=params.get("reg_alpha", 0.1),
            reg_lambda=params.get("reg_lambda", 1.0),
            num_class=3,
            objective="multi:softprob",
            eval_metric="mlogloss",
            early_stopping_rounds=30,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )

        model.fit(
            X_train, y_train,
            sample_weight=sw_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        preds = model.predict(X_val)
        proba = model.predict_proba(X_val)

        # Overall accuracy (all 3 classes)
        acc_all = float(accuracy_score(y_val, preds))

        # Directional accuracy: UP/DOWN only (exclude NEUTRAL from both actual and pred)
        # This is the PRIMARY metric — measures quality of directional calls
        dir_mask = (y_val != 1)  # Actual is UP or DOWN
        if dir_mask.sum() > 0:
            dir_acc = float(accuracy_score(y_val[dir_mask], preds[dir_mask]))
        else:
            dir_acc = 0.5  # No directional samples

        # Class distribution in validation set
        val_class_dist = {
            "down": int((y_val == 0).sum()),
            "neutral": int((y_val == 1).sum()),
            "up": int((y_val == 2).sum()),
        }

        fold_metrics.append({
            "fold": fold + 1,
            "train_size": len(X_train),
            "val_size": len(X_val),
            "acc_all": acc_all,
            "dir_acc": dir_acc,
            "best_iteration": getattr(model, "best_iteration", None),
            "class_distribution": val_class_dist,
        })

        all_actuals.extend(y_val.values.tolist())
        all_preds.extend(preds.tolist())

        best_iter_str = f", best_iter={model.best_iteration}" if hasattr(model, "best_iteration") else ""
        logger.info(
            f"  Fold {fold+1} results: acc_all={acc_all:.4f}, "
            f"dir_acc={dir_acc:.4f}{best_iter_str}, classes={val_class_dist}"
        )

    if not fold_metrics:
        logger.error("No CV folds completed successfully")
        return {
            "acc_all": 0.33, "dir_acc": 0.50,
            "cv_folds": 0, "fold_details": [],
        }

    all_actuals = np.array(all_actuals)
    all_preds = np.array(all_preds)

    # Aggregate metrics
    agg_acc_all = float(accuracy_score(all_actuals, all_preds))
    dir_mask = (all_actuals != 1)
    agg_dir_acc = float(accuracy_score(all_actuals[dir_mask], all_preds[dir_mask])) if dir_mask.sum() > 0 else 0.5

    agg_metrics = {
        "acc_all": agg_acc_all,
        "dir_acc": agg_dir_acc,
        "cv_folds": len(fold_metrics),
        "fold_details": fold_metrics,
    }

    logger.info(
        f"CV Results — Accuracy (all): {agg_acc_all:.4f}, "
        f"Directional Accuracy (UP/DOWN): {agg_dir_acc:.4f}"
    )
    return agg_metrics


def train_scalp_model(
    profile_id: str,
    symbol: str,
    prediction_horizon: str = "30min",
    years_of_data: int = 2,
    db_path: str = None,
) -> dict:
    """
    Full scalp classifier training pipeline.

    Args:
        profile_id: UUID of the profile
        symbol: Ticker symbol (e.g., "SPY")
        prediction_horizon: Must be "30min" for scalp
        years_of_data: How many years of 1-min bars to fetch (default 2)
        db_path: Override DB path (for testing)

    Returns:
        Dict with keys: model_id, model_path, metrics, feature_names, status
    """
    pipeline_start = time.time()
    db_path = db_path or str(DB_PATH)
    model_id = str(uuid.uuid4())
    model_filename = f"{profile_id}_scalp_{symbol}_{model_id[:8]}.joblib"
    model_path = str(MODELS_DIR / model_filename)

    logger.info("=" * 70)
    logger.info("SCALP CLASSIFIER TRAINING PIPELINE START")
    logger.info(f"  Profile:  {profile_id}")
    logger.info(f"  Symbol:   {symbol}")
    logger.info(f"  Preset:   scalp")
    logger.info(f"  Horizon:  {prediction_horizon} ({HORIZON_BARS} bars @ 1-min)")
    logger.info(f"  Neutral band: +/-{NEUTRAL_BAND_PCT}%")
    logger.info(f"  Years:    {years_of_data}")
    logger.info(f"  Model ID: {model_id}")
    logger.info("=" * 70)

    feature_names = _get_feature_names()

    # =====================================================================
    # STEP 1: Fetch historical 1-min bars from Alpaca
    # =====================================================================
    logger.info("")
    logger.info("STEP 1: Fetching historical 1-min bars from Alpaca")
    logger.info("-" * 50)

    from data.alpaca_provider import AlpacaStockProvider
    stock_provider = AlpacaStockProvider()

    end_date = datetime.now() - timedelta(hours=1)
    start_date = end_date - timedelta(days=years_of_data * 365 + 30)

    step_start = time.time()
    try:
        bars_df = stock_provider.get_historical_bars(
            symbol, start_date, end_date, timeframe="1min"
        )
    except Exception as e:
        msg = f"Failed to fetch 1-min bars from Alpaca: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "failed", "message": msg}

    if bars_df is None or bars_df.empty:
        msg = f"No 1-min bars returned for {symbol}"
        logger.error(msg)
        return {"status": "failed", "message": msg}

    bars_df.attrs["symbol"] = symbol
    data_start_date = str(bars_df.index.min().date())
    data_end_date = str(bars_df.index.max().date())
    step_elapsed = time.time() - step_start
    logger.info(
        f"Fetched {len(bars_df)} 1-min bars in {step_elapsed:.0f}s: "
        f"{data_start_date} to {data_end_date}"
    )

    # =====================================================================
    # STEP 2: Compute features
    # =====================================================================
    logger.info("")
    logger.info("STEP 2: Computing features (base @ 1-min + scalp)")
    logger.info("-" * 50)

    step_start = time.time()
    try:
        featured_df = _compute_all_features(bars_df)
        step_elapsed = time.time() - step_start
        logger.info(
            f"Features computed in {step_elapsed:.0f}s: "
            f"{len(featured_df)} rows, {len(featured_df.columns)} columns"
        )
    except Exception as e:
        msg = f"Feature computation failed: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "failed", "message": msg}

    # =====================================================================
    # STEP 3: Calculate class target + subsample
    # =====================================================================
    logger.info("")
    logger.info("STEP 3: Calculating class target and subsampling")
    logger.info("-" * 50)

    featured_df["_target"] = _calculate_class_target(featured_df)

    # Also compute raw forward return for avg_30min_move calculation
    future_close = featured_df["close"].shift(-HORIZON_BARS)
    featured_df["_forward_return_pct"] = (
        (future_close / featured_df["close"]) - 1
    ) * 100

    # Drop rows without target (last HORIZON_BARS rows + NaN from features)
    featured_df = featured_df.dropna(subset=["_target"])
    logger.info(f"After dropping NaN targets: {len(featured_df)} rows")

    # Subsample to avoid overlapping targets
    featured_df = _subsample_strided(featured_df)

    # Calculate average absolute 30-min move (for EV estimation later)
    avg_30min_move_pct = float(featured_df["_forward_return_pct"].abs().mean())
    logger.info(f"Average absolute 30-min move: {avg_30min_move_pct:.4f}%")

    # Class distribution
    class_counts = featured_df["_target"].value_counts().sort_index()
    total = len(featured_df)
    logger.info(f"Class distribution ({total} samples):")
    for cls, count in class_counts.items():
        label = {0: "DOWN", 1: "NEUTRAL", 2: "UP"}.get(int(cls), "?")
        logger.info(f"  {label} ({int(cls)}): {count} ({count/total*100:.1f}%)")

    if total < MIN_TRAINING_SAMPLES:
        msg = (
            f"Only {total} training samples after subsampling "
            f"(need {MIN_TRAINING_SAMPLES}). Try more years of data."
        )
        logger.error(msg)
        return {"status": "failed", "message": msg}

    # Prepare X, y
    X = featured_df[feature_names].copy()
    y = featured_df["_target"].astype(int)

    # Drop remaining NaN feature rows
    # NOTE: Scalp uses .all() (drop if ANY feature is NaN) vs XGBoost's .any()
    # (drop only if ALL features are NaN). This is intentional — scalp's 1-min
    # classifier is more sensitive to missing features than the regressor.
    valid_mask = X.notna().all(axis=1)
    nan_dropped = (~valid_mask).sum()
    if nan_dropped > 0:
        logger.info(f"Dropping {nan_dropped} rows with NaN features")
        X = X[valid_mask]
        y = y[valid_mask]

    # Replace any inf with NaN then fill with 0
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)

    logger.info(f"Training data ready: {len(X)} samples, {len(feature_names)} features")

    # =====================================================================
    # STEP 4: Optuna hyperparameter optimization
    # =====================================================================
    logger.info("")
    logger.info("STEP 4: Optuna hyperparameter optimization")
    logger.info("-" * 50)

    step_start = time.time()
    best_params = _optuna_optimize_classifier(
        X, y,
        n_trials=OPTUNA_N_TRIALS,
        timeout_seconds=OPTUNA_TIMEOUT_SECONDS,
    )
    step_elapsed = time.time() - step_start
    logger.info(f"Optuna completed in {step_elapsed:.0f}s")
    logger.info(f"  Best params: {best_params}")

    # =====================================================================
    # STEP 5: Walk-forward cross-validation (with tuned params)
    # =====================================================================
    logger.info("")
    logger.info("STEP 5: Walk-forward cross-validation")
    logger.info("-" * 50)

    step_start = time.time()
    cv_metrics = _walk_forward_cv_classifier(X, y, xgb_params=best_params)
    step_elapsed = time.time() - step_start
    logger.info(f"CV completed in {step_elapsed:.0f}s")

    # Directional accuracy warning
    dir_acc = cv_metrics.get("dir_acc", 0.5)
    logger.info("=" * 50)
    if dir_acc < 0.52:
        logger.warning(
            f"DIRECTIONAL ACCURACY {dir_acc:.4f} is below 0.52 threshold. "
            f"Scalp model may not be predictive enough for profitable trading."
        )
    else:
        logger.info(f"DirAcc {dir_acc:.4f} >= 0.52 threshold. Looking good!")
    logger.info("=" * 50)

    # =====================================================================
    # STEP 6: Train final classifier on all data (with tuned params)
    # =====================================================================
    logger.info("")
    logger.info("STEP 6: Training final classifier on all data")
    logger.info("-" * 50)

    # Use balanced class weights for final model too
    sw_final = compute_sample_weight("balanced", y)

    # Train/eval split for early stopping on final model (last 10%)
    split_idx = int(len(X) * 0.9)
    X_train_final = X.iloc[:split_idx]
    y_train_final = y.iloc[:split_idx]
    sw_train_final = sw_final[:split_idx]
    X_eval_final = X.iloc[split_idx:]
    y_eval_final = y.iloc[split_idx:]

    step_start = time.time()
    final_model = XGBClassifier(
        n_estimators=best_params.get("n_estimators", 500),
        max_depth=best_params.get("max_depth", 5),
        learning_rate=best_params.get("learning_rate", 0.05),
        subsample=best_params.get("subsample", 0.8),
        colsample_bytree=best_params.get("colsample_bytree", 0.8),
        min_child_weight=best_params.get("min_child_weight", 5),
        reg_alpha=best_params.get("reg_alpha", 0.1),
        reg_lambda=best_params.get("reg_lambda", 1.0),
        num_class=3,
        objective="multi:softprob",
        eval_metric="mlogloss",
        early_stopping_rounds=30,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    final_model.fit(
        X_train_final, y_train_final,
        sample_weight=sw_train_final,
        eval_set=[(X_eval_final, y_eval_final)],
        verbose=False,
    )
    step_elapsed = time.time() - step_start
    best_iter = getattr(final_model, "best_iteration", "N/A")
    logger.info(f"Final classifier trained in {step_elapsed:.0f}s (best_iteration={best_iter})")

    # =====================================================================
    # STEP 7: Save model
    # =====================================================================
    logger.info("")
    logger.info("STEP 7: Saving model to disk")
    logger.info("-" * 50)

    predictor = ScalpPredictor()
    predictor.set_model(final_model, feature_names)
    predictor.save(
        model_path, feature_names,
        neutral_band=NEUTRAL_BAND_PCT / 100,  # Store as decimal
        avg_30min_move_pct=avg_30min_move_pct,
    )

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
        """Run async coroutine with fallback for existing event loops."""
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

    # Merge CV metrics with training metadata
    training_samples = len(X)
    total_time = time.time() - pipeline_start

    metrics_to_save = {
        **cv_metrics,
        "training_samples": training_samples,
        "total_time_seconds": round(total_time, 1),
        "avg_30min_move_pct": avg_30min_move_pct,
        "neutral_band_pct": NEUTRAL_BAND_PCT,
        "subsample_stride": SUBSAMPLE_STRIDE,
        "class_distribution": {
            "down": int((y == 0).sum()),
            "neutral": int((y == 1).sum()),
            "up": int((y == 2).sum()),
        },
    }

    hyperparams = {
        "n_estimators": best_params.get("n_estimators", 500),
        "max_depth": best_params.get("max_depth", 5),
        "learning_rate": best_params.get("learning_rate", 0.05),
        "subsample": best_params.get("subsample", 0.8),
        "colsample_bytree": best_params.get("colsample_bytree", 0.8),
        "min_child_weight": best_params.get("min_child_weight", 5),
        "reg_alpha": best_params.get("reg_alpha", 0.1),
        "reg_lambda": best_params.get("reg_lambda", 1.0),
        "objective": "multi:softprob",
        "num_class": 3,
        "class_weighting": "balanced",
        "early_stopping_rounds": 30,
        "neutral_band_pct": NEUTRAL_BAND_PCT,
        "horizon_bars": HORIZON_BARS,
        "bar_granularity": "1min",
        "prediction_horizon": prediction_horizon,
    }

    async def _save_to_db():
        now = datetime.now(timezone.utc).isoformat()
        pipeline_start_iso = datetime.fromtimestamp(pipeline_start, tz=timezone.utc).isoformat()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO models
                   (id, profile_id, model_type, file_path, status,
                    training_started_at, training_completed_at,
                    data_start_date, data_end_date,
                    metrics, feature_names, hyperparameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    model_id, profile_id, "xgb_classifier", model_path, "ready",
                    pipeline_start_iso, now,
                    data_start_date, data_end_date,
                    json.dumps(metrics_to_save),
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
            logger.info("Scalp model and profile updated in database")
            return True  # Distinguish success from _run_async failure (which returns None)

    db_result = _run_async(_save_to_db())
    if db_result is None:
        logger.error(
            "STEP 7 FAILED: Database save returned None — model file exists "
            f"at {model_path} but has no DB record. Profile status may be stuck "
            "at 'training'. Attempting synchronous fallback..."
        )
        # Synchronous fallback using sqlite3 to prevent orphaned state
        try:
            import sqlite3
            now = datetime.now(timezone.utc).isoformat()
            pipeline_start_iso = datetime.fromtimestamp(pipeline_start, tz=timezone.utc).isoformat()
            conn = sqlite3.connect(db_path, timeout=10)
            conn.execute(
                """INSERT INTO models
                   (id, profile_id, model_type, file_path, status,
                    training_started_at, training_completed_at,
                    data_start_date, data_end_date,
                    metrics, feature_names, hyperparameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    model_id, profile_id, "xgb_classifier", model_path, "ready",
                    pipeline_start_iso, now,
                    data_start_date, data_end_date,
                    json.dumps(metrics_to_save),
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

    # =====================================================================
    # STEP 9: Post-training feature validation
    # =====================================================================
    logger.info("")
    logger.info("STEP 9: Feature validation")
    logger.info("-" * 50)

    expected_features = _get_feature_names()
    missing_features = [f for f in expected_features if f not in feature_names]
    extra_features = [f for f in feature_names if f not in expected_features]
    zero_importance = [f for f, imp in importance.items() if imp == 0.0]

    logger.info(f"Expected features: {len(expected_features)}")
    logger.info(f"Actual features: {len(feature_names)}")
    if missing_features:
        logger.warning(f"Missing features: {missing_features}")
    if extra_features:
        logger.warning(f"Extra features: {extra_features}")
    if zero_importance:
        logger.info(f"Zero-importance features ({len(zero_importance)}): {zero_importance[:5]}...")

    # =====================================================================
    # Done
    # =====================================================================
    total_time = time.time() - pipeline_start
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"SCALP TRAINING COMPLETE in {total_time:.0f}s")
    logger.info(f"  Model ID:  {model_id}")
    logger.info(f"  Model:     {model_path}")
    logger.info(f"  DirAcc:    {dir_acc:.4f}")
    logger.info(f"  Acc (all): {cv_metrics.get('acc_all', 'N/A')}")
    logger.info(f"  Samples:   {training_samples}")
    logger.info(f"  Avg move:  {avg_30min_move_pct:.4f}%")
    logger.info("=" * 70)

    return {
        "status": "ready",
        "model_id": model_id,
        "model_path": model_path,
        "metrics": metrics_to_save,
        "feature_names": feature_names,
        "data_range": f"{data_start_date} to {data_end_date}",
        "training_samples": training_samples,
        "total_time_seconds": round(total_time, 1),
    }

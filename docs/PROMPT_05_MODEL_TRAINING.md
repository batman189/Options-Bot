# CLAUDE CODE PROMPT 05 — XGBoost Model Training Pipeline

## TASK
Create the ML model predictor interface, XGBoost predictor, training pipeline, and standalone training script. This is Phase 1, Step 8 from the architecture.

**Pipeline overview**:
1. Fetch 6+ years of 5-min stock bars from Alpaca (paginated)
2. Compute all features (base + style-specific)
3. Calculate forward return target (e.g., 5-day return for swing)
4. Subsample to 1 bar per day (avoid autocorrelation from adjacent 5-min bars)
5. Walk-forward cross-validation (5-fold, expanding window)
6. Train final model on all data
7. Save model (.joblib), metrics, and feature names to SQLite
8. Update profile status

**Key design decisions**:
- **Subsample to daily**: Features computed at 5-min resolution (for rolling accuracy), but training uses 1 sample per trading day (the 15:50 bar). This avoids massive autocorrelation and gives ~1,500 training samples over 6 years — plenty for XGBoost.
- **Stock features only for initial training**: Options features require ~1,500 per-day API calls to Theta. The trainer handles both, but the first model runs with NaN options features. XGBoost handles missing values natively.
- **Walk-forward CV**: Expanding window, NOT random split. Respects time ordering.

**CRITICAL**: Read this ENTIRE prompt. Build exactly what is specified.

---

## FILES TO CREATE

1. `options-bot/ml/predictor.py` — Abstract ModelPredictor interface
2. `options-bot/ml/xgboost_predictor.py` — XGBoost implementation
3. `options-bot/ml/trainer.py` — Full training pipeline
4. `options-bot/scripts/train_model.py` — Standalone training entry point

---

## FILE 1: `options-bot/ml/predictor.py`

```python
"""
Abstract ModelPredictor interface.
Matches PROJECT_ARCHITECTURE.md Section 7 — Model Interface.

Strategy code calls predictor.predict() — never knows which model is behind it.
"""

from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd


class ModelPredictor(ABC):
    """Abstract interface for ML model predictions."""

    @abstractmethod
    def predict(self, features: dict, sequence: pd.DataFrame = None) -> float:
        """
        Return predicted forward return %.

        Args:
            features: Dict of feature_name -> value for a single observation.
            sequence: Optional DataFrame of sequential data (for TFT, Phase 4).

        Returns:
            Predicted forward return as a percentage (e.g., 2.5 means +2.5%).
        """
        pass

    @abstractmethod
    def predict_batch(self, features_df: pd.DataFrame) -> pd.Series:
        """
        Predict for multiple observations at once.

        Args:
            features_df: DataFrame where each row is one observation.

        Returns:
            Series of predicted forward returns.
        """
        pass

    @abstractmethod
    def get_feature_names(self) -> list[str]:
        """Return the list of feature names this model expects."""
        pass

    @abstractmethod
    def get_feature_importance(self) -> dict:
        """Return dict of feature_name -> importance score."""
        pass
```

---

## FILE 2: `options-bot/ml/xgboost_predictor.py`

```python
"""
XGBoost ModelPredictor implementation.
Matches PROJECT_ARCHITECTURE.md Section 7 — Phase 1-3: XGBoost Only.
"""

import logging
from typing import Optional
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from ml.predictor import ModelPredictor

logger = logging.getLogger("options-bot.ml.xgboost")


class XGBoostPredictor(ModelPredictor):
    """XGBoost regression model for predicting forward returns."""

    def __init__(self, model_path: str = None):
        self._model = None
        self._feature_names = []
        if model_path:
            self.load(model_path)

    def load(self, model_path: str):
        """Load a trained model from disk."""
        logger.info(f"Loading XGBoost model from {model_path}")
        data = joblib.load(model_path)
        self._model = data["model"]
        self._feature_names = data["feature_names"]
        logger.info(
            f"Model loaded: {len(self._feature_names)} features, "
            f"type={type(self._model).__name__}"
        )

    def save(self, model_path: str, feature_names: list[str]):
        """Save the trained model to disk."""
        logger.info(f"Saving XGBoost model to {model_path}")
        Path(model_path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"model": self._model, "feature_names": feature_names},
            model_path,
        )
        self._feature_names = feature_names
        logger.info(f"Model saved: {model_path}")

    def set_model(self, model, feature_names: list[str]):
        """Set the model directly (used during training)."""
        self._model = model
        self._feature_names = feature_names

    def predict(self, features: dict, sequence: pd.DataFrame = None) -> float:
        """Predict forward return for a single observation."""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Build feature array in correct order
        feature_values = []
        for name in self._feature_names:
            val = features.get(name, np.nan)
            feature_values.append(val if val is not None else np.nan)

        X = np.array([feature_values])
        prediction = self._model.predict(X)[0]
        return float(prediction)

    def predict_batch(self, features_df: pd.DataFrame) -> pd.Series:
        """Predict for multiple observations."""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Ensure columns are in correct order, fill missing with NaN
        X = features_df.reindex(columns=self._feature_names).values
        predictions = self._model.predict(X)
        return pd.Series(predictions, index=features_df.index)

    def get_feature_names(self) -> list[str]:
        """Return feature names."""
        return list(self._feature_names)

    def get_feature_importance(self) -> dict:
        """Return feature importance scores."""
        if self._model is None:
            return {}
        importance = self._model.feature_importances_
        return dict(zip(self._feature_names, importance.tolist()))
```

---

## FILE 3: `options-bot/ml/trainer.py`

```python
"""
XGBoost training pipeline.
Matches PROJECT_ARCHITECTURE.md Section 7 — Phase 1-3.

Full pipeline:
    1. Fetch historical stock bars from Alpaca
    2. Compute features (base + style-specific)
    3. Calculate forward return target
    4. Subsample to daily (1 sample per trading day)
    5. Walk-forward cross-validation (5-fold expanding window)
    6. Train final model
    7. Save model + metrics + feature names to DB
    8. Update profile status
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

logger = logging.getLogger("options-bot.ml.trainer")

# Bars per trading day (6.5 hours * 12 bars/hour for 5-min)
BARS_PER_DAY = 78

# Walk-forward CV folds
CV_FOLDS = 5

# Minimum samples required to train
MIN_TRAINING_SAMPLES = 200

# Target bar for daily subsample: 15:50 ET (10 min before close)
TARGET_HOUR = 15
TARGET_MINUTE = 50


def _prediction_horizon_to_bars(horizon: str) -> int:
    """Convert prediction horizon string to number of 5-min bars."""
    mapping = {
        "30min": 6,
        "1d": BARS_PER_DAY,
        "3d": BARS_PER_DAY * 3,
        "5d": BARS_PER_DAY * 5,
        "10d": BARS_PER_DAY * 10,
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
    else:
        return base


def _compute_all_features(bars_df: pd.DataFrame, preset: str) -> pd.DataFrame:
    """Compute base + style-specific features."""
    logger.info(f"Computing all features for preset '{preset}'")
    start = time.time()

    # Base features (stock only — options data added later)
    df = compute_base_features(bars_df.copy(), options_daily_df=None)

    # Style-specific features
    if preset == "swing":
        df = compute_swing_features(df)
    elif preset == "general":
        df = compute_general_features(df)

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


def _subsample_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Subsample to 1 bar per trading day — the bar closest to 15:50 ET.
    This avoids autocorrelation from adjacent 5-min bars.
    """
    logger.info(f"Subsampling {len(df)} bars to daily...")

    if df.index.tz is not None:
        eastern = df.index.tz_convert("US/Eastern")
    else:
        eastern = df.index.tz_localize("UTC").tz_convert("US/Eastern")

    # Add eastern time for filtering
    df = df.copy()
    df["_et_hour"] = eastern.hour
    df["_et_minute"] = eastern.minute
    df["_et_date"] = eastern.date

    # For each day, pick the bar closest to 15:50
    daily_samples = []
    for trade_date, day_group in df.groupby("_et_date"):
        # Target: 15:50 bar
        target_bars = day_group[
            (day_group["_et_hour"] == TARGET_HOUR) &
            (day_group["_et_minute"] >= TARGET_MINUTE - 5) &
            (day_group["_et_minute"] <= TARGET_MINUTE + 5)
        ]
        if len(target_bars) > 0:
            daily_samples.append(target_bars.iloc[-1:])
        elif len(day_group) > 0:
            # Fallback: use the last bar of the day
            daily_samples.append(day_group.iloc[-1:])

    if not daily_samples:
        logger.warning("No daily samples extracted!")
        return pd.DataFrame()

    result = pd.concat(daily_samples)
    result.drop(columns=["_et_hour", "_et_minute", "_et_date"], inplace=True)
    logger.info(f"Subsampled to {len(result)} daily observations")
    return result


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
            f"R²={r2:.4f}, DirAcc={dir_acc:.4f}"
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
        f"CV Results — MAE: {agg_metrics['mae']:.4f}, "
        f"RMSE: {agg_metrics['rmse']:.4f}, "
        f"R²: {agg_metrics['r2']:.4f}, "
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

    horizon_bars = _prediction_horizon_to_bars(prediction_horizon)
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
    start_date = end_date - timedelta(days=years_of_data * 365)

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
        f"({total_bars - has_target} bars at end excluded — no future data)"
    )

    # =====================================================================
    # STEP 4: Subsample to daily
    # =====================================================================
    logger.info("")
    logger.info("STEP 4: Subsampling to daily observations")
    logger.info("-" * 50)

    daily_df = _subsample_daily(featured_df)

    if daily_df.empty:
        logger.error("FATAL: No daily samples after subsampling")
        return {"status": "failed", "message": "No valid daily samples"}

    # Drop rows where target is NaN (end of dataset)
    daily_df = daily_df.dropna(subset=["target"])

    # Keep only feature columns + target
    available_features = [f for f in feature_names if f in daily_df.columns]
    missing_features = [f for f in feature_names if f not in daily_df.columns]
    if missing_features:
        logger.warning(f"Missing features (will be NaN): {missing_features}")
        for f in missing_features:
            daily_df[f] = np.nan

    X = daily_df[feature_names].copy()
    y = daily_df["target"].copy()

    # Drop rows where ALL features are NaN (very start of dataset)
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
            f"⚠️  DirAcc {dir_acc:.4f} < 0.52 threshold. "
            f"Model may not be predictive enough. "
            f"Training will continue but review metrics carefully."
        )
    else:
        logger.info(f"✅ DirAcc {dir_acc:.4f} >= 0.52 threshold. Looking good!")
    logger.info("=" * 50)

    # =====================================================================
    # STEP 6: Train final model on all data
    # =====================================================================
    logger.info("")
    logger.info("STEP 6: Training final model on all data")
    logger.info("-" * 50)

    step_start = time.time()
    final_model = XGBRegressor(
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

    # Add training_samples count to metrics
    cv_metrics["training_samples"] = len(X)
    # Remove fold_details from what we store (too verbose for DB)
    fold_details = cv_metrics.pop("fold_details", [])

    hyperparams = {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "prediction_horizon": prediction_horizon,
        "horizon_bars": horizon_bars,
        "daily_subsample": True,
    }

    now = datetime.utcnow().isoformat()

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

    pipeline_start_iso = datetime.utcfromtimestamp(pipeline_start).isoformat()
    asyncio.run(_save_to_db())

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
    logger.info(f"  R²:           {cv_metrics['r2']:.4f}")
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
```

---

## FILE 4: `options-bot/scripts/train_model.py`

```python
"""
Standalone model training script.

Usage:
    cd options-bot

    # Train using an existing profile (reads config from DB):
    python scripts/train_model.py --profile-id <uuid>

    # Train with explicit parameters (no profile required):
    python scripts/train_model.py --symbol TSLA --preset swing

    # Quick test with fewer years:
    python scripts/train_model.py --symbol TSLA --preset swing --years 2

Requires:
    - .env configured with ALPACA_API_KEY
    - Database initialized (run main.py once or backend must have started)
"""

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LOG_FORMAT, DB_PATH, PRESET_DEFAULTS

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("train_model")


def get_profile_config(profile_id: str) -> dict:
    """Load profile config from database."""
    import aiosqlite
    import asyncio

    async def _load():
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "preset": row["preset"],
                "symbols": json.loads(row["symbols"]),
                "config": json.loads(row["config"]),
            }

    return asyncio.run(_load())


def main():
    parser = argparse.ArgumentParser(description="Train an XGBoost model")
    parser.add_argument("--profile-id", type=str, help="Profile UUID to train for")
    parser.add_argument("--symbol", type=str, default="TSLA", help="Ticker symbol")
    parser.add_argument("--preset", type=str, default="swing", help="Trading preset")
    parser.add_argument("--years", type=int, default=6, help="Years of history")
    args = parser.parse_args()

    from ml.trainer import train_model

    if args.profile_id:
        # Load from database
        profile = get_profile_config(args.profile_id)
        if not profile:
            logger.error(f"Profile {args.profile_id} not found in database")
            sys.exit(1)

        logger.info(f"Training for profile: {profile['name']} ({profile['preset']})")
        symbol = profile["symbols"][0]  # Use first symbol
        preset = profile["preset"]
        horizon = profile["config"].get("prediction_horizon", "5d")
        profile_id = profile["id"]
    else:
        # Use command-line args — create a temporary profile ID
        symbol = args.symbol
        preset = args.preset
        if preset not in PRESET_DEFAULTS:
            logger.error(f"Invalid preset: {preset}. Options: {list(PRESET_DEFAULTS.keys())}")
            sys.exit(1)
        horizon = PRESET_DEFAULTS[preset]["prediction_horizon"]
        profile_id = str(uuid.uuid4())
        logger.info(f"Training with explicit params (temp profile: {profile_id})")

    result = train_model(
        profile_id=profile_id,
        symbol=symbol,
        preset=preset,
        prediction_horizon=horizon,
        years_of_data=args.years,
    )

    if result["status"] == "ready":
        logger.info("")
        logger.info("🎉 Training successful!")
        logger.info(f"   Model: {result['model_path']}")
        logger.info(f"   DirAcc: {result['metrics']['dir_acc']:.4f}")
        logger.info(f"   MAE: {result['metrics']['mae']:.4f}")
    else:
        logger.error(f"Training failed: {result.get('message', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## VERIFICATION

After creating all files, run these commands:

```bash
cd options-bot

# 1. Verify files exist
echo "=== Checking files ==="
for f in \
    ml/predictor.py \
    ml/xgboost_predictor.py \
    ml/trainer.py \
    scripts/train_model.py; do
    if [ -f "$f" ]; then echo "  ✅ $f"; else echo "  ❌ MISSING: $f"; fi
done

# 2. Verify imports
echo ""
echo "=== Testing imports ==="
python -c "from ml.predictor import ModelPredictor; print('  ✅ predictor.py')"
python -c "from ml.xgboost_predictor import XGBoostPredictor; print('  ✅ xgboost_predictor.py')"
python -c "from ml.trainer import train_model; print('  ✅ trainer.py')"

# 3. Quick training test — use 2 years for speed
#    This will take several minutes (data fetching + feature computation + CV)
echo ""
echo "=== Running training (2 years — quick test) ==="
python scripts/train_model.py --symbol TSLA --preset swing --years 2
```

## WHAT SUCCESS LOOKS LIKE

1. All 4 files created
2. Imports clean
3. Training completes with output showing all 8 steps
4. Walk-forward CV reports metrics for each fold
5. Directional accuracy > 50% (ideally > 52%)
6. Model file saved to `models/` directory
7. Final summary printed with all metrics
8. If run with `--profile-id`, profile status updated to 'ready' in DB

**Expected output pattern**:
```
STEP 1: Fetching historical stock bars from Alpaca
  Completed: ~XXX,XXX bars
STEP 2: Computing features
  Features computed in Xs
STEP 3: Calculating forward return target
  XXXX/XXXXX bars have valid targets
STEP 4: Subsampling to daily observations
  Subsampled to ~XXX daily observations
STEP 5: Walk-forward cross-validation
  Fold 1/5: MAE=X.XX, DirAcc=0.XX
  ...
CHECKPOINT: Directional Accuracy = 0.XX
STEP 6: Training final model
STEP 7: Saving model to disk
STEP 8: Saving metrics to database
TRAINING PIPELINE COMPLETE
```

**Timing expectation**: With 2 years of data:
- Data fetch: 1-3 min (many API pages)
- Feature computation: 10-30 sec
- CV + training: 10-30 sec
- Total: 2-5 minutes

With 6 years: 5-15 minutes total.

## WHAT FAILURE LOOKS LIKE

- Alpaca data fetch fails or returns empty
- Feature computation crashes (check for inf/NaN handling)
- Too few training samples after subsampling
- XGBoost throws errors on NaN features (it shouldn't — XGBoost handles NaN natively)
- Database save fails (check DB path)

## DO NOT

- Do NOT modify any files from previous prompts
- Do NOT create the EV filter, risk manager, or strategy yet (Prompt 06)
- Do NOT add options data collection to the training pipeline yet (future enhancement)
- Do NOT add hyperparameter tuning (keep default params for now)
- Do NOT try to train on 6 years in the test run — use --years 2 for verification
- Do NOT add any files not listed in this prompt

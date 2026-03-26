"""
Momentum Model Trainer — trains a classifier to detect whether a price move
currently in progress will continue.

Key difference from scalp/swing trainers:
- Labels are NOT "will price go up or down?"
- Labels ARE "given that price has already moved 0.3%+ in one direction,
  will it continue another 0.2%+ in the same direction within 30 minutes?"

Training data:
1. Fetch 6+ months of 1-minute bars
2. Compute base + momentum features
3. Find all "momentum events" (0.3%+ move in 15 min)
4. Label: did the move continue 0.2%+ more in the same direction within 30 min?
5. Train XGBoost binary classifier with walk-forward validation
6. Calibrate probabilities with isotonic regression

Usage:
    from ml.momentum_trainer import train_momentum_model
    result = train_momentum_model(profile_id, symbol)
"""

import json
import uuid
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MODELS_DIR, DB_PATH
from ml.feature_engineering.base_features import compute_base_features
from ml.feature_engineering.momentum_features import compute_momentum_features, get_momentum_feature_names

logger = logging.getLogger("options-bot.ml.momentum_trainer")

# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

# Momentum event detection: price must move this % in 15 min to qualify
MOMENTUM_DETECTION_PCT = 0.30

# Label: move must continue this % more in the same direction within 30 min
CONTINUATION_PCT = 0.20
CONTINUATION_WINDOW_BARS = 30  # 30 1-min bars

# Minimum bars for features to warm up
MIN_WARMUP_BARS = 60

# Walk-forward cross-validation folds
N_CV_FOLDS = 5

# Minimum training samples
MIN_TRAINING_SAMPLES = 200

# XGBoost hyperparameters — tuned for imbalanced binary classification
XGB_PARAMS = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 10,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "scale_pos_weight": 1.5,  # Boost positive class slightly (continuations are less common)
    "random_state": 42,
    "n_jobs": -1,
    "eval_metric": "logloss",
    # Note: use_label_encoder removed — deprecated in XGBoost 1.7+
}


# ═══════════════════════════════════════════════════════════════════════
# Label Construction
# ═══════════════════════════════════════════════════════════════════════

def _find_momentum_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Find all bars where a momentum event is in progress.

    A momentum event = price has moved >= MOMENTUM_DETECTION_PCT in one direction
    over the last 15 minutes.

    Returns a DataFrame with columns:
        - All original features
        - _event_direction: +1 (upward move) or -1 (downward move)
        - _move_size_pct: absolute size of the 15-min move
    """
    close = df["close"]

    # 15-min price change
    pct_change_15 = close.pct_change(15) * 100  # in percent

    # Filter to bars where |move| >= threshold
    mask = pct_change_15.abs() >= MOMENTUM_DETECTION_PCT
    events = df[mask].copy()
    events["_event_direction"] = np.sign(pct_change_15[mask])
    events["_move_size_pct"] = pct_change_15[mask].abs()

    return events


def _label_momentum_events(df: pd.DataFrame, events: pd.DataFrame) -> pd.Series:
    """
    For each momentum event, check if the move continued.

    Label = 1 if price moved another CONTINUATION_PCT in the same direction
    within CONTINUATION_WINDOW_BARS bars after the event.

    Label = 0 otherwise (reversal or stall).
    """
    close = df["close"]
    labels = pd.Series(index=events.index, dtype=float)

    for idx in events.index:
        pos = df.index.get_loc(idx)
        direction = events.loc[idx, "_event_direction"]
        entry_price = close.iloc[pos]

        # Look forward up to CONTINUATION_WINDOW_BARS
        end_pos = min(pos + CONTINUATION_WINDOW_BARS, len(df) - 1)
        if end_pos <= pos:
            labels.loc[idx] = np.nan  # Not enough future data
            continue

        future_prices = close.iloc[pos + 1:end_pos + 1]

        if direction > 0:
            # Upward move: did price go up another CONTINUATION_PCT?
            max_future = future_prices.max()
            continuation = (max_future - entry_price) / entry_price * 100
            labels.loc[idx] = 1.0 if continuation >= CONTINUATION_PCT else 0.0
        else:
            # Downward move: did price go down another CONTINUATION_PCT?
            min_future = future_prices.min()
            continuation = (entry_price - min_future) / entry_price * 100
            labels.loc[idx] = 1.0 if continuation >= CONTINUATION_PCT else 0.0

    return labels


# ═══════════════════════════════════════════════════════════════════════
# Walk-Forward Cross-Validation
# ═══════════════════════════════════════════════════════════════════════

def _walk_forward_cv(X: pd.DataFrame, y: pd.Series, n_folds: int = N_CV_FOLDS) -> dict:
    """
    Expanding window walk-forward CV.
    Returns metrics dict with accuracy, precision, recall, f1.
    """
    n = len(X)
    min_train = n // (n_folds + 1)  # Minimum training set size
    fold_size = (n - min_train) // n_folds

    all_preds = []
    all_true = []
    all_proba = []

    for fold in range(n_folds):
        train_end = min_train + fold * fold_size
        test_end = min(train_end + fold_size, n)

        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]
        X_test = X.iloc[train_end:test_end]
        y_test = y.iloc[train_end:test_end]

        if len(X_test) == 0 or len(X_train) == 0:
            continue

        model = XGBClassifier(**XGB_PARAMS)
        model.fit(X_train, y_train, verbose=False)

        preds = model.predict(X_test)
        proba = model.predict_proba(X_test)[:, 1]

        all_preds.extend(preds)
        all_true.extend(y_test)
        all_proba.extend(proba)

    all_preds = np.array(all_preds)
    all_true = np.array(all_true)
    all_proba = np.array(all_proba)

    return {
        "accuracy": float(accuracy_score(all_true, all_preds)),
        "precision": float(precision_score(all_true, all_preds, zero_division=0)),
        "recall": float(recall_score(all_true, all_preds, zero_division=0)),
        "f1": float(f1_score(all_true, all_preds, zero_division=0)),
        "positive_rate": float(all_true.mean()),
        "predicted_positive_rate": float(all_preds.mean()),
        "n_folds": n_folds,
        "n_test_samples": len(all_true),
    }


# ═══════════════════════════════════════════════════════════════════════
# Main Training Function
# ═══════════════════════════════════════════════════════════════════════

def train_momentum_model(
    profile_id: str,
    symbol: str,
    years_of_data: float = 0.5,
    db_path: str = None,
) -> dict:
    """
    Train a momentum continuation classifier.

    Args:
        profile_id: UUID of the profile
        symbol: Ticker (e.g., "SPY")
        years_of_data: How many years of historical data to use
        db_path: Override DB path

    Returns:
        Dict with status, model_id, metrics, etc.
    """
    import sqlite3

    started_at = datetime.now(timezone.utc).isoformat()
    pipeline_start = time.time()
    db_path = db_path or str(DB_PATH)
    model_id = str(uuid.uuid4())

    logger.info("=" * 70)
    logger.info("MOMENTUM MODEL TRAINING START")
    logger.info(f"  Profile:  {profile_id}")
    logger.info(f"  Symbol:   {symbol}")
    logger.info(f"  Data:     {years_of_data} years")
    logger.info("=" * 70)

    # ── STEP 1: Fetch historical 1-min bars ──────────────────────────
    logger.info("")
    logger.info("STEP 1: Fetching historical 1-minute bars")
    logger.info("-" * 50)

    try:
        from data.alpaca_provider import AlpacaStockProvider
        provider = AlpacaStockProvider()
        end_date = datetime.now(timezone.utc) - timedelta(hours=1)
        start_date = end_date - timedelta(days=int(years_of_data * 365))

        bars_df = provider.get_historical_bars(
            symbol, start_date, end_date, timeframe="1min"
        )

        if bars_df is None or len(bars_df) < 1000:
            msg = f"Insufficient data: got {len(bars_df) if bars_df is not None else 0} bars, need 1000+"
            logger.error(msg)
            return {"status": "error", "message": msg}

        logger.info(f"  Fetched {len(bars_df)} 1-min bars ({start_date.date()} to {end_date.date()})")
    except Exception as e:
        msg = f"Failed to fetch bars: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    # ── STEP 2: Compute features ─────────────────────────────────────
    logger.info("")
    logger.info("STEP 2: Computing base + momentum features")
    logger.info("-" * 50)

    try:
        featured_df = compute_base_features(bars_df, bars_per_day=390)
        featured_df = compute_momentum_features(featured_df)
        logger.info(f"  Features computed: {len(featured_df)} rows, {len(featured_df.columns)} columns")
    except Exception as e:
        msg = f"Feature computation failed: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    # ── STEP 3: Find momentum events and label them ──────────────────
    logger.info("")
    logger.info("STEP 3: Finding momentum events and labeling")
    logger.info("-" * 50)

    events = _find_momentum_events(featured_df)
    logger.info(f"  Momentum events detected: {len(events)} (from {len(featured_df)} total bars)")

    if len(events) < MIN_TRAINING_SAMPLES:
        msg = (
            f"Insufficient momentum events: {len(events)} < {MIN_TRAINING_SAMPLES}. "
            f"Need more historical data or lower MOMENTUM_DETECTION_PCT."
        )
        logger.error(msg)
        return {"status": "error", "message": msg}

    labels = _label_momentum_events(featured_df, events)
    events["_label"] = labels
    events = events.dropna(subset=["_label"])

    n_continue = int(events["_label"].sum())
    n_reverse = len(events) - n_continue
    pos_rate = n_continue / len(events) * 100

    logger.info(f"  Labeled events: {len(events)}")
    logger.info(f"  Continuations: {n_continue} ({pos_rate:.1f}%)")
    logger.info(f"  Reversals/stalls: {n_reverse} ({100 - pos_rate:.1f}%)")

    # ── STEP 4: Prepare training data ─────────────────────────────────
    logger.info("")
    logger.info("STEP 4: Preparing training data")
    logger.info("-" * 50)

    # Get feature columns (base + momentum, exclude helper columns)
    exclude_cols = {"_label", "_event_direction", "_move_size_pct", "target", "_target"}
    feature_cols = [c for c in events.columns if c not in exclude_cols and not c.startswith("_")]
    # Also exclude OHLCV raw columns
    raw_cols = {"open", "high", "low", "close", "volume"}
    feature_cols = [c for c in feature_cols if c not in raw_cols]

    X = events[feature_cols]
    y = events["_label"].astype(int)

    # Include event_direction as a feature (the model should know which direction the move is)
    X = X.copy()
    X["event_direction"] = events["_event_direction"]
    X["move_size_pct"] = events["_move_size_pct"]
    feature_cols = list(X.columns)

    logger.info(f"  Training samples: {len(X)}")
    logger.info(f"  Features: {len(feature_cols)}")

    # ── STEP 5: Walk-forward cross-validation ─────────────────────────
    logger.info("")
    logger.info("STEP 5: Walk-forward cross-validation")
    logger.info("-" * 50)

    cv_metrics = _walk_forward_cv(X, y)
    logger.info(f"  Accuracy:  {cv_metrics['accuracy']:.4f}")
    logger.info(f"  Precision: {cv_metrics['precision']:.4f}")
    logger.info(f"  Recall:    {cv_metrics['recall']:.4f}")
    logger.info(f"  F1:        {cv_metrics['f1']:.4f}")
    logger.info(f"  Positive rate (data): {cv_metrics['positive_rate']:.4f}")
    logger.info(f"  Positive rate (predicted): {cv_metrics['predicted_positive_rate']:.4f}")

    # ── STEP 6: Train final model on all data ─────────────────────────
    logger.info("")
    logger.info("STEP 6: Training final model on all data")
    logger.info("-" * 50)

    # Split: 80% train, 20% calibration holdout
    split_idx = int(len(X) * 0.8)
    X_train, X_cal = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_cal = y.iloc[:split_idx], y.iloc[split_idx:]

    model = XGBClassifier(**XGB_PARAMS)
    model.fit(X_train, y_train, verbose=False)

    logger.info(f"  Model trained: {XGB_PARAMS['n_estimators']} trees, depth={XGB_PARAMS['max_depth']}")

    # ── STEP 7: Isotonic calibration ──────────────────────────────────
    logger.info("")
    logger.info("STEP 7: Calibrating probabilities (isotonic regression)")
    logger.info("-" * 50)

    cal_proba = model.predict_proba(X_cal)[:, 1]

    calibrator = None
    try:
        calibrator = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip")
        calibrator.fit(cal_proba, y_cal)

        # Evaluate calibration
        cal_pred = calibrator.predict(cal_proba)
        cal_acc = accuracy_score(y_cal, (cal_pred >= 0.5).astype(int))
        logger.info(f"  Calibration holdout accuracy: {cal_acc:.4f}")
        logger.info(f"  Calibrator fitted on {len(X_cal)} samples")
    except Exception as e:
        logger.warning(f"  Calibration failed (non-fatal): {e}")
        calibrator = None

    # ── STEP 8: Feature importance ────────────────────────────────────
    logger.info("")
    logger.info("STEP 8: Feature importance analysis")
    logger.info("-" * 50)

    importances = model.feature_importances_
    feat_imp = sorted(zip(feature_cols, importances), key=lambda x: -x[1])

    logger.info("  Top 15 features:")
    for name, imp in feat_imp[:15]:
        logger.info(f"    {name:35} {imp:.4f}")

    zero_importance = [name for name, imp in feat_imp if imp == 0]
    if zero_importance:
        logger.warning(f"  {len(zero_importance)} features have ZERO importance: {zero_importance}")

    # ── STEP 9: Save model ────────────────────────────────────────────
    logger.info("")
    logger.info("STEP 9: Saving model")
    logger.info("-" * 50)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_filename = f"{profile_id}_momentum_{symbol}_{model_id[:8]}.joblib"
    model_path = str(MODELS_DIR / model_filename)

    save_data = {
        "model": model,
        "feature_names": feature_cols,
        "calibrator": calibrator,
        "metadata": {
            "symbol": symbol,
            "model_type": "momentum_classifier",
            "momentum_detection_pct": MOMENTUM_DETECTION_PCT,
            "continuation_pct": CONTINUATION_PCT,
            "continuation_window_bars": CONTINUATION_WINDOW_BARS,
            "training_samples": len(X),
            "positive_rate": float(y.mean()),
            "cv_accuracy": cv_metrics["accuracy"],
            "cv_precision": cv_metrics["precision"],
            "cv_recall": cv_metrics["recall"],
            "cv_f1": cv_metrics["f1"],
        },
    }
    joblib.dump(save_data, model_path)
    logger.info(f"  Saved to: {model_path}")

    # ── STEP 10: Save to database ─────────────────────────────────────
    logger.info("")
    logger.info("STEP 10: Updating database")
    logger.info("-" * 50)

    metrics = {
        **cv_metrics,
        "training_samples": len(X),
        "calibration_samples": len(X_cal),
        "features_used": len(feature_cols),
        "zero_importance_features": len(zero_importance),
    }

    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO models
               (id, profile_id, model_type, file_path, status,
                training_started_at, training_completed_at,
                data_start_date, data_end_date,
                metrics, feature_names, hyperparameters, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                model_id, profile_id, "momentum_classifier", model_path, "ready",
                started_at, datetime.now(timezone.utc).isoformat(),
                bars_df.index[0].strftime("%Y-%m-%d"),
                bars_df.index[-1].strftime("%Y-%m-%d"),
                json.dumps(metrics),
                json.dumps(feature_cols),
                json.dumps(XGB_PARAMS),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        # Update profile to point to new model
        conn.execute(
            "UPDATE profiles SET model_id = ?, updated_at = ? WHERE id = ?",
            (model_id, datetime.now(timezone.utc).isoformat(), profile_id),
        )
        conn.commit()
        conn.close()
        logger.info(f"  Database updated: model_id={model_id}")
    except Exception as e:
        msg = f"Database update failed: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg, "model_path": model_path}

    # ── Summary ───────────────────────────────────────────────────────
    elapsed = time.time() - pipeline_start
    logger.info("")
    logger.info("=" * 70)
    logger.info("MOMENTUM MODEL TRAINING COMPLETE")
    logger.info(f"  Model ID:    {model_id}")
    logger.info(f"  Samples:     {len(X)} momentum events")
    logger.info(f"  CV Accuracy: {cv_metrics['accuracy']:.4f}")
    logger.info(f"  CV F1:       {cv_metrics['f1']:.4f}")
    logger.info(f"  Precision:   {cv_metrics['precision']:.4f}")
    logger.info(f"  Recall:      {cv_metrics['recall']:.4f}")
    logger.info(f"  Time:        {elapsed:.1f}s")
    logger.info("=" * 70)

    return {
        "status": "completed",
        "model_id": model_id,
        "model_path": model_path,
        "metrics": metrics,
        "message": (
            f"Momentum model trained: {len(X)} events, "
            f"accuracy={cv_metrics['accuracy']:.3f}, "
            f"F1={cv_metrics['f1']:.3f}"
        ),
    }

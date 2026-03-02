"""
TFT (Temporal Fusion Transformer) training pipeline.
Matches PROJECT_ARCHITECTURE.md Section 7 — Phase 4: TFT model.

Pipeline (mirrors structure of ml/trainer.py):
    1. Fetch historical stock bars from Alpaca (same as XGBoost trainer)
    2. Compute features (same feature set as XGBoost)
    3. Build sliding-window sequence dataset (TFT-specific: NOT daily subsampled)
    4. Scale target (standardize forward return — required for TFT stability)
    5. Walk-forward CV (3 folds — TFT trains slower than XGBoost)
    6. Train final model on all data
    7. Save model directory (model.pt + metadata.json via TFTPredictor.save())
    8. Save model record to database

Key difference from XGBoost:
    XGBoost trains on 1 snapshot per day (~1,500 samples for 6 years).
    TFT trains on overlapping sliding windows of 60 bars. Each window covers
    60 consecutive 5-minute bars. With 6 years of 5-min bars (~120,000 bars),
    we get ~120,000 windows — but stride=BARS_PER_DAY (78) to avoid excessive
    overlap and memory pressure, giving ~1,540 non-overlapping daily windows,
    which is comparable to XGBoost's training set size.

The stride ensures adjacent windows share only small overlapping regions while
still capturing the temporal patterns that TFT learns better than XGBoost.
"""

import asyncio
import json
import logging
import time
import uuid
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH, MODELS_DIR
from ml.tft_predictor import TFTPredictor, ENCODER_LENGTH, PREDICTION_LENGTH, GROUP_ID

logger = logging.getLogger("options-bot.ml.tft_trainer")

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

BARS_PER_DAY = 78       # 5-min bars per 6.5-hour trading day (matches trainer.py)
CV_FOLDS = 3            # 3 folds — TFT is 10-20x slower than XGBoost
MAX_EPOCHS = 30         # Cap per fold; early stopping usually fires before this
EARLY_STOPPING_PATIENCE = 5
BATCH_SIZE = 64
GRADIENT_CLIP = 0.1
HIDDEN_SIZE = 64        # TFT hidden layer size — balanced accuracy vs train time
ATTENTION_HEAD_SIZE = 4
DROPOUT = 0.1
LEARNING_RATE = 1e-3    # Starting LR; pytorch-lightning adjusts via scheduler
STRIDE = BARS_PER_DAY   # One window per trading day (78 bars stride)
TARGET_COL = "_target_scaled"   # Column name for scaled forward return
MAX_TRAIN_WINDOWS = 3000  # Cap training samples per dataset for CPU performance


# ─────────────────────────────────────────────────────────────────────────────
# Training helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_strided_loader(dataset, batch_size: int, shuffle: bool = True):
    """
    Create a DataLoader that subsamples a TimeSeriesDataSet by STRIDE.

    With 280K 5-min bars, TimeSeriesDataSet creates ~280K windows.
    Striding by BARS_PER_DAY (78) reduces to ~3,600 windows — one per
    trading day — which is comparable to XGBoost's training set size.
    """
    from torch.utils.data import DataLoader, Subset

    n = len(dataset)
    if n > MAX_TRAIN_WINDOWS:
        step = max(1, n // MAX_TRAIN_WINDOWS)
        indices = list(range(0, n, step))
        subset = Subset(dataset, indices)
        logger.info(f"  Subsampled {n} → {len(indices)} windows (step={step})")
    else:
        subset = dataset
        logger.info(f"  Using all {n} windows")

    return DataLoader(
        subset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=0,
        collate_fn=dataset._collate_fn,
    )


def _make_epoch_logger(pl_module, label: str = ""):
    """Create a Lightning Callback that logs epoch progress."""

    class EpochLogger(pl_module.Callback):
        def on_train_epoch_end(self, trainer, model):
            epoch = trainer.current_epoch + 1
            metrics = trainer.callback_metrics
            loss = metrics.get("train_loss")
            val_loss = metrics.get("val_loss")
            parts = [f"{label}Epoch {epoch}/{trainer.max_epochs}"]
            if loss is not None:
                parts.append(f"loss={float(loss):.4f}")
            if val_loss is not None:
                parts.append(f"val={float(val_loss):.4f}")
            logger.info("  " + " | ".join(parts))

    return EpochLogger()


# ─────────────────────────────────────────────────────────────────────────────
# Feature helpers (reused from trainer.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

def _get_feature_names(preset: str) -> list[str]:
    """Get the full ordered list of feature column names for a preset."""
    from ml.feature_engineering.base_features import get_base_feature_names
    from ml.feature_engineering.swing_features import get_swing_feature_names
    from ml.feature_engineering.general_features import get_general_feature_names

    base = get_base_feature_names()
    if preset == "swing":
        return base + get_swing_feature_names()
    elif preset == "general":
        return base + get_general_feature_names()
    return base


def _compute_all_features(bars_df: pd.DataFrame, preset: str) -> pd.DataFrame:
    """Compute base + style-specific features, including options data from Theta."""
    from ml.feature_engineering.base_features import compute_base_features
    from ml.feature_engineering.swing_features import compute_swing_features
    from ml.feature_engineering.general_features import compute_general_features
    from config import PRESET_DEFAULTS

    logger.info(f"Computing features for preset='{preset}'")

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

    df = compute_base_features(bars_df.copy(), options_daily_df=options_daily_df)
    if preset == "swing":
        df = compute_swing_features(df)
    elif preset == "general":
        df = compute_general_features(df)
    return df


def _prediction_horizon_to_bars(horizon: str) -> int:
    """Convert prediction horizon string to number of 5-min bars."""
    mapping = {
        "30min": 6,
        "1d":  BARS_PER_DAY,
        "3d":  BARS_PER_DAY * 3,
        "5d":  BARS_PER_DAY * 5,
        "10d": BARS_PER_DAY * 10,
    }
    if horizon not in mapping:
        raise ValueError(f"Unknown prediction_horizon: {horizon!r}. Supported: {list(mapping)}")
    return mapping[horizon]


# ─────────────────────────────────────────────────────────────────────────────
# Sequence dataset construction
# ─────────────────────────────────────────────────────────────────────────────

def _build_sequence_df(
    featured_df: pd.DataFrame,
    feature_names: list[str],
    horizon_bars: int,
    stride: int = STRIDE,
) -> pd.DataFrame:
    """
    Build a flat DataFrame of sliding windows suitable for pytorch-forecasting
    TimeSeriesDataSet.

    Each window consists of ENCODER_LENGTH consecutive 5-min bars. The target
    for window i is the forward return at bar[i + ENCODER_LENGTH - 1 + horizon_bars].

    Stride controls how much windows overlap:
        stride = 1:           maximum overlap (expensive, not needed)
        stride = BARS_PER_DAY: one window per trading day (efficient, ~daily resolution)

    Output schema:
        time_idx    int     Global bar index (0, 1, 2, ...)
        group_id    str     Always GROUP_ID constant (single asset)
        <features>  float   All feature columns (NaN filled with 0.0)
        _target_scaled float Standardized forward return (set to 0.0 for encoder rows)

    TimeSeriesDataSet semantics:
        - Encoder rows: time_idx in [window_start, window_start + ENCODER_LENGTH - 1]
        - Decoder row:  time_idx = window_start + ENCODER_LENGTH
          (the future step where the prediction is made)
        - The target on the decoder row is the scaled forward return.

    We construct the DataFrame as a flat sequence of ALL bars, not per-window.
    TimeSeriesDataSet uses min_encoder_length/max_encoder_length to slice windows
    internally. We just need:
        - A contiguous time_idx
        - A target column on each row (the forward return for that bar)
        - Feature columns on each bar

    Args:
        featured_df: DataFrame with DatetimeIndex, all feature columns computed
        feature_names: Ordered list of feature columns to include
        horizon_bars: Number of 5-min bars in the prediction horizon
        stride: Not used here (TimeSeriesDataSet handles its own windowing)

    Returns:
        DataFrame ready for TimeSeriesDataSet. Rows with NaN targets are dropped.
    """
    logger.info(
        f"Building sequence DataFrame: {len(featured_df)} bars, "
        f"horizon={horizon_bars} bars"
    )

    df = featured_df.copy()

    # Calculate forward return target (same formula as XGBoost trainer)
    future_close = df["close"].shift(-horizon_bars)
    df["_target_raw"] = ((future_close / df["close"]) - 1) * 100

    # Drop rows where target is NaN (last horizon_bars rows have no future data)
    df = df.dropna(subset=["_target_raw"])
    logger.info(f"  After dropping NaN targets: {len(df)} bars")

    # Drop rows where features are all NaN (initial lookback period)
    # Keep rows where at least some features are valid
    feature_cols_present = [c for c in feature_names if c in df.columns]
    df = df.dropna(subset=feature_cols_present, how="all")
    logger.info(f"  After dropping all-NaN feature rows: {len(df)} bars")

    if len(df) < ENCODER_LENGTH + 10:
        raise ValueError(
            f"Insufficient data for TFT: {len(df)} rows after cleanup. "
            f"Need at least {ENCODER_LENGTH + 10}."
        )

    # Save original DatetimeIndex before resetting (used by predict_dataset
    # to map predictions back to timestamps for ensemble alignment)
    df["_original_dt_index"] = df.index

    # Add required TimeSeriesDataSet columns
    df = df.reset_index(drop=True)
    df["time_idx"] = df.index.astype(int)
    df["group_id"] = GROUP_ID

    # Fill NaN features with 0.0 (TFT variable selection handles noisy features)
    for col in feature_cols_present:
        df[col] = df[col].fillna(0.0)

    # Ensure all expected feature columns exist (fill missing with 0.0)
    for col in feature_names:
        if col not in df.columns:
            df[col] = 0.0

    # Target column placeholder (will be scaled in train_tft_model)
    df[TARGET_COL] = 0.0  # Overwritten after scaling

    cols_to_keep = ["time_idx", "group_id", "_original_dt_index"] + feature_names + ["_target_raw", TARGET_COL]
    df = df[[c for c in cols_to_keep if c in df.columns]]

    logger.info(f"  Sequence DataFrame built: {len(df)} rows, {len(df.columns)} columns")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward CV
# ─────────────────────────────────────────────────────────────────────────────

def _walk_forward_cv_tft(
    seq_df: pd.DataFrame,
    feature_names: list[str],
    n_folds: int = CV_FOLDS,
) -> dict:
    """
    Walk-forward cross-validation for TFT using expanding windows.

    Mirrors _walk_forward_cv() in trainer.py but uses TimeSeriesDataSet.

    Each fold:
        - Train set: first (fold+1) * fold_size rows
        - Val set:   next fold_size rows
        - Trains a new TFT from scratch on the train set
        - Evaluates on the val set (MAE, RMSE, R², directional accuracy)

    Args:
        seq_df: Flat sequence DataFrame from _build_sequence_df()
        feature_names: Ordered list of feature column names
        n_folds: Number of CV folds (default 3)

    Returns:
        Dict with aggregate metrics (same schema as XGBoost CV output)
    """
    from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
    from pytorch_forecasting.metrics import MAE
    import lightning.pytorch as pl
    from lightning.pytorch.callbacks import EarlyStopping

    logger.info(f"Running {n_folds}-fold walk-forward CV on {len(seq_df)} bars")

    n = len(seq_df)
    fold_size = n // (n_folds + 1)
    min_train_size = ENCODER_LENGTH * 10  # Need at least 10x encoder length to train

    all_actuals = []
    all_preds = []
    fold_metrics = []

    for fold in range(n_folds):
        train_end_idx = fold_size * (fold + 1)
        val_start_idx = train_end_idx
        val_end_idx = min(train_end_idx + fold_size, n)

        if train_end_idx < min_train_size:
            logger.warning(f"Fold {fold+1}: train set too small ({train_end_idx} < {min_train_size}), skipping")
            continue

        if val_end_idx <= val_start_idx:
            logger.warning(f"Fold {fold+1}: no validation data, skipping")
            continue

        train_df = seq_df.iloc[:train_end_idx].copy()
        val_df = seq_df.iloc[val_start_idx:val_end_idx].copy()

        # Re-index time_idx to be contiguous; val continues from train
        train_df = train_df.reset_index(drop=True)
        train_df["time_idx"] = train_df.index.astype(int)
        val_df = val_df.reset_index(drop=True)
        val_df["time_idx"] = (val_df.index + len(train_df)).astype(int)

        logger.info(
            f"  Fold {fold+1}/{n_folds}: train={len(train_df)} bars, "
            f"val={len(val_df)} bars"
        )

        try:
            # Scale target within this fold (fit scaler on train only)
            target_mean = float(train_df["_target_raw"].mean())
            target_std = float(train_df["_target_raw"].std())
            if target_std < 1e-8:
                target_std = 1.0

            train_df[TARGET_COL] = (train_df["_target_raw"] - target_mean) / target_std
            val_df[TARGET_COL] = (val_df["_target_raw"] - target_mean) / target_std

            # Build datasets (drop _original_dt_index — TimeSeriesDataSet can't handle datetime cols)
            train_ds_df = train_df.drop(columns=["_original_dt_index"], errors="ignore")
            val_ds_df = val_df.drop(columns=["_original_dt_index"], errors="ignore")
            train_dataset = _build_timeseries_dataset(train_ds_df, feature_names, training=True)
            val_dataset = _build_timeseries_dataset(val_ds_df, feature_names, training=False)

            if train_dataset is None or val_dataset is None:
                logger.warning(f"  Fold {fold+1}: could not build dataset, skipping")
                continue

            # Subsample training and validation windows for CPU performance
            train_loader = _make_strided_loader(train_dataset, BATCH_SIZE, shuffle=True)
            val_loader = _make_strided_loader(val_dataset, BATCH_SIZE * 2, shuffle=False)

            # Build and train TFT
            model = TemporalFusionTransformer.from_dataset(
                train_dataset,
                learning_rate=LEARNING_RATE,
                hidden_size=HIDDEN_SIZE,
                attention_head_size=ATTENTION_HEAD_SIZE,
                dropout=DROPOUT,
                hidden_continuous_size=32,
                loss=MAE(),
                log_interval=-1,
                reduce_on_plateau_patience=3,
            )

            early_stop = EarlyStopping(
                monitor="val_loss",
                patience=EARLY_STOPPING_PATIENCE,
                mode="min",
                verbose=False,
            )

            epoch_logger = _make_epoch_logger(pl, f"Fold {fold+1} ")

            trainer = pl.Trainer(
                max_epochs=MAX_EPOCHS,
                gradient_clip_val=GRADIENT_CLIP,
                callbacks=[early_stop, epoch_logger],
                enable_progress_bar=False,
                enable_model_summary=False,
                logger=False,
                accelerator="auto",
                devices=1,
            )

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                trainer.fit(model, train_loader, val_loader)

            # Predict on validation set
            with torch.no_grad():
                val_preds_raw = []
                val_actuals_raw = []
                for batch_x, batch_y in val_loader:
                    output = model(batch_x)
                    pred = output.prediction
                    if pred.ndim == 3:
                        # Shape: [batch, time, quantiles]
                        # MAE loss → 1 quantile; QuantileLoss → 7 (median at index 3)
                        q_idx = min(3, pred.shape[2] - 1)
                        median = pred[:, 0, q_idx].cpu().numpy()
                    elif pred.ndim == 2:
                        median = pred[:, 0].cpu().numpy()
                    else:
                        median = pred.cpu().numpy()

                    # Invert scaling
                    median_raw = median * target_std + target_mean

                    actuals = batch_y[0].squeeze(-1).cpu().numpy()
                    actuals_raw = actuals * target_std + target_mean

                    val_preds_raw.extend(median_raw.tolist())
                    val_actuals_raw.extend(actuals_raw.tolist())

            val_preds_arr = np.array(val_preds_raw)
            val_actuals_arr = np.array(val_actuals_raw)

            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            mae = float(mean_absolute_error(val_actuals_arr, val_preds_arr))
            rmse = float(np.sqrt(mean_squared_error(val_actuals_arr, val_preds_arr)))
            r2 = float(r2_score(val_actuals_arr, val_preds_arr))
            dir_acc = float(((val_actuals_arr > 0) == (val_preds_arr > 0)).mean())

            fold_metrics.append({
                "fold": fold + 1,
                "train_size": len(train_df),
                "val_size": len(val_df),
                "mae": mae,
                "rmse": rmse,
                "r2": r2,
                "dir_acc": dir_acc,
            })

            all_actuals.extend(val_actuals_arr.tolist())
            all_preds.extend(val_preds_arr.tolist())

            logger.info(
                f"  Fold {fold+1} results: MAE={mae:.4f}, RMSE={rmse:.4f}, "
                f"R²={r2:.4f}, DirAcc={dir_acc:.4f}"
            )

        except Exception as e:
            logger.error(f"  Fold {fold+1} failed: {e}", exc_info=True)
            continue

    if not fold_metrics:
        logger.error("No CV folds completed successfully")
        return {
            "mae": 999.0, "rmse": 999.0, "r2": -999.0, "dir_acc": 0.5,
            "cv_folds": 0, "fold_details": [],
        }

    all_actuals_arr = np.array(all_actuals)
    all_preds_arr = np.array(all_preds)

    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    agg = {
        "mae":     float(mean_absolute_error(all_actuals_arr, all_preds_arr)),
        "rmse":    float(np.sqrt(mean_squared_error(all_actuals_arr, all_preds_arr))),
        "r2":      float(r2_score(all_actuals_arr, all_preds_arr)),
        "dir_acc": float(((all_actuals_arr > 0) == (all_preds_arr > 0)).mean()),
        "cv_folds": len(fold_metrics),
        "fold_details": fold_metrics,
    }

    logger.info(
        f"CV Results — MAE: {agg['mae']:.4f}, RMSE: {agg['rmse']:.4f}, "
        f"R²: {agg['r2']:.4f}, DirAcc: {agg['dir_acc']:.4f}"
    )
    return agg


def _build_timeseries_dataset(
    df: pd.DataFrame,
    feature_names: list[str],
    training: bool = True,
):
    """
    Construct a pytorch-forecasting TimeSeriesDataSet from a flat bar DataFrame.

    Returns None if the DataFrame is too small to form valid windows.
    """
    from pytorch_forecasting import TimeSeriesDataSet

    min_rows_needed = ENCODER_LENGTH + PREDICTION_LENGTH + 5
    if len(df) < min_rows_needed:
        logger.warning(
            f"DataFrame too small for TimeSeriesDataSet: {len(df)} < {min_rows_needed}"
        )
        return None

    feature_cols = [c for c in feature_names if c in df.columns]

    try:
        dataset = TimeSeriesDataSet(
            df,
            time_idx="time_idx",
            target=TARGET_COL,
            group_ids=["group_id"],
            min_encoder_length=ENCODER_LENGTH,
            max_encoder_length=ENCODER_LENGTH,
            min_prediction_length=PREDICTION_LENGTH,
            max_prediction_length=PREDICTION_LENGTH,
            time_varying_unknown_reals=feature_cols,
            add_relative_time_idx=True,
            add_target_scales=False,
            add_encoder_length=False,
            allow_missing_timesteps=True,
        )
        return dataset
    except Exception as e:
        logger.error(f"TimeSeriesDataSet construction failed: {e}", exc_info=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Predict dataset (used by EnsemblePredictor in P4P4)
# ─────────────────────────────────────────────────────────────────────────────

def predict_dataset(
    model,              # Trained TemporalFusionTransformer
    seq_df: pd.DataFrame,
    feature_names: list[str],
    target_mean: float,
    target_std: float,
) -> pd.Series:
    """
    Run batch inference on a sequence DataFrame using a trained TFT model.

    Used by EnsemblePredictor to get TFT predictions during meta-learner training.
    Returns a Series of predicted forward return % values (unscaled), indexed
    to match the rows of seq_df that had valid predictions.

    Args:
        model: Trained TemporalFusionTransformer (from pytorch-forecasting)
        seq_df: Flat bar DataFrame (time_idx, group_id, features, _target_raw, TARGET_COL)
        feature_names: Ordered list of feature column names
        target_mean: Mean used to scale the target during training
        target_std: Std used to scale the target during training

    Returns:
        pd.Series of predictions (unscaled %) indexed by seq_df row index.
        Rows that couldn't be predicted (near edges) will be missing.
    """
    # Drop _original_dt_index before passing to TimeSeriesDataSet (it can't handle
    # datetime columns), but we keep seq_df intact so we can use it for alignment below.
    ds_df = seq_df.drop(columns=["_original_dt_index"], errors="ignore")
    dataset = _build_timeseries_dataset(ds_df, feature_names, training=False)
    if dataset is None:
        return pd.Series(dtype=float)

    loader = dataset.to_dataloader(train=False, batch_size=BATCH_SIZE * 2, num_workers=0)

    all_preds = []
    model.eval()
    with torch.no_grad():
        for batch_x, _ in loader:
            output = model(batch_x)
            pred = output.prediction
            if pred.ndim == 3:
                q_idx = min(3, pred.shape[2] - 1)
                median = pred[:, 0, q_idx].cpu().numpy()
            elif pred.ndim == 2:
                median = pred[:, 0].cpu().numpy()
            else:
                median = pred.cpu().numpy()
            median_raw = median * target_std + target_mean
            all_preds.extend(median_raw.tolist())

    # TimeSeriesDataSet with encoder_length=60 and prediction_length=1 produces
    # its first prediction for the bar at time_idx = ENCODER_LENGTH (the decoder step).
    # Each subsequent window shifts by 1. Total predictions = len(df) - ENCODER_LENGTH.
    start_idx = ENCODER_LENGTH
    end_idx = start_idx + len(all_preds)

    # Use original DatetimeIndex if available (for ensemble alignment with XGBoost)
    if "_original_dt_index" in seq_df.columns:
        dt_vals = seq_df["_original_dt_index"].iloc[start_idx:end_idx]
        index = dt_vals.values[:len(all_preds)]
        return pd.Series(all_preds[:len(index)], index=index)

    index = seq_df.index[start_idx:end_idx] if end_idx <= len(seq_df) else seq_df.index[start_idx:]
    return pd.Series(all_preds[:len(index)], index=index)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers (mirrors trainer.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

def _save_tft_model_to_db(
    model_id: str,
    profile_id: str,
    model_dir: str,
    preset: str,
    symbol: str,
    data_start_date: str,
    data_end_date: str,
    metrics: dict,
    feature_names: list[str],
    hyperparams: dict,
    pipeline_start_iso: str,
    db_path: str,
):
    """Insert TFT model record and update profile to point to it."""
    import aiosqlite
    import concurrent.futures

    async def _save():
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """INSERT INTO models
                   (id, profile_id, model_type, file_path, status,
                    training_started_at, training_completed_at,
                    data_start_date, data_end_date,
                    metrics, feature_names, hyperparameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    model_id, profile_id, "tft", model_dir, "ready",
                    pipeline_start_iso, now,
                    data_start_date, data_end_date,
                    json.dumps(metrics),
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
        logger.info(f"TFT model saved to DB: model_id={model_id}")

    try:
        asyncio.run(_save())
    except RuntimeError:
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(asyncio.run, _save()).result(timeout=60)
        except Exception as e:
            logger.error(f"_save_tft_to_db fallback failed: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"_save_tft_to_db failed: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def train_tft_model(
    profile_id: str,
    symbol: str,
    preset: str,
    prediction_horizon: str = "5d",
    years_of_data: int = 6,
    db_path: str = None,
) -> dict:
    """
    Full TFT training pipeline. Mirrors train_model() in trainer.py.

    Args:
        profile_id: UUID of the profile
        symbol: Ticker symbol (e.g., "TSLA")
        preset: Trading preset ("swing" or "general")
        prediction_horizon: Forward return horizon string (e.g., "5d")
        years_of_data: How many years of history to fetch from Alpaca
        db_path: Override DB path (for testing)

    Returns:
        Dict with keys: status, model_id, model_dir, metrics, feature_names,
                        data_range, training_samples, total_time_seconds
        On failure: {status: "error", message: str}
    """
    import aiosqlite

    pipeline_start = time.time()
    pipeline_start_iso = datetime.utcnow().isoformat()
    db_path = db_path or str(DB_PATH)
    model_id = str(uuid.uuid4())
    model_dir = str(MODELS_DIR / f"{profile_id}_tft_{model_id[:8]}")

    logger.info("=" * 70)
    logger.info("TFT TRAINING PIPELINE START")
    logger.info(f"  Profile:  {profile_id}")
    logger.info(f"  Symbol:   {symbol}")
    logger.info(f"  Preset:   {preset}")
    logger.info(f"  Horizon:  {prediction_horizon}")
    logger.info(f"  Years:    {years_of_data}")
    logger.info(f"  Model ID: {model_id}")
    logger.info(f"  Model Dir: {model_dir}")
    logger.info(f"  GPU: {'available' if torch.cuda.is_available() else 'not available (CPU)'}")
    logger.info("=" * 70)

    horizon_bars = _prediction_horizon_to_bars(prediction_horizon)
    feature_names = _get_feature_names(preset)

    # =========================================================================
    # STEP 1: Fetch historical stock bars from Alpaca
    # =========================================================================
    logger.info("")
    logger.info("STEP 1: Fetching historical stock bars from Alpaca")
    logger.info("-" * 50)

    try:
        from data.alpaca_provider import AlpacaStockProvider
        provider = AlpacaStockProvider()
        end_date = datetime.now() - timedelta(hours=1)
        start_date = end_date - timedelta(days=years_of_data * 365 + 30)

        bars_df = provider.get_historical_bars(symbol, start_date, end_date, timeframe="5min")
    except Exception as e:
        msg = f"Failed to fetch bars from Alpaca: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    if bars_df is None or bars_df.empty:
        msg = f"No bars returned for {symbol}"
        logger.error(msg)
        return {"status": "error", "message": msg}

    # Tag bars_df with symbol so options fetcher can use it
    bars_df.attrs["symbol"] = symbol

    data_start_date = str(bars_df.index.min().date())
    data_end_date = str(bars_df.index.max().date())
    logger.info(f"Fetched {len(bars_df)} bars: {data_start_date} to {data_end_date}")

    # =========================================================================
    # STEP 2: Compute features
    # =========================================================================
    logger.info("")
    logger.info("STEP 2: Computing features")
    logger.info("-" * 50)

    try:
        featured_df = _compute_all_features(bars_df, preset)
        logger.info(f"Features computed: {len(featured_df)} rows, {len(featured_df.columns)} cols")
    except Exception as e:
        msg = f"Feature computation failed: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    # =========================================================================
    # STEP 3: Build sliding-window sequence DataFrame
    # =========================================================================
    logger.info("")
    logger.info("STEP 3: Building sequence DataFrame")
    logger.info("-" * 50)

    try:
        seq_df = _build_sequence_df(featured_df, feature_names, horizon_bars)
    except ValueError as e:
        msg = str(e)
        logger.error(msg)
        return {"status": "error", "message": msg}
    except Exception as e:
        msg = f"Sequence building failed: {e}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "message": msg}

    training_samples = len(seq_df)
    logger.info(f"Sequence DataFrame: {training_samples} rows")

    # =========================================================================
    # STEP 4: Scale target
    # =========================================================================
    logger.info("")
    logger.info("STEP 4: Scaling target")
    logger.info("-" * 50)

    target_mean = float(seq_df["_target_raw"].mean())
    target_std = float(seq_df["_target_raw"].std())
    if target_std < 1e-8:
        target_std = 1.0
    seq_df[TARGET_COL] = (seq_df["_target_raw"] - target_mean) / target_std

    logger.info(f"Target mean={target_mean:.4f}%, std={target_std:.4f}%")
    logger.info(f"Target scaled to mean~0, std~1")

    # =========================================================================
    # STEP 5: Walk-forward cross-validation
    # =========================================================================
    logger.info("")
    logger.info("STEP 5: Walk-forward cross-validation (3 folds)")
    logger.info("-" * 50)

    step_start = time.time()
    cv_metrics = _walk_forward_cv_tft(seq_df, feature_names, n_folds=CV_FOLDS)
    logger.info(f"CV complete in {time.time() - step_start:.0f}s")

    if cv_metrics["dir_acc"] < 0.48:
        logger.warning(
            f"TFT directional accuracy low: {cv_metrics['dir_acc']:.4f}. "
            f"Training will continue but review results carefully."
        )
    else:
        logger.info(f"TFT DirAcc {cv_metrics['dir_acc']:.4f} — proceeding to final training")

    # =========================================================================
    # STEP 6: Train final model on all data
    # =========================================================================
    logger.info("")
    logger.info("STEP 6: Training final TFT on all data")
    logger.info("-" * 50)

    from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
    from pytorch_forecasting.metrics import MAE
    import lightning.pytorch as pl
    from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint

    step_start = time.time()

    final_ds_df = seq_df.drop(columns=["_original_dt_index"], errors="ignore")
    final_dataset = _build_timeseries_dataset(final_ds_df, feature_names, training=True)
    if final_dataset is None:
        msg = "Failed to build final training dataset"
        logger.error(msg)
        return {"status": "error", "message": msg}

    final_loader = _make_strided_loader(final_dataset, BATCH_SIZE, shuffle=True)

    final_model = TemporalFusionTransformer.from_dataset(
        final_dataset,
        learning_rate=LEARNING_RATE,
        hidden_size=HIDDEN_SIZE,
        attention_head_size=ATTENTION_HEAD_SIZE,
        dropout=DROPOUT,
        hidden_continuous_size=32,
        loss=MAE(),
        log_interval=-1,
        reduce_on_plateau_patience=3,
    )

    checkpoint_callback = ModelCheckpoint(
        dirpath=model_dir,
        filename="best",
        monitor="train_loss",
        mode="min",
        save_top_k=1,
    )

    epoch_logger = _make_epoch_logger(pl, "Final ")

    final_trainer = pl.Trainer(
        max_epochs=MAX_EPOCHS,
        gradient_clip_val=GRADIENT_CLIP,
        callbacks=[checkpoint_callback, epoch_logger],
        enable_progress_bar=False,
        enable_model_summary=False,
        logger=False,
        accelerator="auto",
        devices=1,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        final_trainer.fit(final_model, final_loader)

    logger.info(f"Final TFT training complete in {time.time() - step_start:.0f}s")

    # =========================================================================
    # STEP 7: Save model directory
    # =========================================================================
    logger.info("")
    logger.info("STEP 7: Saving TFT model to disk")
    logger.info("-" * 50)

    hyperparams = {
        "encoder_length": ENCODER_LENGTH,
        "prediction_length": PREDICTION_LENGTH,
        "hidden_size": HIDDEN_SIZE,
        "attention_head_size": ATTENTION_HEAD_SIZE,
        "dropout": DROPOUT,
        "batch_size": BATCH_SIZE,
        "max_epochs": MAX_EPOCHS,
        "learning_rate": LEARNING_RATE,
        "prediction_horizon": prediction_horizon,
        "horizon_bars": horizon_bars,
        "stride": STRIDE,
        "target_mean": target_mean,
        "target_std": target_std,
    }

    # Load the best checkpoint (by train_loss) instead of using the last epoch,
    # which may be overfit. ModelCheckpoint saved it to best.ckpt.
    best_ckpt_path = Path(model_dir) / "best.ckpt"
    if best_ckpt_path.exists():
        logger.info(f"  Loading best checkpoint from {best_ckpt_path}")
        try:
            best_model = final_model.__class__.load_from_checkpoint(str(best_ckpt_path))
            final_model = best_model
            logger.info("  Best checkpoint loaded successfully")
        except Exception as ckpt_err:
            logger.warning(f"  Could not load best checkpoint ({ckpt_err}), using last epoch")
    else:
        logger.info("  No best.ckpt found, using last epoch model")

    predictor = TFTPredictor()
    predictor._model = final_model
    predictor._feature_names = feature_names
    predictor._encoder_length = ENCODER_LENGTH
    predictor._target_mean = target_mean
    predictor._target_std = target_std

    predictor.save(
        model_dir=model_dir,
        trainer=final_trainer,
        feature_names=feature_names,
        target_mean=target_mean,
        target_std=target_std,
        extra_metadata=hyperparams,
    )

    logger.info(f"TFT model saved to: {model_dir}")

    # =========================================================================
    # STEP 8: Save to database
    # =========================================================================
    logger.info("")
    logger.info("STEP 8: Saving model record to database")
    logger.info("-" * 50)

    fold_details = cv_metrics.pop("fold_details", [])
    cv_metrics["training_samples"] = training_samples

    _save_tft_model_to_db(
        model_id=model_id,
        profile_id=profile_id,
        model_dir=model_dir,
        preset=preset,
        symbol=symbol,
        data_start_date=data_start_date,
        data_end_date=data_end_date,
        metrics=cv_metrics,
        feature_names=feature_names,
        hyperparams=hyperparams,
        pipeline_start_iso=pipeline_start_iso,
        db_path=db_path,
    )

    # =========================================================================
    # STEP 9: Post-training feature validation
    # =========================================================================
    logger.info("")
    logger.info("STEP 9: Feature validation")
    logger.info("-" * 50)

    expected_features = _get_feature_names(preset)
    missing_features = [f for f in expected_features if f not in feature_names]
    options_features = [f for f in expected_features if f.startswith(("atm_", "iv_", "rv_iv", "put_call", "theta_delta", "gamma_theta", "vega_theta"))]
    options_present = [f for f in options_features if f in feature_names]
    options_missing = [f for f in options_features if f not in feature_names]

    logger.info(f"  Expected features: {len(expected_features)}")
    logger.info(f"  Model features:    {len(feature_names)}")
    logger.info(f"  Missing features:  {len(missing_features)}")
    if missing_features:
        logger.warning(f"  MISSING: {missing_features}")
    logger.info(f"  Options features:  {len(options_present)}/{len(options_features)} present")
    if options_missing:
        logger.warning(f"  OPTIONS MISSING: {options_missing}")

    # Check NaN coverage in sequence data
    nan_counts = seq_df[feature_names].isna().sum()
    total_rows = len(seq_df)
    high_nan_features = [(f, int(c), f"{c/total_rows*100:.0f}%") for f, c in nan_counts.items() if c > total_rows * 0.5]
    if high_nan_features:
        logger.warning(f"  Features >50% NaN in training data:")
        for fname, count, pct in high_nan_features:
            logger.warning(f"    {fname}: {count}/{total_rows} ({pct})")
    else:
        logger.info(f"  All features <50% NaN in training data")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    total_elapsed = time.time() - pipeline_start

    logger.info("")
    logger.info("=" * 70)
    logger.info("TFT TRAINING PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"  Model ID:         {model_id}")
    logger.info(f"  Model Dir:        {model_dir}")
    logger.info(f"  Data Range:       {data_start_date} to {data_end_date}")
    logger.info(f"  Training Samples: {training_samples} bars")
    logger.info(f"  Features:         {len(feature_names)}")
    logger.info(f"  MAE:              {cv_metrics['mae']:.4f}")
    logger.info(f"  DirAcc:           {cv_metrics['dir_acc']:.4f}")
    logger.info(f"  Total Time:       {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")
    logger.info("=" * 70)

    return {
        "status": "ready",
        "model_id": model_id,
        "model_dir": model_dir,
        "metrics": cv_metrics,
        "feature_names": feature_names,
        "data_range": f"{data_start_date} to {data_end_date}",
        "training_samples": training_samples,
        "total_time_seconds": total_elapsed,
        "target_mean": target_mean,
        "target_std": target_std,
    }

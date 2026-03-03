"""
Ensemble (stacking) ModelPredictor.
Matches PROJECT_ARCHITECTURE.md Section 7 — Phase 4: Ensemble.

Combines XGBoost and TFT predictions via a Ridge regression meta-learner.
Strategy code calls predictor.predict(features, sequence) — identical interface
to XGBoostPredictor and TFTPredictor. EnsemblePredictor routes to both sub-models
and combines their outputs.

Degraded mode: if sequence is None or too short, falls back to XGBoost prediction.
This ensures live trading never blocks on missing sequence data.

Save format: single .joblib file (not directory — meta-learner is tiny).
Training: train_meta_learner() fetches predictions from both sub-models and
          fits Ridge regression on [xgb_pred, tft_pred] -> actual_return.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from ml.predictor import ModelPredictor
from ml.xgboost_predictor import XGBoostPredictor
from ml.tft_predictor import TFTPredictor, ENCODER_LENGTH

logger = logging.getLogger("options-bot.ml.ensemble")


class EnsemblePredictor(ModelPredictor):
    """
    Stacking ensemble of XGBoost + TFT via Ridge regression meta-learner.

    Usage:
        # Training (done by backend/routes/models.py on 'ensemble' train trigger):
        predictor = EnsemblePredictor()
        result = predictor.train_meta_learner(
            profile_id, symbol, preset, xgb_model_path, tft_model_dir, db_path
        )

        # Inference (strategy code — identical to XGBoost):
        predictor = EnsemblePredictor(model_path="models/ensemble_xxx.joblib")
        prediction = predictor.predict(features_dict, sequence_df)
    """

    def __init__(self, model_path: str = None):
        self._meta_learner: Optional[Ridge] = None
        self._xgb: Optional[XGBoostPredictor] = None
        self._tft: Optional[TFTPredictor] = None
        self._feature_names: list[str] = []
        self._encoder_length: int = ENCODER_LENGTH
        self._xgb_weight: float = 0.5
        self._tft_weight: float = 0.5
        self._xgb_model_path: Optional[str] = None
        self._tft_model_dir: Optional[str] = None

        if model_path:
            self.load(model_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Load / Save
    # ─────────────────────────────────────────────────────────────────────────

    def load(self, model_path: str):
        """
        Load ensemble from a .joblib file.

        The .joblib stores paths to the XGBoost and TFT models, not the models
        themselves. Both sub-models are loaded at this point.

        Args:
            model_path: Path to the ensemble .joblib file
        """
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Ensemble model not found: {model_path}")

        logger.info(f"Loading ensemble from {model_path}")
        data = joblib.load(model_path)

        self._meta_learner = data["meta_learner"]
        self._feature_names = data["feature_names"]
        self._encoder_length = data.get("encoder_length", ENCODER_LENGTH)
        self._xgb_weight = data.get("xgb_weight", 0.5)
        self._tft_weight = data.get("tft_weight", 0.5)
        self._xgb_model_path = data["xgb_model_path"]
        self._tft_model_dir = data["tft_model_dir"]

        # Load sub-models
        self._xgb = XGBoostPredictor(self._xgb_model_path)
        self._tft = TFTPredictor(self._tft_model_dir)

        logger.info(
            f"Ensemble loaded: {len(self._feature_names)} features, "
            f"xgb_weight={self._xgb_weight:.3f}, tft_weight={self._tft_weight:.3f}"
        )

    def save(self, model_path: str):
        """
        Save ensemble meta-learner and sub-model paths to a .joblib file.

        Sub-models (XGBoost, TFT) are NOT embedded — only their paths are stored.
        This keeps the ensemble file small and avoids duplicating large model files.

        Args:
            model_path: Destination path for the .joblib file
        """
        if self._meta_learner is None:
            raise RuntimeError("No meta-learner to save. Run train_meta_learner() first.")

        model_path = Path(model_path)
        model_path.parent.mkdir(parents=True, exist_ok=True)

        # Extract weights from Ridge coefficients
        coef = self._meta_learner.coef_
        xgb_weight = float(coef[0]) if len(coef) > 0 else 0.5
        tft_weight = float(coef[1]) if len(coef) > 1 else 0.5

        data = {
            "meta_learner": self._meta_learner,
            "xgb_model_path": self._xgb_model_path,
            "tft_model_dir": self._tft_model_dir,
            "feature_names": self._feature_names,
            "encoder_length": self._encoder_length,
            "xgb_weight": xgb_weight,
            "tft_weight": tft_weight,
        }

        joblib.dump(data, model_path)
        self._xgb_weight = xgb_weight
        self._tft_weight = tft_weight

        logger.info(
            f"Ensemble saved to {model_path} — "
            f"xgb_weight={xgb_weight:.3f}, tft_weight={tft_weight:.3f}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Inference
    # ─────────────────────────────────────────────────────────────────────────

    def predict(self, features: dict, sequence: pd.DataFrame = None) -> float:
        """
        Predict forward return % using ensemble of XGBoost + TFT.

        If sequence is None or too short for TFT, falls back to XGBoost only.
        Strategy code calls this identically to XGBoostPredictor.predict().

        Args:
            features: Dict of feature_name -> value (snapshot for XGBoost)
            sequence: DataFrame of last ENCODER_LENGTH 5-min bars (for TFT)
                      Pass None to use XGBoost-only degraded mode.

        Returns:
            Predicted forward return % (e.g., 2.5 means +2.5%)
        """
        if self._meta_learner is None or self._xgb is None:
            raise RuntimeError("Ensemble not loaded. Call load() first.")

        # Always get XGBoost prediction (fast, no sequence needed)
        try:
            xgb_pred = self._xgb.predict(features)
        except Exception as e:
            logger.error(f"XGBoost sub-prediction failed: {e}")
            xgb_pred = 0.0

        if np.isnan(xgb_pred) or np.isinf(xgb_pred):
            logger.error(f"XGBoost returned NaN/Inf, using 0.0")
            xgb_pred = 0.0

        # Attempt TFT prediction — degrade gracefully if sequence unavailable
        tft_pred = None
        if sequence is not None and len(sequence) >= self._encoder_length:
            try:
                tft_pred = self._tft.predict(features, sequence)
            except Exception as e:
                logger.warning(f"TFT sub-prediction failed, using XGBoost only: {e}")
                tft_pred = None

        if tft_pred is None or np.isnan(tft_pred) or np.isinf(tft_pred):
            # Degraded mode: XGBoost only
            if tft_pred is not None:
                logger.error(f"TFT returned NaN/Inf, falling back to XGBoost only")
            else:
                logger.debug("Ensemble degraded mode: TFT unavailable, using XGBoost only")
            return float(xgb_pred)

        # Meta-learner combination
        X_meta = np.array([[xgb_pred, tft_pred]])
        ensemble_pred = float(self._meta_learner.predict(X_meta)[0])

        if np.isnan(ensemble_pred) or np.isinf(ensemble_pred):
            logger.error(f"Meta-learner produced NaN/Inf, falling back to XGBoost")
            return float(xgb_pred)

        logger.debug(
            f"Ensemble: xgb={xgb_pred:.3f}%, tft={tft_pred:.3f}%, "
            f"ensemble={ensemble_pred:.3f}%"
        )
        return ensemble_pred

    def predict_batch(self, features_df: pd.DataFrame) -> pd.Series:
        """
        Predict for multiple snapshot observations (XGBoost path only).

        TFT batch prediction requires full sequences — for that use
        train_meta_learner() which handles the full sequence dataset internally.
        This method is XGBoost-only for interface compliance.
        """
        if self._xgb is None:
            raise RuntimeError("Ensemble not loaded. Call load() first.")

        logger.warning(
            "EnsemblePredictor.predict_batch() uses XGBoost-only predictions. "
            "For full ensemble batch prediction, use train_meta_learner()."
        )
        return self._xgb.predict_batch(features_df)

    # ─────────────────────────────────────────────────────────────────────────
    # Feature names / importance
    # ─────────────────────────────────────────────────────────────────────────

    def get_feature_names(self) -> list[str]:
        """Return the feature names used by the sub-models."""
        return list(self._feature_names)

    def get_feature_importance(self) -> dict:
        """
        Return a combined feature importance from XGBoost and TFT.

        Weighted average: importance = xgb_weight * xgb_imp + tft_weight * tft_imp
        Weights are the Ridge meta-learner coefficients (normalized to sum to 1).

        Falls back to XGBoost importance only if TFT importance unavailable.
        Returns {} if no models loaded.
        """
        if self._xgb is None:
            return {}

        xgb_imp = self._xgb.get_feature_importance()
        if not xgb_imp:
            return {}

        if self._tft is None:
            return xgb_imp

        tft_imp = self._tft.get_feature_importance()
        if not tft_imp:
            return xgb_imp

        # Normalize weights to sum to 1
        total_weight = abs(self._xgb_weight) + abs(self._tft_weight)
        if total_weight < 1e-8:
            w_xgb, w_tft = 0.5, 0.5
        else:
            w_xgb = abs(self._xgb_weight) / total_weight
            w_tft = abs(self._tft_weight) / total_weight

        # Blend importance scores
        combined = {}
        all_features = set(xgb_imp) | set(tft_imp)
        for feat in all_features:
            combined[feat] = (
                w_xgb * xgb_imp.get(feat, 0.0)
                + w_tft * tft_imp.get(feat, 0.0)
            )

        return combined

    # ─────────────────────────────────────────────────────────────────────────
    # Meta-learner training
    # ─────────────────────────────────────────────────────────────────────────

    def train_meta_learner(
        self,
        profile_id: str,
        symbol: str,
        preset: str,
        xgb_model_path: str,
        tft_model_dir: str,
        prediction_horizon: str = "5d",
        years_of_data: int = 6,
        db_path: str = None,
    ) -> dict:
        """
        Train the Ridge meta-learner using predictions from both sub-models.

        Process:
            1. Load XGBoost and TFT models from their paths
            2. Fetch the same historical bars used to train both sub-models
            3. Compute features (same pipeline as trainer.py)
            4. Get XGBoost predictions on the daily-subsampled dataset
            5. Get TFT predictions on the same bars via predict_dataset()
            6. Align predictions to the same rows (inner join on index)
            7. Fit Ridge on [xgb_pred, tft_pred] -> actual_return
            8. Save ensemble .joblib
            9. Save ensemble model record to database

        Args:
            profile_id: UUID of the profile
            symbol: Ticker symbol (e.g., "TSLA")
            preset: Trading preset ("swing" or "general")
            xgb_model_path: Path to existing XGBoost .joblib file
            tft_model_dir: Path to existing TFT model directory
            prediction_horizon: Forward return horizon (e.g., "5d")
            years_of_data: How many years of Alpaca data to fetch
            db_path: Override DB path (for testing)

        Returns:
            Dict with keys: status, model_id, model_path, metrics,
                            xgb_weight, tft_weight
            On failure: {status: "error", message: str}
        """
        import asyncio
        import time
        import uuid as _uuid
        import aiosqlite
        from datetime import datetime, timedelta
        from config import DB_PATH as _DB_PATH, MODELS_DIR

        db_path = db_path or str(_DB_PATH)
        pipeline_start = time.time()
        model_id = str(_uuid.uuid4())
        model_filename = f"{profile_id}_ensemble_{model_id[:8]}.joblib"
        model_path = str(MODELS_DIR / model_filename)

        logger.info("=" * 70)
        logger.info("ENSEMBLE META-LEARNER TRAINING START")
        logger.info(f"  Profile:     {profile_id}")
        logger.info(f"  Symbol:      {symbol}")
        logger.info(f"  Preset:      {preset}")
        logger.info(f"  Horizon:     {prediction_horizon}")
        logger.info(f"  XGB path:    {xgb_model_path}")
        logger.info(f"  TFT dir:     {tft_model_dir}")
        logger.info("=" * 70)

        # ─── Step 1: Load sub-models ──────────────────────────────────────────
        logger.info("STEP 1: Loading sub-models")

        try:
            self._xgb = XGBoostPredictor(xgb_model_path)
            self._xgb_model_path = xgb_model_path
            logger.info(f"  XGBoost loaded: {len(self._xgb.get_feature_names())} features")
        except Exception as e:
            return {"status": "error", "message": f"Failed to load XGBoost: {e}"}

        try:
            self._tft = TFTPredictor(tft_model_dir)
            self._tft_model_dir = tft_model_dir
            self._encoder_length = self._tft._encoder_length
            logger.info(f"  TFT loaded: encoder_length={self._encoder_length}")
        except Exception as e:
            return {"status": "error", "message": f"Failed to load TFT: {e}"}

        self._feature_names = self._xgb.get_feature_names()

        # ─── Step 2: Fetch historical bars ───────────────────────────────────
        logger.info("")
        logger.info("STEP 2: Fetching historical bars from Alpaca")

        try:
            from data.alpaca_provider import AlpacaStockProvider
            provider = AlpacaStockProvider()
            end_date = datetime.now() - timedelta(hours=1)
            start_date = end_date - timedelta(days=years_of_data * 365 + 30)
            bars_df = provider.get_historical_bars(symbol, start_date, end_date, timeframe="5min")
        except Exception as e:
            return {"status": "error", "message": f"Alpaca fetch failed: {e}"}

        if bars_df is None or bars_df.empty:
            return {"status": "error", "message": f"No bars returned for {symbol}"}

        # Tag bars_df with symbol so options fetcher can use it
        bars_df.attrs["symbol"] = symbol

        data_start_date = str(bars_df.index.min().date())
        data_end_date = str(bars_df.index.max().date())
        logger.info(f"  Fetched {len(bars_df)} bars: {data_start_date} to {data_end_date}")

        # ─── Step 3: Compute features ─────────────────────────────────────────
        logger.info("")
        logger.info("STEP 3: Computing features")

        try:
            from ml.feature_engineering.base_features import compute_base_features
            from ml.feature_engineering.swing_features import compute_swing_features
            from ml.feature_engineering.general_features import compute_general_features
            from config import PRESET_DEFAULTS

            # Fetch options data from Theta Terminal (if available)
            options_daily_df = None
            try:
                from data.options_data_fetcher import fetch_options_for_training
                preset_config = PRESET_DEFAULTS.get(preset, {})
                options_daily_df = fetch_options_for_training(
                    symbol=symbol,
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

            featured_df = compute_base_features(bars_df.copy(), options_daily_df=options_daily_df)
            if preset == "swing":
                featured_df = compute_swing_features(featured_df)
            elif preset == "general":
                featured_df = compute_general_features(featured_df)
            logger.info(f"  Features computed: {len(featured_df)} rows")
        except Exception as e:
            return {"status": "error", "message": f"Feature computation failed: {e}"}

        # ─── Step 4: Calculate targets and prepare training data ──────────────
        logger.info("")
        logger.info("STEP 4: Calculating targets and preparing training data")

        try:
            from ml.trainer import _prediction_horizon_to_bars, _calculate_target
            horizon_bars = _prediction_horizon_to_bars(prediction_horizon)

            # Calculate actual forward returns (the ground truth)
            target = _calculate_target(featured_df, horizon_bars)
            featured_df["_target"] = target

            train_df = featured_df.dropna(subset=["_target"])

            logger.info(f"  Training samples: {len(train_df)}")
        except Exception as e:
            return {"status": "error", "message": f"Target calculation failed: {e}"}

        if len(train_df) < 50:
            return {
                "status": "error",
                "message": f"Too few samples for meta-learner: {len(train_df)}"
            }

        # ─── Step 5: XGBoost predictions on daily samples ────────────────────
        logger.info("")
        logger.info("STEP 5: Getting XGBoost predictions")

        try:
            feature_cols = [c for c in self._feature_names if c in train_df.columns]
            xgb_preds = self._xgb.predict_batch(train_df[feature_cols])
            logger.info(f"  XGBoost predictions: {len(xgb_preds)} values")
        except Exception as e:
            return {"status": "error", "message": f"XGBoost batch prediction failed: {e}"}

        # ─── Step 6: TFT predictions on same bars (sequence-based) ───────────
        logger.info("")
        logger.info("STEP 6: Getting TFT predictions")

        try:
            from ml.tft_trainer import (
                predict_dataset as tft_predict_dataset,
                _build_sequence_df, TARGET_COL
            )

            # Build sequence DataFrame from the full featured bars
            seq_df = _build_sequence_df(featured_df, self._feature_names, horizon_bars)
            # Scale target using TFT's stored mean/std
            target_mean = self._tft._target_mean
            target_std = self._tft._target_std
            seq_df[TARGET_COL] = (seq_df["_target_raw"] - target_mean) / target_std

            tft_preds_series = tft_predict_dataset(
                model=self._tft._model,
                seq_df=seq_df,
                feature_names=self._feature_names,
                target_mean=target_mean,
                target_std=target_std,
            )
            logger.info(f"  TFT predictions: {len(tft_preds_series)} values")
        except Exception as e:
            logger.error(f"TFT batch prediction failed: {e}", exc_info=True)
            return {"status": "error", "message": f"TFT batch prediction failed: {e}"}

        # ─── Step 7: Align predictions to common index ────────────────────────
        logger.info("")
        logger.info("STEP 7: Aligning predictions and fitting Ridge meta-learner")

        try:
            # Both XGBoost and TFT now predict on all 5-min bars.
            # Join on common index to get aligned predictions.
            xgb_df = pd.DataFrame({
                "_xgb_pred": xgb_preds.values,
                "_target": train_df["_target"].values,
            }, index=train_df.index)

            tft_df = pd.DataFrame({
                "_tft_pred": tft_preds_series.values,
            }, index=tft_preds_series.index)

            # Normalize both indices to tz-naive to prevent
            # "Cannot join tz-naive with tz-aware DatetimeIndex" errors
            if hasattr(xgb_df.index, 'tz') and xgb_df.index.tz is not None:
                xgb_df.index = xgb_df.index.tz_localize(None)
            if hasattr(tft_df.index, 'tz') and tft_df.index.tz is not None:
                tft_df.index = tft_df.index.tz_localize(None)

            # Inner join on index — keeps only bars where both models have predictions
            merged = xgb_df.join(tft_df, how="inner")
            merged = merged.dropna(subset=["_xgb_pred", "_tft_pred", "_target"])

            n_aligned = len(merged)
            logger.info(
                f"  XGB predictions: {len(xgb_df)}, "
                f"TFT predictions: {len(tft_df)}, "
                f"aligned: {n_aligned}"
            )

            if n_aligned < 30:
                return {
                    "status": "error",
                    "message": (
                        f"Only {n_aligned} aligned rows between XGBoost and TFT "
                        f"predictions (need >= 30). Cannot train meta-learner. "
                        f"Ensure both XGBoost and TFT models are trained on the "
                        f"same symbol/preset with overlapping date ranges."
                    ),
                }
            else:
                xgb_vals = merged["_xgb_pred"].values
                tft_vals = merged["_tft_pred"].values
                y_vals = merged["_target"].values

                X_meta = np.column_stack([xgb_vals, tft_vals])
                self._meta_learner = Ridge(alpha=0.1, fit_intercept=True)
                self._meta_learner.fit(X_meta, y_vals)

                coef = self._meta_learner.coef_
                logger.info(
                    f"  Ridge fitted: xgb_coef={coef[0]:.4f}, tft_coef={coef[1]:.4f}, "
                    f"intercept={self._meta_learner.intercept_:.4f}"
                )
                logger.info(f"  Training rows for meta-learner: {n_aligned}")

        except Exception as e:
            return {"status": "error", "message": f"Meta-learner fitting failed: {e}"}

        # ─── Step 8: Evaluate ensemble vs XGBoost-only ───────────────────────
        logger.info("")
        logger.info("STEP 8: Evaluating ensemble vs XGBoost-only")

        try:
            from sklearn.metrics import mean_absolute_error

            if n_aligned >= 30:
                xgb_vals = merged["_xgb_pred"].values
                tft_vals = merged["_tft_pred"].values
                y_vals = merged["_target"].values
                X_meta = np.column_stack([xgb_vals, tft_vals])

                xgb_mae = float(mean_absolute_error(y_vals, xgb_vals))
                tft_mae = float(mean_absolute_error(y_vals, tft_vals))
                ens_preds = self._meta_learner.predict(X_meta)
                ens_mae = float(mean_absolute_error(y_vals, ens_preds))

                xgb_dir = float(((y_vals > 0) == (xgb_vals > 0)).mean())
                tft_dir = float(((y_vals > 0) == (tft_vals > 0)).mean())
                ens_dir = float(((y_vals > 0) == (ens_preds > 0)).mean())

                metrics = {
                    "xgb_mae": xgb_mae,
                    "tft_mae": tft_mae,
                    "ensemble_mae": ens_mae,
                    "xgb_dir_acc": xgb_dir,
                    "tft_dir_acc": tft_dir,
                    "ensemble_dir_acc": ens_dir,
                    "meta_learner_samples": n_aligned,
                }

                logger.info(f"  XGBoost MAE:  {xgb_mae:.4f}, DirAcc: {xgb_dir:.4f}")
                logger.info(f"  TFT MAE:      {tft_mae:.4f}, DirAcc: {tft_dir:.4f}")
                logger.info(f"  Ensemble MAE: {ens_mae:.4f}, DirAcc: {ens_dir:.4f}")

                if ens_mae < xgb_mae and ens_dir > xgb_dir:
                    logger.info("  Ensemble improves on BOTH MAE and directional accuracy vs XGBoost")
                elif ens_mae < xgb_mae or ens_dir > xgb_dir:
                    logger.info("  Ensemble improves on ONE metric vs XGBoost")
                else:
                    logger.warning(
                        "  Ensemble does NOT improve over XGBoost on either metric. "
                        "Review TFT training quality."
                    )
            else:
                metrics = {
                    "xgb_mae": None, "tft_mae": None, "ensemble_mae": None,
                    "xgb_dir_acc": None, "tft_dir_acc": None, "ensemble_dir_acc": None,
                    "meta_learner_samples": n_aligned,
                    "note": "Insufficient aligned rows for evaluation",
                }
        except Exception as e:
            logger.warning(f"Evaluation failed (non-fatal): {e}")
            metrics = {"error": str(e)}

        # ─── Step 9: Save ensemble model ──────────────────────────────────────
        logger.info("")
        logger.info("STEP 9: Saving ensemble model")

        try:
            self.save(model_path)
        except Exception as e:
            return {"status": "error", "message": f"Save failed: {e}"}

        # ─── Step 10: Save to database ────────────────────────────────────────
        logger.info("")
        logger.info("STEP 10: Saving ensemble record to database")

        now_iso = datetime.utcnow().isoformat()
        pipeline_start_iso = datetime.utcfromtimestamp(pipeline_start).isoformat()
        hyperparams = {
            "xgb_model_path": xgb_model_path,
            "tft_model_dir": tft_model_dir,
            "meta_learner": "Ridge(alpha=0.1)",
            "prediction_horizon": prediction_horizon,
            "xgb_weight": self._xgb_weight,
            "tft_weight": self._tft_weight,
        }

        async def _save_to_db():
            import aiosqlite as _aio
            async with _aio.connect(db_path) as db:
                db.row_factory = _aio.Row
                await db.execute(
                    """INSERT INTO models
                       (id, profile_id, model_type, file_path, status,
                        training_started_at, training_completed_at,
                        data_start_date, data_end_date,
                        metrics, feature_names, hyperparameters, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        model_id, profile_id, "ensemble", model_path, "ready",
                        pipeline_start_iso, now_iso,
                        data_start_date, data_end_date,
                        json.dumps(metrics),
                        json.dumps(self._feature_names),
                        json.dumps(hyperparams),
                        now_iso,
                    ),
                )
                await db.execute(
                    "UPDATE profiles SET model_id = ?, status = 'ready', updated_at = ? WHERE id = ?",
                    (model_id, now_iso, profile_id),
                )
                await db.commit()

        import asyncio as _asyncio
        import concurrent.futures as _cf
        try:
            _asyncio.run(_save_to_db())
        except RuntimeError:
            try:
                with _cf.ThreadPoolExecutor() as pool:
                    pool.submit(_asyncio.run, _save_to_db()).result(timeout=60)
            except Exception as e:
                logger.error(f"_save_to_db fallback failed: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"_save_to_db failed: {e}", exc_info=True)

        total_elapsed = time.time() - pipeline_start
        logger.info("")
        logger.info("=" * 70)
        logger.info("ENSEMBLE TRAINING COMPLETE")
        logger.info(f"  Model ID:     {model_id}")
        logger.info(f"  Model Path:   {model_path}")
        logger.info(f"  XGB weight:   {self._xgb_weight:.4f}")
        logger.info(f"  TFT weight:   {self._tft_weight:.4f}")
        logger.info(f"  Total Time:   {total_elapsed:.0f}s")
        logger.info("=" * 70)

        return {
            "status": "ready",
            "model_id": model_id,
            "model_path": model_path,
            "metrics": metrics,
            "xgb_weight": self._xgb_weight,
            "tft_weight": self._tft_weight,
            "feature_names": self._feature_names,
            "total_time_seconds": total_elapsed,
        }

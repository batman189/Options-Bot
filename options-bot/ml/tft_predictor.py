"""
TFT ModelPredictor implementation.
Matches PROJECT_ARCHITECTURE.md Section 7 — Phase 4: XGBoost + TFT Ensemble.

Uses pytorch-forecasting TemporalFusionTransformer for sequence-based prediction.
Receives the last ENCODER_LENGTH 5-min bars as input, predicts forward return %.

Strategy code calls:
    predictor.predict(features=snapshot_dict, sequence=last_60_bars_df)
XGBoost uses `features`. TFT uses `sequence`.
EnsemblePredictor calls both and combines outputs.

Save format: directory containing model.pt + metadata.json + scaler.joblib
"""

import json
import logging
import warnings
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import torch

from ml.predictor import ModelPredictor

logger = logging.getLogger("options-bot.ml.tft")

# Architecture Section 7: encoder length = 60 bars of 5-min data
ENCODER_LENGTH = 60
PREDICTION_LENGTH = 1      # Single step: predict return at end of sequence
GROUP_ID = "asset"         # Constant group identifier for single-series inference


class TFTPredictor(ModelPredictor):
    """
    TemporalFusionTransformer predictor implementing ModelPredictor interface.

    After loading, call predict(features, sequence) where sequence is a DataFrame
    of the last ENCODER_LENGTH 5-minute bars with computed features.

    The model predicts the forward return % for the final bar in the sequence.
    """

    def __init__(self, model_dir: str = None):
        self._model = None
        self._feature_names: list[str] = []
        self._encoder_length: int = ENCODER_LENGTH
        self._target_mean: float = 0.0
        self._target_std: float = 1.0
        self._model_dir: Optional[Path] = None
        self._metadata: dict = {}

        if model_dir:
            self.load(model_dir)

    # -------------------------------------------------------------------------
    # Load / Save
    # -------------------------------------------------------------------------

    def load(self, model_dir: str):
        """
        Load a trained TFT model from a directory.

        Args:
            model_dir: Path to directory containing model.pt, metadata.json, scaler.joblib
        """
        from pytorch_forecasting import TemporalFusionTransformer

        model_dir = Path(model_dir)
        if not model_dir.is_dir():
            raise FileNotFoundError(f"TFT model directory not found: {model_dir}")

        logger.info(f"Loading TFT model from {model_dir}")

        # Load metadata first
        metadata_path = model_dir / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"metadata.json not found in {model_dir}")
        with open(metadata_path) as f:
            self._metadata = json.load(f)

        self._feature_names = self._metadata["feature_names"]
        self._encoder_length = self._metadata.get("encoder_length", ENCODER_LENGTH)
        self._target_mean = self._metadata.get("target_mean", 0.0)
        self._target_std = self._metadata.get("target_std", 1.0)

        # Load PyTorch model
        model_path = model_dir / "model.pt"
        if not model_path.exists():
            raise FileNotFoundError(f"model.pt not found in {model_dir}")

        # Reconstruct TFT from checkpoint
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._model = TemporalFusionTransformer.load_from_checkpoint(
                str(model_path),
                map_location="cpu",
            )
        self._model.eval()
        self._model_dir = model_dir

        logger.info(
            f"TFT model loaded: {len(self._feature_names)} features, "
            f"encoder_length={self._encoder_length}"
        )

    def save(
        self,
        model_dir: str,
        trainer,               # pytorch_lightning.Trainer
        feature_names: list[str],
        target_mean: float = 0.0,
        target_std: float = 1.0,
        extra_metadata: dict = None,
    ):
        """
        Save a trained TFT model to a directory.

        Called by tft_trainer.py after training completes.

        Args:
            model_dir: Directory to save into (created if missing)
            trainer: pytorch_lightning.Trainer that trained the model
                     (used to save checkpoint)
            feature_names: Ordered list of feature column names
            target_mean: Mean of the training target (for inverse scaling)
            target_std: Std of the training target (for inverse scaling)
            extra_metadata: Optional dict merged into metadata.json
        """
        model_dir = Path(model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Saving TFT model to {model_dir}")

        # Save PyTorch Lightning checkpoint
        # Prefer best.ckpt from ModelCheckpoint callback over trainer's last-epoch state
        # (H2 fix: trainer.save_checkpoint() saves last epoch, not best)
        model_path = model_dir / "model.pt"
        best_ckpt = model_dir / "best.ckpt"
        if best_ckpt.exists():
            import shutil
            shutil.copy2(str(best_ckpt), str(model_path))
            logger.info(f"  Copied best checkpoint to {model_path}")
        else:
            trainer.save_checkpoint(str(model_path))
            logger.info(f"  No best.ckpt found, saved last epoch checkpoint")

        # Save metadata
        metadata = {
            "feature_names": feature_names,
            "encoder_length": self._encoder_length,
            "prediction_length": PREDICTION_LENGTH,
            "target_mean": float(target_mean),
            "target_std": float(target_std),
            "group_id": GROUP_ID,
            "model_type": "tft",
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        with open(model_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        self._feature_names = feature_names
        self._target_mean = target_mean
        self._target_std = target_std
        self._model_dir = model_dir

        logger.info(f"TFT model saved: {model_dir}")

    # -------------------------------------------------------------------------
    # Inference
    # -------------------------------------------------------------------------

    def predict(self, features: dict, sequence: pd.DataFrame = None) -> float:
        """
        Predict forward return % for the most recent bar in the sequence.

        Args:
            features: Snapshot feature dict (not used by TFT, accepted for
                      interface compatibility with EnsemblePredictor)
            sequence: DataFrame of the last ENCODER_LENGTH 5-minute bars.
                      Must have feature columns matching what was used in training.
                      Missing columns are filled with NaN.

        Returns:
            Predicted forward return as a percentage (e.g., 2.5 means +2.5%)

        Raises:
            RuntimeError: If model not loaded or sequence is None/too short
        """
        if self._model is None:
            raise RuntimeError("TFT model not loaded. Call load() first.")

        if sequence is None:
            raise RuntimeError(
                "TFT requires sequence data. Pass sequence=last_N_bars_df to predict()."
            )

        if len(sequence) < self._encoder_length:
            raise RuntimeError(
                f"TFT requires at least {self._encoder_length} bars. "
                f"Got {len(sequence)}."
            )

        # Use the last encoder_length rows
        seq = sequence.iloc[-self._encoder_length:].copy()

        # Align to training feature order (fill missing with NaN)
        seq = seq.reindex(columns=self._feature_names)

        # Fill NaN with 0.0 for inference (model trained with 0-imputed NaNs)
        seq = seq.fillna(0.0)

        # Build inference DataFrame for TimeSeriesDataSet
        inference_df = self._build_inference_df(seq)

        # Create dataset and predict
        prediction_scaled = self._run_tft_inference(inference_df)

        # Invert target scaling: raw_return = prediction_scaled * std + mean
        prediction_raw = float(prediction_scaled * self._target_std + self._target_mean)

        if np.isnan(prediction_raw) or np.isinf(prediction_raw):
            logger.error(f"TFT produced NaN/Inf prediction (scaled={prediction_scaled}), returning 0.0")
            return 0.0

        logger.debug(
            f"TFT predict: scaled={prediction_scaled:.4f}, "
            f"raw={prediction_raw:.4f}%"
        )
        return prediction_raw

    def predict_batch(self, features_df: pd.DataFrame) -> pd.Series:
        """
        Predict for multiple observations (each row is the LAST bar of its sequence).

        NOTE: For TFT, batch prediction is not naturally supported without full
        sequences per observation. This method is implemented for interface
        compliance but is primarily used by EnsemblePredictor in training mode,
        where tft_trainer.py handles batch prediction directly via TimeSeriesDataSet.

        For each row, we predict using only that single row (encoder_length=1)
        which degrades TFT to a simple feedforward. This is a known limitation
        of the batch interface for temporal models.

        For production use during training evaluation, use TFTTrainer.predict_dataset()
        which has access to full sequences.
        """
        if self._model is None:
            raise RuntimeError("TFT model not loaded. Call load() first.")

        logger.warning(
            "TFTPredictor.predict_batch() called — this uses single-row inference "
            "which degrades TFT accuracy. Use TFTTrainer.predict_dataset() for "
            "proper batch prediction during training."
        )

        results = []
        for idx, row in features_df.iterrows():
            try:
                # Build single-row sequence for minimal inference
                single_row = pd.DataFrame([row])
                # Pad to encoder_length with zeros if needed
                pad_rows = self._encoder_length - 1
                if pad_rows > 0:
                    pad_df = pd.DataFrame(
                        np.zeros((pad_rows, len(single_row.columns))),
                        columns=single_row.columns,
                    )
                    seq = pd.concat([pad_df, single_row], ignore_index=True)
                else:
                    seq = single_row
                result = self.predict(features={}, sequence=seq)
            except Exception as e:
                logger.warning(f"TFT predict_batch error at index {idx}: {e}")
                result = 0.0
            results.append(result)

        return pd.Series(results, index=features_df.index)

    # -------------------------------------------------------------------------
    # Feature importance / interpretability
    # -------------------------------------------------------------------------

    def get_feature_names(self) -> list[str]:
        """Return the ordered list of feature column names."""
        return list(self._feature_names)

    def get_feature_importance(self) -> dict:
        """
        Return TFT variable importance scores from the variable selection network.

        TFT's built-in variable selection produces attention weights per feature.
        These weights sum to 1.0 and reflect how much each feature is used.

        Returns:
            Dict of feature_name -> importance_score (float, 0-1, sums to ~1.0)
            Empty dict if model not loaded or if importance extraction fails.
        """
        if self._model is None:
            return {}

        try:
            # pytorch-forecasting exposes interpretation on a forward pass
            # We need a minimal batch to get variable importances
            # The model stores variable selection weights as attributes
            # after a forward pass — we trigger one with a zero input

            dummy_df = self._build_inference_df(
                pd.DataFrame(
                    np.zeros((self._encoder_length, len(self._feature_names))),
                    columns=self._feature_names,
                )
            )

            with torch.no_grad():
                importance_raw = self._extract_variable_importance(dummy_df)

            return importance_raw

        except Exception as e:
            logger.warning(f"TFT feature importance extraction failed: {e}")
            # Fall back to equal weights
            n = len(self._feature_names)
            return {name: 1.0 / n for name in self._feature_names}

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _build_inference_df(self, seq: pd.DataFrame) -> pd.DataFrame:
        """
        Build a DataFrame suitable for pytorch-forecasting TimeSeriesDataSet
        from a sequence of feature rows.

        Adds required columns: time_idx (int), group_id (str).
        A dummy future row is added so TimeSeriesDataSet has room for
        prediction_length=1.

        Args:
            seq: DataFrame of exactly encoder_length rows with feature columns

        Returns:
            DataFrame ready for TimeSeriesDataSet construction
        """
        n = len(seq)
        df = seq.reset_index(drop=True).copy()

        # time_idx: 0, 1, ..., encoder_length-1, encoder_length (future stub)
        df["time_idx"] = range(n)
        df["group_id"] = GROUP_ID

        # Add a dummy future row for prediction_length=1
        # TimeSeriesDataSet requires encoder + decoder rows in the same DataFrame
        future_row = df.iloc[-1:].copy()
        future_row["time_idx"] = n
        # Target for future row is 0.0 (it will be predicted, not used as label)
        if "_target_scaled" in df.columns:
            future_row["_target_scaled"] = 0.0

        df = pd.concat([df, future_row], ignore_index=True)
        return df

    def _run_tft_inference(self, inference_df: pd.DataFrame) -> float:
        """
        Construct a TimeSeriesDataSet from inference_df and run the TFT model.

        Returns the scaled prediction for the final step (the future row).
        """
        from pytorch_forecasting import TimeSeriesDataSet

        # All feature columns (exclude metadata columns)
        meta_cols = {"time_idx", "group_id", "_target_scaled"}
        feature_cols = [c for c in inference_df.columns if c not in meta_cols]

        # Use a dummy target column for inference (all zeros)
        if "_target_scaled" not in inference_df.columns:
            inference_df = inference_df.copy()
            inference_df["_target_scaled"] = 0.0

        try:
            dataset = TimeSeriesDataSet(
                inference_df,
                time_idx="time_idx",
                target="_target_scaled",
                group_ids=["group_id"],
                min_encoder_length=self._encoder_length,
                max_encoder_length=self._encoder_length,
                min_prediction_length=PREDICTION_LENGTH,
                max_prediction_length=PREDICTION_LENGTH,
                time_varying_unknown_reals=feature_cols,
                add_relative_time_idx=True,
                add_target_scales=False,
                add_encoder_length=False,
                allow_missing_timesteps=True,
            )
        except Exception as e:
            logger.error(f"TFT TimeSeriesDataSet construction failed: {e}")
            raise

        dataloader = dataset.to_dataloader(train=False, batch_size=1, num_workers=0)

        with torch.no_grad():
            for batch_x, batch_y in dataloader:
                output = self._model(batch_x)
                # TFT output: quantile predictions at dim=-1
                # Default: 7 quantiles [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98]
                # We use the median (index 3 of the 7 quantiles)
                prediction = output.prediction
                if prediction.ndim == 3:
                    # Shape: (batch, prediction_length, quantiles)
                    # Use median (index 3 of 7 quantiles) when available,
                    # but clamp to last index for single-output losses (MAE)
                    q_idx = min(3, prediction.shape[2] - 1)
                    median_pred = prediction[0, 0, q_idx]
                elif prediction.ndim == 2:
                    # Shape: (batch, prediction_length)
                    median_pred = prediction[0, 0]
                else:
                    median_pred = prediction[0]
                result = float(median_pred.cpu().numpy())
                if np.isnan(result) or np.isinf(result):
                    logger.error(f"TFT inference produced NaN/Inf, returning 0.0")
                    return 0.0
                return result

        # Should not reach here
        return 0.0

    def _extract_variable_importance(self, dummy_df: pd.DataFrame) -> dict:
        """
        Extract variable selection weights from the TFT model.

        pytorch-forecasting stores variable importance in the model's
        interpret_output() after a forward pass.
        """
        from pytorch_forecasting import TimeSeriesDataSet

        meta_cols = {"time_idx", "group_id", "_target_scaled"}
        feature_cols = [c for c in dummy_df.columns if c not in meta_cols]

        if "_target_scaled" not in dummy_df.columns:
            dummy_df = dummy_df.copy()
            dummy_df["_target_scaled"] = 0.0

        dataset = TimeSeriesDataSet(
            dummy_df,
            time_idx="time_idx",
            target="_target_scaled",
            group_ids=["group_id"],
            min_encoder_length=self._encoder_length,
            max_encoder_length=self._encoder_length,
            min_prediction_length=PREDICTION_LENGTH,
            max_prediction_length=PREDICTION_LENGTH,
            time_varying_unknown_reals=feature_cols,
            add_relative_time_idx=True,
            add_target_scales=False,
            add_encoder_length=False,
            allow_missing_timesteps=True,
        )

        dataloader = dataset.to_dataloader(train=False, batch_size=1, num_workers=0)

        with torch.no_grad():
            for batch_x, batch_y in dataloader:
                output = self._model(batch_x)
                interpretation = self._model.interpret_output(
                    output, reduction="sum"
                )
                # encoder_variables: shape (n_features,)
                encoder_importance = interpretation.get(
                    "encoder_variables", None
                )
                if encoder_importance is not None:
                    weights = encoder_importance.cpu().numpy().flatten()
                    # The encoder_variables tensor includes an extra entry for
                    # relative_time_idx (added by add_relative_time_idx=True).
                    # We need to match feature_names to the correct weight indices.
                    # Build the full variable list as TimeSeriesDataSet sees it.
                    full_var_names = list(self._feature_names) + ["relative_time_idx"]
                    if len(weights) == len(full_var_names):
                        # Remove relative_time_idx weight before normalizing
                        weights = weights[:len(self._feature_names)]
                    elif len(weights) > len(self._feature_names):
                        # Extra variables — take only the first N matching features
                        weights = weights[:len(self._feature_names)]
                    # Normalize to sum to 1.0
                    total = weights.sum()
                    if total > 0:
                        weights = weights / total
                    return dict(zip(self._feature_names, weights.tolist()))
                break

        # Fallback: equal weights
        n = len(self._feature_names)
        return {name: 1.0 / n for name in self._feature_names}

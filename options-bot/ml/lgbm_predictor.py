"""
LightGBM ModelPredictor implementation.
Phase C — ML Accuracy Improvements.

Same interface as XGBoostPredictor: predict(features: dict, sequence=None) -> float.
Save format: single .joblib with {"model": lgbm_model, "feature_names": list}.
"""

import logging
from typing import Optional
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from ml.predictor import ModelPredictor

logger = logging.getLogger("options-bot.ml.lgbm")


class LightGBMPredictor(ModelPredictor):
    """LightGBM regression model for predicting forward returns."""

    def __init__(self, model_path: str = None):
        self._model = None
        self._feature_names: list[str] = []
        if model_path:
            self.load(model_path)

    def load(self, model_path: str):
        """Load a trained LightGBM model from disk."""
        logger.info(f"Loading LightGBM model from {model_path}")
        data = joblib.load(model_path)
        self._model = data["model"]
        self._feature_names = data["feature_names"]
        logger.info(
            f"LightGBM loaded: {len(self._feature_names)} features, "
            f"type={type(self._model).__name__}"
        )

    def save(self, model_path: str, feature_names: list[str]):
        """Save the trained model to disk."""
        logger.info(f"Saving LightGBM model to {model_path}")
        Path(model_path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"model": self._model, "feature_names": feature_names},
            model_path,
        )
        self._feature_names = feature_names
        logger.info(f"LightGBM saved: {model_path}")

    def set_model(self, model, feature_names: list[str]):
        """Set the model directly (used during training)."""
        self._model = model
        self._feature_names = feature_names

    def predict(self, features: dict, sequence: pd.DataFrame = None) -> float:
        """Predict forward return for a single observation."""
        if self._model is None:
            raise RuntimeError("LightGBM not loaded. Call load() first.")

        # Build feature array in correct order (same pattern as XGBoostPredictor)
        feature_values = []
        for name in self._feature_names:
            val = features.get(name, np.nan)
            feature_values.append(val if val is not None else np.nan)

        X = np.array([feature_values])
        prediction = float(self._model.predict(X)[0])
        if np.isnan(prediction) or np.isinf(prediction):
            logger.error("LightGBM produced NaN/Inf prediction, returning 0.0")
            return 0.0
        return prediction

    def predict_batch(self, features_df: pd.DataFrame) -> pd.Series:
        """Predict for multiple observations."""
        if self._model is None:
            raise RuntimeError("LightGBM not loaded. Call load() first.")

        X = features_df.reindex(columns=self._feature_names).values
        predictions = self._model.predict(X)
        return pd.Series(predictions, index=features_df.index)

    def get_feature_names(self) -> list[str]:
        """Return the list of feature names this model expects."""
        return list(self._feature_names)

    def get_feature_importance(self) -> dict:
        """Return dict of feature_name -> importance score."""
        if self._model is None:
            return {}
        try:
            importances = self._model.feature_importances_
            return dict(zip(self._feature_names, [float(v) for v in importances]))
        except Exception:
            return {}

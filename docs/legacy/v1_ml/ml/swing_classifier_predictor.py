"""
Swing Classifier predictor — signed confidence output.
Extends scalp classifier pattern to swing/general presets.

Returns signed confidence from predict():
    +0.72 = 72% confident price goes UP in next trading day
    -0.65 = 65% confident price goes DOWN
    0.0   = model is uncertain (probability near 0.5) — no trade signal

Binary classifier: 0=DOWN, 1=UP.
Uses predict_proba() to get P(UP), then converts to signed confidence:
    confidence = (p_up - 0.5) * 2  (maps 0.5→0.0, 1.0→1.0, 0.0→-1.0)
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from ml.predictor import ModelPredictor

logger = logging.getLogger("options-bot.ml.swing_classifier_predictor")

# Binary class labels
CLASS_DOWN = 0
CLASS_UP = 1


class SwingClassifierPredictor(ModelPredictor):
    """Binary classifier for swing/general direction prediction with signed confidence."""

    def __init__(self, model_path: str = None):
        self._model = None
        self._feature_names = []
        self._neutral_band = 0.003  # ±0.30% as decimal
        self._avg_daily_move_pct = 0.0  # Stored from training for EV estimation
        self._model_type = "xgb_swing_classifier"
        if model_path:
            self.load(model_path)

    def load(self, model_path: str):
        """Load a trained swing classifier model from disk."""
        logger.info(f"Loading swing classifier from {model_path}")
        data = joblib.load(model_path)
        self._model = data["model"]
        self._feature_names = data["feature_names"]
        self._neutral_band = data.get("neutral_band", 0.003)
        self._avg_daily_move_pct = data.get("avg_daily_move_pct", 1.0)
        self._model_type = data.get("model_type", "xgb_swing_classifier")
        logger.info(
            f"Swing classifier loaded: {len(self._feature_names)} features, "
            f"type={type(self._model).__name__}, "
            f"model_type={self._model_type}, "
            f"neutral_band={self._neutral_band*100:.2f}%, "
            f"avg_daily_move={self._avg_daily_move_pct:.3f}%"
        )

    def save(self, model_path: str, feature_names: list[str],
             neutral_band: float = 0.003, avg_daily_move_pct: float = 1.0,
             model_type: str = "xgb_swing_classifier"):
        """Save the trained classifier to disk."""
        logger.info(f"Saving swing classifier to {model_path}")
        Path(model_path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self._model,
                "feature_names": feature_names,
                "neutral_band": neutral_band,
                "avg_daily_move_pct": avg_daily_move_pct,
                "model_type": model_type,
                "binary_classifier": True,
            },
            model_path,
        )
        self._feature_names = feature_names
        self._neutral_band = neutral_band
        self._avg_daily_move_pct = avg_daily_move_pct
        self._model_type = model_type
        logger.info(f"Swing classifier saved: {model_path}")

    def set_model(self, model, feature_names: list[str]):
        """Set the model directly (used during training)."""
        self._model = model
        self._feature_names = feature_names

    def predict(self, features: dict, sequence: pd.DataFrame = None) -> float:
        """
        Predict direction with signed confidence for a single observation.

        Returns:
            Signed float where:
                sign = direction (positive=UP, negative=DOWN)
                magnitude = confidence (0.0 to 1.0)
                0.0 = model is uncertain (near 50/50)

        The strategy interprets:
            abs(prediction) >= min_confidence -> enter trade
            sign(prediction) -> CALL if positive, PUT if negative
        """
        if self._model is None:
            raise RuntimeError("Swing classifier not loaded. Call load() first.")

        # Build feature array in correct order
        feature_values = []
        for name in self._feature_names:
            val = features.get(name, np.nan)
            feature_values.append(val if val is not None else np.nan)

        X = np.array([feature_values])
        proba = self._model.predict_proba(X)[0]
        return self._binary_to_signed_confidence(proba)

    def predict_batch(self, features_df: pd.DataFrame) -> pd.Series:
        """Predict signed confidence for multiple observations."""
        if self._model is None:
            raise RuntimeError("Swing classifier not loaded. Call load() first.")

        X = features_df.reindex(columns=self._feature_names).values
        proba_matrix = self._model.predict_proba(X)

        signed_confs = [
            self._binary_to_signed_confidence(proba_matrix[i])
            for i in range(len(proba_matrix))
        ]
        return pd.Series(signed_confs, index=features_df.index)

    def get_feature_names(self) -> list[str]:
        """Return feature names."""
        return list(self._feature_names)

    def get_feature_importance(self) -> dict:
        """Return feature importance scores."""
        if self._model is None:
            return {}
        importance = self._model.feature_importances_
        return dict(zip(self._feature_names, importance.tolist()))

    def get_avg_daily_move_pct(self) -> float:
        """Return the average daily absolute return from training data.
        Used by strategy for EV estimation:
            estimated_return = confidence * avg_daily_move * direction_sign
        """
        return self._avg_daily_move_pct

    def _binary_to_signed_confidence(self, proba: np.ndarray) -> float:
        """
        Convert binary probability [p_down, p_up] to signed confidence.

        Maps p_up (0.0 to 1.0) to signed confidence (-1.0 to +1.0):
            p_up = 0.5  -> confidence = 0.0  (uncertain, no trade)
            p_up = 0.75 -> confidence = +0.50  (moderately bullish)
            p_up = 1.0  -> confidence = +1.0  (very bullish)
            p_up = 0.25 -> confidence = -0.50  (moderately bearish)
            p_up = 0.0  -> confidence = -1.0  (very bearish)
        """
        p_up = float(proba[1]) if len(proba) > 1 else float(proba[0])
        return (p_up - 0.5) * 2.0

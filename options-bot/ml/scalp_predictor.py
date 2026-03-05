"""
Scalp XGBClassifier predictor — signed confidence output.
Matches PROJECT_ARCHITECTURE.md Section 7 — Phase 5: XGBoost Classifier.

Returns signed confidence from predict():
    +0.72 = 72% confident price goes UP in next 30 minutes
    -0.65 = 65% confident price goes DOWN
    0.0   = model's best guess is NEUTRAL (no trade signal)

Internally uses XGBClassifier with 3 classes: 0=DOWN, 1=NEUTRAL, 2=UP
and predict_proba() to get calibrated confidence scores.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import joblib

from ml.predictor import ModelPredictor

logger = logging.getLogger("options-bot.ml.scalp_predictor")

# Class labels
CLASS_DOWN = 0
CLASS_NEUTRAL = 1
CLASS_UP = 2


class ScalpPredictor(ModelPredictor):
    """XGBoost Classifier for scalp direction prediction with signed confidence."""

    def __init__(self, model_path: str = None):
        self._model = None
        self._feature_names = []
        self._neutral_band = 0.0012  # ±0.12% as decimal
        self._avg_30min_move_pct = 0.0  # Stored from training for EV estimation
        if model_path:
            self.load(model_path)

    def load(self, model_path: str):
        """Load a trained scalp classifier model from disk."""
        logger.info(f"Loading scalp classifier from {model_path}")
        data = joblib.load(model_path)
        self._model = data["model"]
        self._feature_names = data["feature_names"]
        self._neutral_band = data.get("neutral_band", 0.0012)
        self._avg_30min_move_pct = data.get("avg_30min_move_pct", 0.10)
        logger.info(
            f"Scalp classifier loaded: {len(self._feature_names)} features, "
            f"type={type(self._model).__name__}, "
            f"neutral_band={self._neutral_band*100:.2f}%, "
            f"avg_30min_move={self._avg_30min_move_pct:.3f}%"
        )

    def save(self, model_path: str, feature_names: list[str],
             neutral_band: float = 0.0012, avg_30min_move_pct: float = 0.10):
        """Save the trained classifier to disk."""
        logger.info(f"Saving scalp classifier to {model_path}")
        Path(model_path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self._model,
                "feature_names": feature_names,
                "neutral_band": neutral_band,
                "avg_30min_move_pct": avg_30min_move_pct,
                "model_type": "xgb_classifier",
            },
            model_path,
        )
        self._feature_names = feature_names
        self._neutral_band = neutral_band
        self._avg_30min_move_pct = avg_30min_move_pct
        logger.info(f"Scalp classifier saved: {model_path}")

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
                0.0 = NEUTRAL (model's best class is neutral)

        The scalp strategy interprets:
            abs(prediction) >= min_confidence -> enter trade
            sign(prediction) -> CALL if positive, PUT if negative
        """
        if self._model is None:
            raise RuntimeError("Scalp classifier not loaded. Call load() first.")

        # Build feature array in correct order
        feature_values = []
        for name in self._feature_names:
            val = features.get(name, np.nan)
            feature_values.append(val if val is not None else np.nan)

        X = np.array([feature_values])
        proba = self._model.predict_proba(X)[0]  # [p_down, p_neutral, p_up]

        return self._proba_to_signed_confidence(proba)

    def predict_batch(self, features_df: pd.DataFrame) -> pd.Series:
        """Predict signed confidence for multiple observations."""
        if self._model is None:
            raise RuntimeError("Scalp classifier not loaded. Call load() first.")

        X = features_df.reindex(columns=self._feature_names).values
        proba_matrix = self._model.predict_proba(X)  # shape: (n, 3)

        signed_confs = [
            self._proba_to_signed_confidence(proba_matrix[i])
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

    def get_avg_30min_move_pct(self) -> float:
        """Return the average 30-min absolute return from training data.
        Used by scalp strategy for EV estimation:
            estimated_return = confidence * avg_30min_move * direction_sign
        """
        return self._avg_30min_move_pct

    def _proba_to_signed_confidence(self, proba: np.ndarray) -> float:
        """
        Convert probability array [p_down, p_neutral, p_up] to signed confidence.

        Logic:
            1. Find the class with highest probability
            2. If NEUTRAL -> return 0.0
            3. If UP -> return +p_up
            4. If DOWN -> return -p_down
        """
        p_down, p_neutral, p_up = float(proba[0]), float(proba[1]), float(proba[2])
        best_class = int(np.argmax(proba))

        if best_class == CLASS_NEUTRAL:
            return 0.0
        elif best_class == CLASS_UP:
            return p_up
        else:  # CLASS_DOWN
            return -p_down

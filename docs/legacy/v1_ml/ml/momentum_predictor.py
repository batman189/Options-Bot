"""
Momentum Predictor — loads a trained momentum continuation model and
produces predictions at inference time.

Output: signed confidence where magnitude = probability of continuation
and sign = direction of the current move (+1 up, -1 down).

Integrates with base_strategy.py via the standard predict() interface.
"""

import logging
from pathlib import Path

import numpy as np
import joblib

logger = logging.getLogger("options-bot.ml.momentum_predictor")


class MomentumPredictor:
    """Predictor for momentum continuation classifier."""

    def __init__(self, model_path: str = None):
        self._model = None
        self._feature_names = None
        self._calibrator = None
        self._metadata = {}

        if model_path:
            self.load(model_path)

    def load(self, model_path: str):
        """Load model, feature names, calibrator, and metadata from disk."""
        data = joblib.load(model_path)
        self._model = data["model"]
        self._feature_names = data["feature_names"]
        self._calibrator = data.get("calibrator")
        self._metadata = data.get("metadata", {})

        logger.info(
            f"MomentumPredictor loaded: {len(self._feature_names)} features, "
            f"calibrator={'yes' if self._calibrator else 'no'}"
        )

    def set_model(self, model, feature_names: list[str]):
        """Set model directly (for incremental training)."""
        self._model = model
        self._feature_names = feature_names

    def save(self, model_path: str, feature_names: list[str], calibrator=None):
        """Save model to disk."""
        data = {
            "model": self._model,
            "feature_names": feature_names,
            "calibrator": calibrator or self._calibrator,
            "metadata": self._metadata,
        }
        joblib.dump(data, model_path)

    def predict(self, latest_features: dict, sequence=None) -> float:
        """
        Predict momentum continuation from a single feature dict.

        Returns signed confidence:
            +0.35 = 35% confidence that an UPWARD move will continue
            -0.42 = 42% confidence that a DOWNWARD move will continue
            Near 0 = no momentum event detected or low confidence

        The sign comes from the event_direction feature (which direction
        the current move is going). The magnitude comes from the calibrated
        probability of continuation.
        """
        if self._model is None:
            raise RuntimeError("No model loaded")

        # Build feature array in the correct order
        X = np.array([[latest_features.get(f, np.nan) for f in self._feature_names]])

        # Get raw probability of continuation
        raw_proba = self._model.predict_proba(X)[0]

        # Binary classifier: index 1 = P(continuation)
        p_continue = float(raw_proba[1]) if len(raw_proba) > 1 else float(raw_proba[0])

        # Apply calibration if available
        if self._calibrator is not None:
            p_continue = float(
                np.clip(self._calibrator.predict([p_continue])[0], 0.0, 1.0)
            )

        # Convert to signed confidence:
        # confidence = P(continuation) - 0.5, scaled to [-1, +1]
        # Then multiply by the direction of the current move
        confidence = (p_continue - 0.5) * 2  # Maps [0, 1] -> [-1, 1]

        # Get the direction from features
        direction = latest_features.get("event_direction", 0)
        if direction == 0:
            # No momentum event — check velocity to infer direction
            vel_5 = latest_features.get("mom_velocity_5m", 0)
            direction = 1.0 if vel_5 > 0 else -1.0

        # Signed confidence: positive = bullish continuation, negative = bearish
        signed_confidence = confidence * direction

        return float(signed_confidence)

    def predict_batch(self, features_df) -> list[float]:
        """Predict on a DataFrame of features. Returns list of signed confidence values."""
        if self._model is None:
            raise RuntimeError("No model loaded")

        X = features_df[self._feature_names].values
        raw_proba = self._model.predict_proba(X)[:, 1]

        if self._calibrator is not None:
            calibrated = np.clip(self._calibrator.predict(raw_proba), 0.0, 1.0)
        else:
            calibrated = raw_proba

        confidence = (calibrated - 0.5) * 2

        # Get direction from features
        if "event_direction" in features_df.columns:
            directions = features_df["event_direction"].values
        else:
            vel_5 = features_df.get("mom_velocity_5m", pd.Series(0, index=features_df.index))
            directions = np.where(vel_5 > 0, 1.0, -1.0)

        return (confidence * directions).tolist()

    def get_metadata(self) -> dict:
        """Return training metadata."""
        return self._metadata

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

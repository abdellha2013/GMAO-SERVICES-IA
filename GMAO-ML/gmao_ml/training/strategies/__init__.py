"""Stratégies d'entraînement disponibles dans GMAO-ML."""

from __future__ import annotations

from gmao_ml.training.strategies.base import TrainingStrategy
from gmao_ml.training.strategies.hist_gradient_boosting import (
    HistGradientBoostingStrategy,
)
from gmao_ml.training.strategies.logistic_regression import (
    LogisticRegressionStrategy,
)
from gmao_ml.training.strategies.random_forest import RandomForestStrategy

__all__ = [
    "TrainingStrategy",
    "LogisticRegressionStrategy",
    "RandomForestStrategy",
    "HistGradientBoostingStrategy",
]

"""Stratégie de régression logistique (baseline linéaire)."""

from __future__ import annotations

from typing import Any

from sklearn.linear_model import LogisticRegression

from gmao_ml.training.strategies.base import TrainingStrategy

__all__ = ["LogisticRegressionStrategy"]


class LogisticRegressionStrategy(TrainingStrategy):
    """Baseline rapide et interprétable pour la classification multi-classes."""

    def __init__(
        self,
        random_state: int = 42,
        max_iter: int = 1000,
        balance_class_weights: bool = False,
    ) -> None:
        self._random_state = random_state
        self._max_iter = max_iter
        self._class_weight = "balanced" if balance_class_weights else None

    @property
    def name(self) -> str:
        """Identifiant registre de la stratégie."""

        return "logistic_regression"

    def create_estimator(self) -> Any:
        """Instancie un ``LogisticRegression`` multi-classes."""

        return LogisticRegression(
            max_iter=self._max_iter,
            random_state=self._random_state,
            class_weight=self._class_weight,
        )

    def get_params(self) -> dict[str, Any]:
        """Hyperparamètres journalisés dans MLflow."""

        return {
            "max_iter": self._max_iter,
            "class_weight": str(self._class_weight),
        }

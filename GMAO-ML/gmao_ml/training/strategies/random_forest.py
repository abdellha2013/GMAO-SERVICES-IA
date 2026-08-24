"""Stratégie forêt aléatoire (ensemble d'arbres, robuste par défaut)."""

from __future__ import annotations

from typing import Any

from sklearn.ensemble import RandomForestClassifier

from gmao_ml.training.strategies.base import TrainingStrategy

__all__ = ["RandomForestStrategy"]


class RandomForestStrategy(TrainingStrategy):
    """Forêt aléatoire : bon compromis performance/robustesse sur tabulaire."""

    def __init__(
        self,
        random_state: int = 42,
        n_estimators: int = 300,
        n_jobs: int = -1,
        balance_class_weights: bool = False,
    ) -> None:
        self._random_state = random_state
        self._n_estimators = n_estimators
        self._n_jobs = n_jobs
        self._class_weight = "balanced" if balance_class_weights else None

    @property
    def name(self) -> str:
        """Identifiant registre de la stratégie."""

        return "random_forest"

    def create_estimator(self) -> Any:
        """Instancie un ``RandomForestClassifier``."""

        return RandomForestClassifier(
            n_estimators=self._n_estimators,
            random_state=self._random_state,
            n_jobs=self._n_jobs,
            class_weight=self._class_weight,
        )

    def get_params(self) -> dict[str, Any]:
        """Hyperparamètres journalisés dans MLflow."""

        return {
            "n_estimators": self._n_estimators,
            "class_weight": str(self._class_weight),
        }

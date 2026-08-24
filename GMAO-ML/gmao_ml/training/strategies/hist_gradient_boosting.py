"""Stratégie gradient boosting histogramme (équivalent LightGBM/XGBoost natif sklearn)."""

from __future__ import annotations

from typing import Any

from sklearn.ensemble import HistGradientBoostingClassifier

from gmao_ml.training.strategies.base import TrainingStrategy

__all__ = ["HistGradientBoostingStrategy"]


class HistGradientBoostingStrategy(TrainingStrategy):
    """Boosting performant sur données tabulaires, sans dépendance externe.

    Note
    ----
    Le support de ``class_weight`` est disponible depuis scikit-learn
    1.8 ; ``balance_class_weights=True`` transmet donc
    ``class_weight="balanced"`` comme pour les autres stratégies.
    """

    def __init__(
        self,
        random_state: int = 42,
        balance_class_weights: bool = False,
    ) -> None:
        self._random_state = random_state
        self._class_weight = "balanced" if balance_class_weights else None

    @property
    def name(self) -> str:
        """Identifiant registre de la stratégie."""

        return "hist_gradient_boosting"

    def create_estimator(self) -> Any:
        """Instancie un ``HistGradientBoostingClassifier``."""

        return HistGradientBoostingClassifier(
            random_state=self._random_state,
            class_weight=self._class_weight,
        )

    def get_params(self) -> dict[str, Any]:
        """Hyperparamètres journalisés dans MLflow."""

        return {
            "class_weight": str(self._class_weight),
        }

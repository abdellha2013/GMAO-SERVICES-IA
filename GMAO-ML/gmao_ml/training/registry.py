"""Registre des stratégies d'entraînement GMAO-ML."""

from __future__ import annotations

from gmao_ml.exceptions import (
    InvalidTrainingStrategyError,
    TrainingStrategyNotRegisteredError,
    TrainingValidationError,
)
from gmao_ml.training.strategies.base import TrainingStrategy
from gmao_ml.training.strategies.hist_gradient_boosting import (
    HistGradientBoostingStrategy,
)
from gmao_ml.training.strategies.logistic_regression import (
    LogisticRegressionStrategy,
)
from gmao_ml.training.strategies.random_forest import RandomForestStrategy

__all__ = ["TrainingStrategyRegistry"]


class TrainingStrategyRegistry:
    """Stocke les classes de stratégies sous leur nom normalisé (minuscule)."""

    def __init__(self) -> None:
        self._strategies: dict[str, type[TrainingStrategy]] = {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str):
            raise TrainingValidationError(
                message="strategy name must be a string.",
                details={"received_type": type(name).__name__},
            )

        normalized = name.strip().lower()
        if not normalized:
            raise TrainingValidationError(
                message="strategy name must not be empty.",
            )

        return normalized

    @staticmethod
    def _validate_strategy(strategy: type[TrainingStrategy]) -> None:
        if not isinstance(strategy, type):
            raise InvalidTrainingStrategyError(
                message="strategy must be a class.",
                details={"received_type": type(strategy).__name__},
            )

        if not issubclass(strategy, TrainingStrategy):
            raise InvalidTrainingStrategyError(
                message="strategy must inherit from TrainingStrategy.",
                details={
                    "strategy": getattr(strategy, "__name__", type(strategy).__name__),
                    "expected_base": "TrainingStrategy",
                },
            )

    def register(self, strategy: type[TrainingStrategy]) -> None:
        """Enregistre une classe de stratégie via le nom d'une instance par défaut."""

        self._validate_strategy(strategy)

        try:
            instance = strategy()
            name = self._normalize_name(instance.name)
        except (TrainingValidationError, InvalidTrainingStrategyError):
            raise
        except Exception as exc:
            raise InvalidTrainingStrategyError(
                message="Unable to instantiate training strategy.",
                details={"strategy": strategy.__name__},
                original=exc,
            ) from exc

        if name in self._strategies:
            raise TrainingValidationError(
                message=f"A training strategy is already registered as '{name}'.",
                details={
                    "strategy": strategy.__name__,
                    "existing_strategy": self._strategies[name].__name__,
                },
            )

        self._strategies[name] = strategy

    def get(self, name: str) -> type[TrainingStrategy]:
        """Retourne la classe enregistrée sous ``name``."""

        normalized = self._normalize_name(name)
        try:
            return self._strategies[normalized]
        except KeyError:
            raise TrainingStrategyNotRegisteredError(
                message=f"No training strategy registered as '{normalized}'.",
                details={
                    "strategy_name": normalized,
                    "supported_strategies": self.supported_strategies(),
                },
            ) from None

    def has(self, name: str) -> bool:
        """Variante silencieuse de :meth:`get` (booléen, sans exception)."""

        return isinstance(name, str) and bool(name.strip()) and name.strip().lower() in self._strategies

    def unregister(self, name: str) -> None:
        """Retire la classe associée à ``name``."""

        normalized = self._normalize_name(name)
        if normalized not in self._strategies:
            raise TrainingStrategyNotRegisteredError(
                message=f"No training strategy registered as '{normalized}'.",
                details={
                    "strategy_name": normalized,
                    "supported_strategies": self.supported_strategies(),
                },
            )
        del self._strategies[normalized]

    def supported_strategies(self) -> list[str]:
        """Liste triée des noms de stratégies disponibles."""

        return sorted(self._strategies.keys())


def build_default_registry(random_state: int = 42) -> TrainingStrategyRegistry:
    """Construit un registre pré-rempli avec les stratégies standard.

    Parameters
    ----------
    random_state:
        Graine transmise aux stratégies pour la reproductibilité.

    Returns
    -------
    TrainingStrategyRegistry
        Registre contenant logistic_regression / random_forest /
        hist_gradient_boosting.
    """

    registry = TrainingStrategyRegistry()
    registry.register(LogisticRegressionStrategy)
    registry.register(RandomForestStrategy)
    registry.register(HistGradientBoostingStrategy)
    return registry

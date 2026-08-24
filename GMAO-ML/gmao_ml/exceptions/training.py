"""Exceptions de la couche entraînement (stratégies, orchestration)."""

from __future__ import annotations

from gmao_ml.exceptions.base_exception import MLError

__all__ = [
    "InvalidTrainingStrategyError",
    "TrainingError",
    "TrainingStrategyNotRegisteredError",
    "TrainingValidationError",
]


class TrainingError(MLError):
    """Base des erreurs liées à l'entraînement."""


class TrainingValidationError(TrainingError):
    """Les données ou paramètres fournis à l'entraînement sont invalides."""


class InvalidTrainingStrategyError(TrainingError):
    """La classe fournie n'est pas une stratégie d'entraînement valide."""


class TrainingStrategyNotRegisteredError(TrainingError):
    """Aucune stratégie d'entraînement enregistrée sous ce nom."""

"""Exceptions de la couche modèle (artefacts, inférence, sérialisation)."""

from __future__ import annotations

from gmao_ml.exceptions.base_exception import MLError

__all__ = [
    "ModelError",
    "InferenceValidationError",
    "ModelNotFoundError",
    "ModelNotReadyError",
    "ModelSerializationError",
    "PredictionError",
]


class ModelError(MLError):
    """Base des erreurs liées aux modèles et artefacts."""


class ModelNotFoundError(ModelError):
    """L'artefact demandé (modèle ou métadonnées) est introuvable."""


class ModelNotReadyError(ModelError):
    """Aucun modèle n'est chargé en mémoire côté service de prédiction."""


class ModelSerializationError(ModelError):
    """La sérialisation/désérialisation d'un artefact a échoué."""


class PredictionError(ModelError):
    """Erreur survenue pendant l'exécution d'une prédiction."""


class InferenceValidationError(ModelError):
    """Les features fournies en entrée de l'inférence sont invalides."""

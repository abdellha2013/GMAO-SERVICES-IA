"""Exceptions de la couche données (chargement / validation de datasets)."""

from __future__ import annotations

from gmao_ml.exceptions.base_exception import MLError

__all__ = [
    "DataError",
    "DatasetLoadError",
    "DatasetValidationError",
]


class DataError(MLError):
    """Base des erreurs liées à la couche données."""


class DatasetLoadError(DataError):
    """Le dataset n'a pas pu être lu ou trouvé (fichier absent, illisible…)."""


class DatasetValidationError(DataError):
    """Le dataset ne respecte pas le contrat attendu (colonnes, volume, qualité)."""

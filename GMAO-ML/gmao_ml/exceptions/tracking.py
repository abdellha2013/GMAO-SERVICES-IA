"""Exceptions de la couche tracking (MLflow)."""

from __future__ import annotations

from gmao_ml.exceptions.base_exception import MLError

__all__ = [
    "TrackingError",
]


class TrackingError(MLError):
    """Erreur survenue lors du suivi d'expériences (MLflow indisponible, URI invalide…)."""

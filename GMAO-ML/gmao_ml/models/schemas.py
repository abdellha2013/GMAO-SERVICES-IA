"""Schémas Pydantic des requêtes/réponses de l'API GMAO-ML."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "PredictRequest",
    "BatchPredictRequest",
    "PredictionItem",
    "PredictResponse",
    "BatchPredictResponse",
    "ModelInfoResponse",
    "HealthResponse",
]


class PredictRequest(BaseModel):
    """Requête de prédiction unitaire.

    Les clés de ``features`` doivent correspondre aux colonnes attendues
    par le modèle (les colonnes manquantes seront imputées, les colonnes
    superflues ignorées).
    """

    features: dict[str, Any] = Field(
        ...,
        description="Feature vector keyed by column name.",
        examples=[{
            "type_machine": "Pompe",
            "temperature_c": 82.5,
            "vibration_mm_s": 6.1,
            "pression_bar": 7.2,
            "rotation_tr_min": 3150,
            "heures_depuis_maintenance": 830,
            "age_mois": 96,
        }],
    )


class BatchPredictRequest(BaseModel):
    """Requête de prédiction par lot (max 1000 échantillons)."""

    samples: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of feature vectors.",
    )


class PredictionItem(BaseModel):
    """Résultat de prédiction pour un échantillon."""

    prediction: str | int | float = Field(..., description="Predicted class label.")
    probabilities: dict[str, float] | None = Field(
        None,
        description="Class probabilities, when the estimator exposes predict_proba.",
    )
    model_version: str = Field(..., description="Version of the model used.")


class PredictResponse(PredictionItem):
    """Réponse de prédiction unitaire."""


class BatchPredictResponse(BaseModel):
    """Réponse de prédiction par lot."""

    predictions: list[PredictionItem]
    count: int = Field(..., ge=0)
    model_version: str


class ModelInfoResponse(BaseModel):
    """Métadonnées du modèle actuellement chargé."""

    name: str
    version: str
    strategy: str
    target_column: str
    classes: list[str]
    features: dict[str, list[str]]
    metrics: dict[str, Any]
    trained_at: str
    n_training_samples: int
    sklearn_version: str


class HealthResponse(BaseModel):
    """Réponse du endpoint de santé."""

    status: str = "ok"
    service: str = "gmao-ml"
    model_loaded: bool
    model_name: str | None = None
    model_version: str | None = None

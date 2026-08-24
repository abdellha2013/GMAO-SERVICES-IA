"""Modèles de domaine et schémas Pydantic de GMAO-ML."""

from __future__ import annotations

from gmao_ml.models.schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    HealthResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    PredictionItem,
)

__all__ = [
    "PredictRequest",
    "BatchPredictRequest",
    "PredictionItem",
    "PredictResponse",
    "BatchPredictResponse",
    "ModelInfoResponse",
    "HealthResponse",
]

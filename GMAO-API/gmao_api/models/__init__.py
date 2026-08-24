"""Schémas de l'API GMAO-API."""

from gmao_api.models.schemas import (
    AlertRecord,
    AlertsResponse,
    HealthResponse,
    PredictionOutcome,
    PredictionsRequest,
    PredictionsResponse,
    SensorReading,
    SimulateRequest,
)

__all__ = [
    "SensorReading",
    "PredictionsRequest",
    "SimulateRequest",
    "PredictionOutcome",
    "PredictionsResponse",
    "AlertRecord",
    "AlertsResponse",
    "HealthResponse",
]

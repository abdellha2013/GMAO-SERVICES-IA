"""Orchestrateur : relevé → prédiction ML."""

from __future__ import annotations

import logging
from typing import Any

from gmao_api.exceptions import ApiError
from gmao_api.models.schemas import (
    PredictionOutcome,
    PredictionsResponse,
    SensorReading,
)
from gmao_api.services.equipment_service import EquipmentService
from gmao_api.services.ml_client import MlClient, positive_probability

logger = logging.getLogger("gmao_api.orchestrator")


def _as_int(prediction: Any) -> int:
    """Normalise la prédiction ('1', 1, 1.0 → 1)."""

    try:
        return int(str(prediction))
    except (TypeError, ValueError):
        return -1


class PredictionOrchestrator:
    """Chaîne complète pour un lot de relevés."""

    def __init__(
        self,
        ml_client: MlClient,
        equipment_service: EquipmentService,
    ) -> None:
        self._ml = ml_client
        self._equipment = equipment_service

    async def process(self, readings: list[SensorReading]) -> PredictionsResponse:
        results: list[PredictionOutcome] = []
        model_version: str | None = None

        for reading in readings:
            outcome = await self._process_one(reading)
            model_version = model_version or outcome.model_version
            results.append(outcome)

        return PredictionsResponse(
            results=results,
            model_version=model_version,
        )

    async def _process_one(self, reading: SensorReading) -> PredictionOutcome:
        equipement_nom = await self._equipment.describe(reading.equipement_id)

        ml_result = await self._ml.predict(reading.to_ml_features())
        probability = positive_probability(ml_result["probabilities"])
        prediction = _as_int(ml_result["prediction"])
        model_version = ml_result.get("model_version")

        if prediction == 1:
            logger.info("PANNE prédite — %s P=%.3f", equipement_nom, probability)

        return PredictionOutcome(
            equipement_id=reading.equipement_id,
            equipement_nom=equipement_nom,
            prediction=prediction,
            probability_failure=probability,
            model_version=model_version,
        )


__all__ = ["PredictionOrchestrator", "ApiError"]

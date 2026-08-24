"""Orchestrateur : relevé → prédiction ML → (alerte Laravel si panne)."""

from __future__ import annotations

import logging
from typing import Any

from gmao_api.config import Settings
from gmao_api.exceptions import ApiError
from gmao_api.models.schemas import (
    PredictionOutcome,
    PredictionsResponse,
    SensorReading,
)
from gmao_api.services import equipment_catalog
from gmao_api.services.journal import AlertJournal
from gmao_api.services.laravel_client import LaravelClient, build_demande_intervention
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
        settings: Settings,
        ml_client: MlClient,
        laravel_client: LaravelClient,
        journal: AlertJournal,
    ) -> None:
        self._settings = settings
        self._ml = ml_client
        self._laravel = laravel_client
        self._journal = journal

    async def process(self, readings: list[SensorReading]) -> PredictionsResponse:
        results: list[PredictionOutcome] = []
        alerts_count = 0
        model_version: str | None = None

        for reading in readings:
            outcome = await self._process_one(reading)
            model_version = model_version or _first_version(outcome)
            if outcome.alert_sent:
                alerts_count += 1
            results.append(outcome)

        return PredictionsResponse(
            results=results,
            alerts_count=alerts_count,
            model_version=model_version,
        )

    async def _process_one(self, reading: SensorReading) -> PredictionOutcome:
        equipement = equipment_catalog.get_equipement(reading.equipement_id)
        equipement_nom = equipment_catalog.describe(reading.equipement_id)

        ml_result = await self._ml.predict(reading.to_ml_features())
        probability = positive_probability(ml_result["probabilities"])
        prediction = _as_int(ml_result["prediction"])
        model_version = ml_result.get("model_version")

        alert_sent = False
        delivery = "not_triggered"
        laravel_response: dict[str, Any] | None = None
        payload: dict[str, Any] | None = None

        if prediction == 1:
            payload = build_demande_intervention(
                reading=reading,
                probability_failure=probability,
                model_version=model_version,
                settings=self._settings,
            )
            delivery, laravel_response = await self._laravel.send_alert(payload)
            alert_sent = delivery in {"sent", "simulated"}

            self._journal.add(
                equipement_id=reading.equipement_id,
                equipement_nom=equipement_nom,
                probability_failure=probability,
                delivery=delivery,
                demande_intervention=payload,
                laravel_response=laravel_response,
                model_version=model_version,
            )

            logger.info(
                "Alerte (%s) — %s P=%.3f",
                delivery,
                equipement_nom,
                probability,
            )

        return PredictionOutcome(
            equipement_id=reading.equipement_id,
            equipement_nom=equipement_nom,
            prediction=prediction,
            probability_failure=probability,
            alert_sent=alert_sent,
            alert_delivery=delivery,
            demande_intervention=payload,
            laravel_response=laravel_response,
        )


def _first_version(outcome: PredictionOutcome) -> str | None:
    payload = outcome.demande_intervention or {}
    meta = payload.get("_meta") or {}
    version = meta.get("model_version")
    return version if isinstance(version, str) else None


__all__ = ["PredictionOrchestrator", "ApiError"]

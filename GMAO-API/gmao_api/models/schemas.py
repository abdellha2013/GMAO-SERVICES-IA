"""Schémas Pydantic des requêtes/réponses de GMAO-API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "SensorReading",
    "PredictionsRequest",
    "SimulateRequest",
    "PredictionOutcome",
    "PredictionsResponse",
    "HealthResponse",
]


class SensorReading(BaseModel):
    """Relevé capteurs d'une machine (schéma AI4I) rattaché à un équipement réel."""

    model_config = ConfigDict(populate_by_name=True)

    equipement_id: int = Field(..., ge=1, description="ID de la table equipements.")
    machine_type: Literal["L", "M", "H"] = Field("L", alias="Type")
    air_temperature_k: float = Field(..., alias="Air temperature [K]", gt=250, lt=350)
    process_temperature_k: float = Field(..., alias="Process temperature [K]", gt=250, lt=400)
    rotational_speed_rpm: float = Field(..., alias="Rotational speed [rpm]", gt=0)
    torque_nm: float = Field(..., alias="Torque [Nm]", ge=0)
    tool_wear_min: float = Field(..., alias="Tool wear [min]", ge=0)

    def to_ml_features(self) -> dict[str, Any]:
        """Colonnes brutes attendues par le modèle GMAO-ML (input_features)."""

        return {
            "Type": self.machine_type,
            "Air temperature [K]": self.air_temperature_k,
            "Process temperature [K]": self.process_temperature_k,
            "Rotational speed [rpm]": self.rotational_speed_rpm,
            "Torque [Nm]": self.torque_nm,
            "Tool wear [min]": self.tool_wear_min,
        }


class PredictionsRequest(BaseModel):
    """Relevés réels soumis à la chaîne complète."""

    readings: list[SensorReading] = Field(..., min_length=1, max_length=100)


class SimulateRequest(BaseModel):
    """Génération artificielle de relevés puis chaîne complète identique."""

    count: int = Field(10, ge=1, le=100)
    failure_rate: float = Field(0.3, ge=0.0, le=1.0)
    random_state: int | None = Field(None, description="Seed pour reproductibilité.")


class PredictionOutcome(BaseModel):
    """Résultat du pipeline pour un relevé."""

    equipement_id: int
    equipement_nom: str
    prediction: int
    probability_failure: float
    model_version: str | None = None


class PredictionsResponse(BaseModel):
    results: list[PredictionOutcome]
    readings: list[dict] | None = None
    model_version: str | None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "gmao-api"
    version: str
    ml_api_reachable: bool

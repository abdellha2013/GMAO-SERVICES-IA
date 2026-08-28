"""Schémas Pydantic des requêtes/réponses de GMAO-ANALYTICS."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EquipementMeta",
    "EquipementMetrics",
    "GlobalMetrics",
    "RiskCrossover",
    "ReportResponse",
    "HealthResponse",
    "MetricSummary",
]


class EquipementMeta(BaseModel):
    """Identité d'un équipement du référentiel."""

    id_equipement: int
    nom_equipement: str
    localisation: str | None = None
    criticite: str | None = None
    marque: str | None = None
    modele: str | None = None


class MetricSummary(BaseModel):
    """Indicateurs calculés pour un équipement (ou agrégat global)."""

    mtbf_hours: float | None = Field(None, description="Temps moyen entre pannes (h).")
    mttr_hours: float | None = Field(None, description="Temps moyen de réparation (h).")
    availability_pct: float | None = Field(None, description="Disponibilité = MTBF/(MTBF+MTTR) (%).")
    nb_pannes: int = 0
    nb_interventions: int = 0


class EquipementMetrics(EquipementMeta, MetricSummary):
    """Indicateurs + identité d'un équipement."""


class GlobalMetrics(BaseModel):
    """Agrégat global du parc + répartition par équipement."""

    model_config = ConfigDict(populate_by_name=True)

    global_: MetricSummary = Field(alias="global")
    per_equipement: list[EquipementMetrics]
    generated_at: str | None = None


class RiskCrossover(BaseModel):
    """Croisement risque ML prédit ↔ historique de maintenance (MTBF)."""

    equipement_id: int
    equipement_nom: str
    predicted_risk: str
    probability_failure: float | None = None
    mtbf_hours: float | None = None
    nb_pannes: int = 0
    comment: str | None = None


class ReportResponse(BaseModel):
    """Rapport de maintenance complet."""

    generated_at: str
    global_metrics: MetricSummary
    per_equipement: list[EquipementMetrics]
    risk: list[RiskCrossover] | None = None
    text: str | None = Field(None, description="Rapport texte (markdown) lisible.")
    content_type: str = "json"


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "gmao-analytics"
    version: str
    ml_api_reachable: bool = False
    equipements_count: int = 0

"""Service d'analytique : calcule les indicateurs MTBF/MTTR/disponibilité
à partir de la source DB et les enrichit du risque prédit (GMAO-ML).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from gmao_analytics.db import MaintenanceSource
from gmao_analytics.metrics.engine import global_summary, metric_summary_from_df
from gmao_analytics.models.schemas import (
    EquipementMetrics,
    GlobalMetrics,
    MetricSummary,
    ReportResponse,
    RiskCrossover,
)

logger = logging.getLogger("gmao_analytics.analytics")


class AnalyticsService:
    """Agrège les données de maintenance et calcule les indicateurs."""

    def __init__(
        self,
        source: MaintenanceSource,
        ml_enrich=None,
    ) -> None:
        self._source = source
        self._ml_enrich = ml_enrich  # callable(async) ou None → risque ML

    async def computed_generated(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    async def compute_metrics(self) -> GlobalMetrics:
        """Indicateurs globaux + ventilés par équipement."""

        equipements = await self._source.equipements()
        panne_df = await self._source.panne_df()
        ot_df = await self._source.ot_df()

        per_equip: list[EquipementMetrics] = []
        for eq in equipements:
            eq_panne = _filter(panne_df, eq["id_equipement"])
            eq_ot = _filter_ot(ot_df, eq["id_equipement"])
            m = metric_summary_from_df(eq_panne, eq_ot)
            per_equip.append(
                EquipementMetrics(
                    **eq,
                    **m,
                )
            )

        global_ = MetricSummary(**global_summary([e.model_dump() for e in per_equip]))
        return GlobalMetrics(
            global_=global_,
            per_equipement=per_equip,
            generated_at=await self.computed_generated(),
        )

    async def compute_report(self) -> ReportResponse:
        """Rapport complet : indicateurs + risque ML enrichi + texte lisible."""

        g = await self.compute_metrics()
        risk = await self._compute_risk(g.per_equipement) if self._ml_enrich else None
        text = build_report_text(g, risk)
        return ReportResponse(
            generated_at=g.generated_at,
            global_metrics=g.global_,
            per_equipement=g.per_equipement,
            risk=risk,
            text=text,
            content_type="json",
        )

    async def _compute_risk(self, per_equip: list[EquipementMetrics]) -> list[RiskCrossover]:
        if self._ml_enrich is None:
            return []
        try:
            return await self._ml_enrich([e.id_equipement for e in per_equip], per_equip)
        except Exception as exc:  # pragma: no cover - tolérance
            logger.warning("Enrichissement ML indisponible : %s", exc)
            return []


def _filter(panne_df: pd.DataFrame, equipement_id: int) -> pd.DataFrame:
    if panne_df is None or panne_df.empty:
        return pd.DataFrame(columns=["id_equipement", "date_detection"])
    return panne_df[panne_df["id_equipement"] == equipement_id]


def _filter_ot(ot_df: pd.DataFrame, equipement_id: int) -> pd.DataFrame:
    if ot_df is None or ot_df.empty:
        return pd.DataFrame(columns=["id_equipement", "statut", "date_debut", "date_fin", "temps_reel"])
    return ot_df[(ot_df["id_equipement"] == equipement_id) & (ot_df["statut"] == "termine")]


def build_report_text(g: GlobalMetrics, risk: list[RiskCrossover] | None) -> str:
    """Produit un rapport lisible (format markdown)."""

    gm = g.global_
    lines: list[str] = []
    lines.append("# Rapport de maintenance (GMAO Analytics)")
    lines.append("")
    lines.append(f"_Généré le : {g.generated_at}_")
    lines.append("")
    lines.append("## Indicateurs globaux")
    lines.append("")
    lines.append("| Indicateur | Valeur |")
    lines.append("|---|---|")
    lines.append(f"| MTBF | {_fmt(gm.mtbf_hours)} h |")
    lines.append(f"| MTTR | {_fmt(gm.mttr_hours)} h |")
    lines.append(f"| Disponibilité | {_fmt(gm.availability_pct)} % |")
    lines.append(f"| Pannes recensées | {gm.nb_pannes} |")
    lines.append(f"| Interventions terminées | {gm.nb_interventions} |")
    lines.append("")
    lines.append("## Détail par équipement")
    lines.append("")
    lines.append("| Équipement | MTBF (h) | MTTR (h) | Dispo (%) | Pannes |")
    lines.append("|---|---|---|---|---|")
    for e in g.per_equipement:
        lines.append(
            f"| {e.nom_equipement} (#{e.id_equipement}) | {_fmt(e.mtbf_hours)} | "
            f"{_fmt(e.mttr_hours)} | {_fmt(e.availability_pct)} | {e.nb_pannes} |"
        )

    if risk:
        lines.append("")
        lines.append("## Croisement risque prédictif (GMAO-ML)")
        lines.append("")
        lines.append("| Équipement | Risque prédit | P(panne) | MTBF (h) |")
        lines.append("|---|---|---|---|")
        for r in risk:
            lines.append(
                f"| {r.equipement_nom} (#{r.equipement_id}) | {r.predicted_risk} | "
                f"{_fmt(r.probability_failure)} | {_fmt(r.mtbf_hours)} |"
            )

    return "\n".join(lines) + "\n"


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:g}"


__all__ = ["AnalyticsService", "build_report_text"]

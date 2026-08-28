"""Routes v1 de GMAO-ANALYTICS."""

from __future__ import annotations

import io
import logging
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request, Response

from gmao_analytics.models.schemas import (
    GlobalMetrics,
    HealthResponse,
    ReportResponse,
)

logger = logging.getLogger("gmao_analytics.routes")

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz(request: Request) -> HealthResponse:
    """État du service + joignabilité GMAO-ML (enrichissement)."""

    ml_ok = False
    if request.app.state.ml_enricher is not None:
        ml_ok = await request.app.state.ml_enricher.health()

    equipements = await request.app.state.analytics._source.equipements()
    return HealthResponse(
        status="ok",
        service="gmao-analytics",
        version=request.app.state.version,
        ml_api_reachable=ml_ok,
        equipements_count=len(equipements),
    )


@router.get("/metrics", response_model=GlobalMetrics, tags=["metrics"])
async def get_metrics(request: Request) -> GlobalMetrics:
    """Indicateurs globaux MTBF/MTTR/disponibilité + ventilation par équipement."""

    return await request.app.state.analytics.compute_metrics()


@router.get("/metrics/equipements", response_model=GlobalMetrics, tags=["metrics"])
async def get_metrics_equipements(request: Request) -> GlobalMetrics:
    """Alias lisible : mêmes indicateurs (global + par équipement)."""

    return await request.app.state.analytics.compute_metrics()


@router.get("/metrics/equipement/{id_equipement}", response_model=GlobalMetrics, tags=["metrics"])
async def get_metrics_equipement(id_equipement: int, request: Request) -> GlobalMetrics:
    """Indicateurs filtrés sur un équipement précis."""

    g = await request.app.state.analytics.compute_metrics()
    per_equip = [e for e in g.per_equipement if e.id_equipement == id_equipement]
    if not per_equip:
        raise HTTPException(status_code=404, detail=f"Équipement {id_equipement} introuvable.")
    g.per_equipement = per_equip
    return g


@router.get("/report", response_model=ReportResponse, tags=["reports"])
async def get_report(
    request: Request,
    format: Literal["json", "csv", "markdown"] = Query("json", description="Format du rapport."),
) -> Response | ReportResponse:
    """Rapport de maintenance complet, exportable en CSV ou Markdown."""

    report = await request.app.state.analytics.compute_report()

    if format == "markdown":
        return Response(
            content=report.text or "",
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment; filename=rapport_maintenance.md"},
        )
    if format == "csv":
        csv_content = _report_to_csv(report)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=rapport_maintenance.csv"},
        )
    return report


def _report_to_csv(report: ReportResponse) -> str:
    """Transforme le rapport en CSV (table plate par équipement)."""

    buffer = io.StringIO()
    frame = pd.DataFrame([e.model_dump() for e in report.per_equipement])
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()


__all__ = ["router"]

"""Routes v1 de GMAO-API."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from gmao_api.api.auth import verify_api_key
from gmao_api.exceptions import ApiError
from gmao_api.models.schemas import (
    AlertsResponse,
    HealthResponse,
    PredictionsRequest,
    PredictionsResponse,
    SimulateRequest,
)
from gmao_api.services.simulator import generate_batch

logger = logging.getLogger("gmao_api.routes")

router = APIRouter()


def _orchestrator(request: Request):
    return request.app.state.orchestrator


def _settings(request: Request):
    return request.app.state.settings


@router.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz(request: Request) -> HealthResponse:
    """Sonde de disponibilité (non authentifiée)."""

    settings = request.app.state.settings
    ml_ok = await request.app.state.ml_client.health()
    return HealthResponse(
        status="ok" if ml_ok else "degraded",
        service="gmao-api",
        version=request.app.state.version,
        ml_api_reachable=ml_ok,
        laravel_mode="simulated" if settings.simulate_laravel else "real",
    )


@router.post("/predictions", response_model=PredictionsResponse, tags=["predictions"])
async def create_predictions(
    payload: PredictionsRequest,
    request: Request,
    _token: str = Depends(verify_api_key),
) -> PredictionsResponse:
    """Relevés réels → prédiction ML → alertes Laravel si panne."""

    logger.info("POST /predictions — %d relevé(s)", len(payload.readings))
    return await request.app.state.orchestrator.process(list(payload.readings))


@router.post("/simulate", response_model=PredictionsResponse, tags=["simulation"])
async def simulate(
    payload: SimulateRequest,
    request: Request,
    _token: str = Depends(verify_api_key),
) -> PredictionsResponse:
    """Génère des relevés artificiels puis exécute la chaîne complète identique."""

    equipement_ids = await request.app.state.equipment_service.equipment_ids()
    readings_raw = generate_batch(
        count=payload.count,
        failure_rate=payload.failure_rate,
        random_state=payload.random_state,
        equipement_ids=equipement_ids,
    )
    readings = [request.app.state.reading_model.model_validate(r) for r in readings_raw]
    logger.info(
        "POST /simulate — %d relevés générés (failure_rate=%.2f, %d équipements dispo)",
        len(readings),
        payload.failure_rate,
        len(equipement_ids),
    )
    return await request.app.state.orchestrator.process(readings)


@router.get("/alerts", response_model=AlertsResponse, tags=["alerts"])
async def list_alerts(
    request: Request,
    _token: str = Depends(verify_api_key),
) -> AlertsResponse:
    """Journal des demandes d'intervention émises depuis le démarrage."""

    records = request.app.state.journal.all()
    return AlertsResponse(count=len(records), alerts=records)


@router.get("/laravel/interventions", tags=["laravel"])
async def laravel_inbox(
    request: Request,
    _token: str = Depends(verify_api_key),
) -> dict:
    """Boîte de réception côté backend (proxy lecture vers Laravel/mock)."""

    settings = request.app.state.settings
    result = await request.app.state.laravel_client.fetch_interventions()
    return {
        "mode": "simulated" if settings.simulate_laravel else "real",
        **result,
    }


__all__ = ["router", "_orchestrator", "_settings", "ApiError"]

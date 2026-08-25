"""Routes v1 de GMAO-API."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from gmao_api.api.auth import verify_api_key
from gmao_api.exceptions import ApiError
from gmao_api.models.schemas import (
    HealthResponse,
    PredictionsRequest,
    PredictionsResponse,
    SimulateRequest,
)
from gmao_api.services.simulator import generate_batch

logger = logging.getLogger("gmao_api.routes")

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz(request: Request) -> HealthResponse:
    """Sonde de disponibilité (non authentifiée)."""

    ml_ok = await request.app.state.ml_client.health()
    return HealthResponse(
        status="ok" if ml_ok else "degraded",
        service="gmao-api",
        version=request.app.state.version,
        ml_api_reachable=ml_ok,
    )


@router.post("/predictions", response_model=PredictionsResponse, tags=["predictions"])
async def create_predictions(
    payload: PredictionsRequest,
    request: Request,
    _token: str = Depends(verify_api_key),
) -> PredictionsResponse:
    """Relevés réels → prédiction ML."""

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
    result = await request.app.state.orchestrator.process(readings)
    result.readings = readings_raw
    return result


__all__ = ["router", "ApiError"]

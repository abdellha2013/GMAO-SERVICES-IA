"""Health endpoint (no authentication required)."""
from __future__ import annotations

from fastapi import APIRouter

from gmao_ml.api.deps import _container
from gmao_ml.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness/readiness probe: reports whether a model is loaded."""
    predictor = _container.predictor

    return HealthResponse(
        status="ok",
        service="gmao-ml",
        model_loaded=predictor is not None and predictor.is_loaded,
        model_name=predictor.metadata["name"] if predictor is not None and predictor.is_loaded else None,
        model_version=predictor.version if predictor is not None else None,
    )

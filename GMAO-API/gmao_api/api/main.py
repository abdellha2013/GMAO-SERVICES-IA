"""Application FastAPI GMAO-API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import gmao_api
from gmao_api.config import Settings, load_settings
from gmao_api.exceptions import ApiError
from gmao_api.services.equipment_service import EquipmentService
from gmao_api.services.journal import AlertJournal
from gmao_api.services.laravel_client import LaravelClient
from gmao_api.services.ml_client import MlClient
from gmao_api.services.orchestrator import PredictionOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("gmao_api.main")


def create_app(
    settings: Settings | None = None,
    *,
    ml_transport=None,
    laravel_transport=None,
) -> FastAPI:
    """Fabrique l'application (injection de settings/transports pour les tests)."""

    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.version = gmao_api.__version__
        app.state.reading_model = _reading_model_cls()

        # ── Connexion MySQL (table equipements) ──────────────────
        db_engine: AsyncEngine | None = None
        if resolved_settings.equipements_db_url:
            db_engine = create_async_engine(
                resolved_settings.equipements_db_url,
                pool_pre_ping=True,
                pool_recycle=300,
            )
            logger.info("Connexion MySQL configurée : %s", resolved_settings.equipements_db_url.split("@")[-1])

        app.state.equipment_service = EquipmentService(engine=db_engine)

        app.state.ml_client = MlClient(resolved_settings, transport=ml_transport)
        app.state.laravel_client = LaravelClient(resolved_settings, transport=laravel_transport)
        app.state.journal = AlertJournal()
        app.state.orchestrator = PredictionOrchestrator(
            settings=resolved_settings,
            ml_client=app.state.ml_client,
            laravel_client=app.state.laravel_client,
            journal=app.state.journal,
            equipment_service=app.state.equipment_service,
        )
        logger.info(
            "GMAO-API prête — ML=%s | Laravel mode=%s | equipements=%s",
            resolved_settings.ml_api_url,
            "simulated" if resolved_settings.simulate_laravel else "real",
            "MySQL" if db_engine else "catalogue Python",
        )
        yield
        await app.state.equipment_service.close()
        await app.state.ml_client.aclose()
        await app.state.laravel_client.aclose()

    app = FastAPI(
        title="GMAO-API — passerelle IA ↔ Laravel",
        description=(
            "API externe du workspace GMAO : reçoit des relevés capteurs, "
            "interroge le modèle prédictif (GMAO-ML) et pousse une demande "
            "d'intervention vers le backend Laravel lorsque la panne est prédite."
        ),
        version=gmao_api.__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from gmao_api.api.v1.routes import router as v1_router

    app.include_router(v1_router, prefix="/api/v1")

    # ── Dashboard (page unique servie sur "/") ────────────────────
    index_html = Path(__file__).resolve().parents[2] / "static" / "index.html"

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(index_html, media_type="text/html")

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        logger.warning("ApiError %s : %s", exc.error_code, exc.message)
        return JSONResponse(status_code=exc.http_status, content=exc.to_body())

    return app


def _reading_model_cls():
    from gmao_api.models.schemas import SensorReading

    return SensorReading


app = create_app()


__all__ = ["create_app", "app"]

"""Application FastAPI GMAO-ANALYTICS."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import gmao_analytics
from gmao_analytics.config import Settings, load_settings
from gmao_analytics.db import MaintenanceSource
from gmao_analytics.services.analytics import AnalyticsService
from gmao_analytics.services.ml_client import MlEnricher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("gmao_analytics.main")


def create_app(
    settings: Settings | None = None,
    *,
    ml_transport=None,
    source: MaintenanceSource | None = None,
) -> FastAPI:
    """Fabrique l'application (injection settings/transports/source pour les tests)."""

    resolved = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved
        app.state.version = gmao_analytics.__version__

        db_engine: AsyncEngine | None = None
        if resolved.maintenance_db_url and source is None:
            db_engine = create_async_engine(
                resolved.maintenance_db_url,
                pool_pre_ping=True,
                pool_recycle=300,
            )
            logger.info("Connexion MySQL maintenance configurée : %s", resolved.maintenance_db_url.split("@")[-1])

        resolved_source = source or MaintenanceSource(engine=db_engine)
        ml_enricher = MlEnricher(resolved, transport=ml_transport)
        app.state.ml_enricher = ml_enricher
        app.state.analytics = AnalyticsService(source=resolved_source, ml_enrich=ml_enricher.enrich if resolved.ml_api_url else None)

        logger.info(
            "GMAO-ANALYTICS prête — source=%s | ML=%s",
            "MySQL" if db_engine else "catalogue (vide)",
            resolved.ml_api_url,
        )
        yield
        if source is None:
            await resolved_source.close()
        await ml_enricher.aclose()

    app = FastAPI(
        title="GMAO-ANALYTICS — indicateurs de maintenance",
        description=(
            "API du workspace GMAO : calcule les indicateurs MTBF/MTTR/disponibilité "
            "à partir des données de maintenance (MySQL) et produit des rapports, "
            "enrichis des sorties du modèle prédictif (GMAO-ML)."
        ),
        version=gmao_analytics.__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from gmao_analytics.api.v1.routes import router as v1_router

    app.include_router(v1_router, prefix="/api/v1")

    # ── Dashboard de visualisation (page statique sur "/") ──────
    index_html = Path(__file__).resolve().parents[2] / "static" / "index.html"

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(index_html, media_type="text/html")

    return app


app = create_app()


__all__ = ["create_app", "app"]

"""Point d'entrée FastAPI de GMAO-OCR.

``create_app`` reçoit les dépendances (settings, client Laravel, service d'OCR)
avec des valeurs par défaut, ce qui permet des tests purs sans I/O réel.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import gmao_ocr
from gmao_ocr.config import Settings, PROJECT_ROOT, load_settings
from gmao_ocr.qr.decoder import HAVE_CV2, HAVE_PYZBAR
from gmao_ocr.services.equipement_client import LaravelEquipementClient
from gmao_ocr.services.ocr_service import OcrService

logger = logging.getLogger("gmao_ocr.main")

load_dotenv(PROJECT_ROOT / ".env", override=False)

WEB_DIR = PROJECT_ROOT / "static"


def _build_laravel_client(settings: Settings) -> LaravelEquipementClient | None:
    if not settings.laravel_api_url:
        return None
    try:
        return LaravelEquipementClient(
            base_url=settings.laravel_api_url,
            timeout_s=settings.laravel_timeout_s,
        )
    except ValueError:
        return None


def create_app(
    settings: Settings | None = None,
    laravel_client: LaravelEquipementClient | None = None,
    ocr_service: OcrService | None = None,
) -> FastAPI:
    """Construit l'application FastAPI de GMAO-OCR.

    Parameters
    ----------
    settings:
        Configuration. Défaut : chargée depuis l'environnement/``.env``.
    laravel_client:
        Client Laravel à injecter (tests). Défaut : construit depuis settings.
    ocr_service:
        Service d'OCR à injecter (tests). Défaut : bâti ici.
    """

    settings = settings or load_settings()
    if laravel_client is None:
        laravel_client = _build_laravel_client(settings)
    ocr_service = ocr_service or OcrService(
        settings=settings,
        laravel_client=laravel_client,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        decoder = "pyzbar" if HAVE_PYZBAR else ("opencv" if HAVE_CV2 else "none")
        logger.info(
            "GMAO-OCR prête — décodeur=%s | laravel=%s",
            decoder,
            bool(settings.laravel_api_url),
        )
        yield
        if laravel_client is not None:
            await laravel_client.aclose()

    app = FastAPI(
        title="GMAO-OCR",
        description=(
            "Vision par ordinateur : lecture des QR codes d'équipements à partir "
            "d'une simple photo (décodage pyzbar/OpenCV, validation anti-phishing "
            "du format d'URL, enrichissement via l'API Laravel)."
        ),
        version=gmao_ocr.__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.version = gmao_ocr.__version__
    app.state.ocr_service = ocr_service

    from gmao_ocr.api.v1.routes import router as v1_router

    app.include_router(v1_router, prefix="/api/v1")

    # ── Interface web de visualisation ─────────────────────────
    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

    return app


app = create_app()

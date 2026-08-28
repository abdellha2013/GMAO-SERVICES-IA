"""Fixtures partagées des tests unitaires GMAO-OCR."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from gmao_ocr.config import Settings
from gmao_ocr.services.equipement_client import (
    EquipementNotFoundError,
    EquipementUnavailableError,
)
from gmao_ocr.services.ocr_service import OcrService

ASSETS_DIR = Path(__file__).parent / "assets"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        laravel_api_url="",  # pas d'enrichissement par défaut dans les tests
        allowed_hosts=[],
    )


@pytest.fixture
def qr_png() -> bytes:
    return (ASSETS_DIR / "qr_test.png").read_bytes()


@pytest.fixture
def qr_rotated_png() -> bytes:
    return (ASSETS_DIR / "qr_test_rotated.png").read_bytes()


@pytest.fixture
def qr_svg() -> bytes:
    """QR SVG réel (path vectoriel), décode le même contenu que le PNG."""

    return (ASSETS_DIR / "qr_test_equipement.svg").read_bytes()


@pytest.fixture
def qr_eps() -> bytes:
    """Version EPS du QR de test (raster Pillow + Ghostscript)."""

    from PIL import Image

    img = Image.open(ASSETS_DIR / "qr_test.png").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="EPS")
    return buf.getvalue()


class OkClient:
    """Mock Laravel : renvoie une fiche équipement."""

    async def fetch_equipement(self, equipement_id: int) -> dict:
        return {"id": equipement_id, "nom": "Pompe Centrifuge P-101", "site": "Sfax"}


class NotFoundClient:
    """Mock Laravel : équipement inexistant."""

    async def fetch_equipement(self, equipement_id: int) -> dict:
        raise EquipementNotFoundError(equipement_id)


class UnavailableClient:
    """Mock Laravel : API injoignable."""

    async def fetch_equipement(self, equipement_id: int) -> dict:
        raise EquipementUnavailableError("API injoignable")


@pytest.fixture
def ocr_service(settings: Settings) -> OcrService:
    return OcrService(settings)


@pytest.fixture
def ocr_service_ok(settings: Settings) -> OcrService:
    return OcrService(settings, OkClient())


@pytest.fixture
def ocr_service_notfound(settings: Settings) -> OcrService:
    return OcrService(settings, NotFoundClient())


@pytest.fixture
def ocr_service_unavailable(settings: Settings) -> OcrService:
    return OcrService(settings, UnavailableClient())

"""Tests HTTP de l'endpoint POST /api/v1/qr/scan et GET /api/v1/healthz."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gmao_ocr.api.main import create_app
from gmao_ocr.config import Settings

VALID = "https://mondomaine.com/api/equipements/5"


def _client(ocr_service) -> TestClient:
    settings = Settings(laravel_api_url="https://mondomaine.com", allowed_hosts=[])
    app = create_app(settings=settings, ocr_service=ocr_service)
    return TestClient(app)


def test_healthz(ocr_service):
    c = _client(ocr_service)
    r = c.get("/api/v1/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "gmao-ocr"
    assert body["version"] == "0.1.0"
    assert body["decoder"] in ("opencv", "pyzbar", "none")
    assert "laravel_configured" in body


def test_scan_success_with_enrichment(ocr_service_ok, qr_png):
    c = _client(ocr_service_ok)
    r = c.post("/api/v1/qr/scan", files={"file": ("qr.png", qr_png, "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["id_equipement"] == 5
    assert body["lien_equipement"] == VALID
    assert body["equipement"]["id"] == 5
    assert body["equipement"]["nom"] == "Pompe Centrifuge P-101"


def test_scan_success_without_laravel(ocr_service, qr_png):
    c = _client(ocr_service)
    r = c.post("/api/v1/qr/scan", files={"file": ("qr.png", qr_png, "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["equipement_details_indisponibles"] is True
    assert "equipement" not in body


def test_scan_equipement_not_found(ocr_service_notfound, qr_png):
    c = _client(ocr_service_notfound)
    r = c.post("/api/v1/qr/scan", files={"file": ("qr.png", qr_png, "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["error"] == "Équipement introuvable"


def test_scan_laravel_unavailable_keeps_success(ocr_service_unavailable, qr_png):
    c = _client(ocr_service_unavailable)
    r = c.post("/api/v1/qr/scan", files={"file": ("qr.png", qr_png, "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["equipement_details_indisponibles"] is True


def test_scan_no_qr(ocr_service):
    c = _client(ocr_service)
    r = c.post("/api/v1/qr/scan", files={"file": ("bad.png", b"not-a-real-image", "image/png")})
    assert r.status_code == 200
    assert r.json()["success"] is False


def test_scan_unsupported_content_type(ocr_service):
    c = _client(ocr_service)
    r = c.post("/api/v1/qr/scan", files={"file": ("doc.gif", b"GIF89a", "image/gif")})
    assert r.status_code == 415


def test_scan_svg_success(ocr_service, qr_svg):
    c = _client(ocr_service)
    r = c.post("/api/v1/qr/scan", files={"file": ("qr.svg", qr_svg, "image/svg+xml")})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["id_equipement"] == 1
    assert body["lien_equipement"] == "http://localhost:8001/api/equipements/1"


def test_scan_eps_success(ocr_service, qr_eps):
    c = _client(ocr_service)
    r = c.post(
        "/api/v1/qr/scan",
        files={"file": ("qr.eps", qr_eps, "application/postscript")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["id_equipement"] == 5


def test_debug_raster_svg(ocr_service, qr_svg):
    c = _client(ocr_service)
    r = c.post("/api/v1/debug/raster", files={"file": ("qr.svg", qr_svg, "image/svg+xml")})
    assert r.status_code == 200
    body = r.json()
    assert body["source_format"] == "svg"
    assert body["taille"]["largeur"] > 0
    import base64

    png = base64.b64decode(body["png_base64"])
    assert png.startswith(b"\x89PNG")


def test_debug_raster_rejects_gif(ocr_service):
    c = _client(ocr_service)
    r = c.post("/api/v1/debug/raster", files={"file": ("doc.gif", b"GIF89a", "image/gif")})
    assert r.status_code == 415


def test_debug_sample_svg(ocr_service):
    from gmao_ocr.config import PROJECT_ROOT

    c = _client(ocr_service)
    r = c.get("/api/v1/debug/sample-svg")
    if (PROJECT_ROOT.parent / "qr_equipement.svg").exists():
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/svg+xml"
    else:
        assert r.status_code == 404


def test_scan_missing_file_field(ocr_service):
    c = _client(ocr_service)
    r = c.post("/api/v1/qr/scan", files={})
    assert r.status_code in (400, 422)

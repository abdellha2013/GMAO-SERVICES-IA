"""Routes v1 de GMAO-OCR."""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from gmao_ocr.models.schemas import HealthResponse, ScanResponse
from gmao_ocr.qr.decoder import (
    HAVE_CV2,
    HAVE_PYZBAR,
    decode_qr_from_bytes,
    render_to_png_bytes,
)

logger = logging.getLogger("gmao_ocr.routes")

router = APIRouter()


def _decoder_name() -> str:
    if HAVE_PYZBAR:
        return "pyzbar"
    if HAVE_CV2:
        return "opencv"
    return "none"


@router.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz(request: Request) -> HealthResponse:
    """État du service + moteur de décodage actif."""

    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service="gmao-ocr",
        version=request.app.state.version,
        decoder=_decoder_name(),
        laravel_configured=settings.laravel_api_url != "",
    )


@router.post(
    "/qr/scan",
    response_model=ScanResponse,
    response_model_exclude_none=True,
    tags=["qr"],
    summary="Scanner un QR code équipement à partir d'une photo",
    description=(
        "Reçoit une photo (JPEG/PNG/SVG/EPS) d'un QR code collé sur une machine, décode "
        "l'URL de la fiche équipement, valide son format (`/api/equipements/{id}`) "
        "pour éviter tout QR arbitraire (anti-phishing) puis renvoie l'id et, si "
        "l'API Laravel est joignable, la fiche équipement détaillée.\n\n"
        "Cas d'échec (toujours `success=false` avec un message clair) : image sans "
        "QR détectable, image floue/mal cadrée, URL dont le format est inattendu, "
        "équipement introuvable (404 Laravel). Si l'appel Laravel échoue en "
        "timeout/réseau, le lien brut est conservé avec "
        "`equipement_details_indisponibles: true`."
    ),
)
async def scan_qr(
    request: Request,
    file: UploadFile = File(..., description="Image JPEG/PNG/SVG/EPS contenant le QR code."),
) -> Response:
    """Décode un QR code depuis une photo et renvoie la fiche équipement."""

    settings = request.app.state.settings

    # ── Vérifications protocole (fichier) ──────────────────────────
    content_type = (file.content_type or "").lower()
    if content_type not in settings.accepted_content_types:
        raise HTTPException(
            status_code=415,
            detail=f"Format non pris en charge : {content_type} (JPEG/PNG/SVG/EPS attendu).",
        )

    image_bytes = await file.read()
    if len(image_bytes) > settings.max_image_bytes:
        raise HTTPException(
            status_code=413,
            detail="Image trop volumineuse (limite "
            f"{settings.max_image_bytes // (1024 * 1024)} Mo).",
        )
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Fichier image vide.")

    # ── Délégation à la couche métier ──────────────────────────────
    outcome = await request.app.state.ocr_service.scan(
        image_bytes=image_bytes,
        content_type=content_type,
    )

    payload = ScanResponse(
        success=outcome.success,
        id_equipement=outcome.equipement_id,
        lien_equipement=outcome.lien_equipement,
        equipement=outcome.equipement,
        equipement_details_indisponibles=outcome.equipement_details_indisponibles,
        error=outcome.error,
        method=outcome.method,
    )

    # Les échecs d'analyse sont des réponses métier (200 + success=false).
    return Response(
        content=payload.model_dump_json(exclude_none=True),
        status_code=200,
        media_type="application/json",
    )


@router.post("/debug/raster", tags=["debug"])
async def debug_raster(
    request: Request,
    file: UploadFile = File(..., description="Fichier image SVG/PNG/EPS/JPEG."),
) -> dict:
    """Aperçu du travail de préprocessing : rasterise le fichier en PNG et
    renvoie l'image (base64) + métadonnées pour la visualisation web."""

    settings = request.app.state.settings

    content_type = (file.content_type or "").lower()
    if content_type not in settings.accepted_content_types:
        raise HTTPException(status_code=415, detail=f"Format non pris en charge : {content_type}")

    image_bytes = await file.read()
    if len(image_bytes) > settings.max_image_bytes:
        raise HTTPException(
            status_code=413,
            detail="Image trop volumineuse (limite "
            f"{settings.max_image_bytes // (1024 * 1024)} Mo).",
        )
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Fichier image vide.")

    try:
        png_bytes, source, size = render_to_png_bytes(image_bytes, content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = decode_qr_from_bytes(
        image_bytes,
        attempts=settings.decode_attempts,
        content_type=content_type,
    )

    return {
        "source_format": source,
        "content_type": content_type,
        "taille": {"largeur": size[0], "hauteur": size[1]},
        "png_base64": base64.b64encode(png_bytes).decode("ascii"),
        "decode_apercu": {
            "data": result.data,
            "method": result.method,
            "attempts": result.attempts,
        },
        "decoders": {"pyzbar": HAVE_PYZBAR, "opencv": HAVE_CV2},
    }


@router.get("/debug/sample-svg", tags=["debug"])
async def debug_sample_svg() -> Response:
    """Renvoie le QR SVG d'exemple du dépôt racine (test rapide)."""

    from gmao_ocr.config import PROJECT_ROOT

    sample = PROJECT_ROOT.parent / "qr_equipement.svg"
    if not sample.exists():
        raise HTTPException(status_code=404, detail="SVG d'exemple introuvable.")

    return Response(
        content=sample.read_bytes(),
        status_code=200,
        media_type="image/svg+xml",
        headers={"Content-Disposition": 'inline; filename="qr_equipement.svg"'},
    )


__all__ = ["router"]

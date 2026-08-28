"""Schémas Pydantic des requêtes/réponses de GMAO-OCR."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ConfigDict

__all__ = ["ScanResponse", "HealthResponse"]


class ScanResponse(BaseModel):
    """Réponse normalisée du scan d'un QR code équipement."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    id_equipement: int | None = None
    lien_equipement: str | None = Field(
        None, description="URL complète de la fiche équipement encodée dans le QR."
    )
    equipement: dict[str, Any] | None = Field(
        None, description="Fiche équipement renvoyée par l'API Laravel (si joignable)."
    )
    equipement_details_indisponibles: bool | None = Field(
        None, description="true si l'enrichissement Laravel a échoué (lien brut conservé)."
    )
    error: str | None = Field(None, description="Message d'erreur (si success=false).")
    method: str = Field(
        "none", description="Moteur de décodage utilisé (pyzbar|opencv|none)."
    )


class HealthResponse(BaseModel):
    """État du service + moteur de décodage actif."""

    status: str = "ok"
    service: str = "gmao-ocr"
    version: str
    decoder: str  # "pyzbar" | "opencv" | "none"
    laravel_configured: bool = False

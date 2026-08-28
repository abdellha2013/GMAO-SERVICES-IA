"""Service d'orchestration du scan QR.

Enchaîne : décodage → validation anti-phishing → extraction id → enrichissement
Laravel (tolérant). Produit une :class:`ScanOutcome` typée utilisée par la route.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from gmao_ocr.config import Settings
from gmao_ocr.qr.decoder import decode_qr_from_bytes
from gmao_ocr.qr.validation import validate_qr_url
from gmao_ocr.services.equipement_client import (
    EquipementNotFoundError,
    EquipementUnavailableError,
    LaravelEquipementClient,
)

logger = logging.getLogger("gmao_ocr.service")


@dataclass
class ScanOutcome:
    """Résultat normalisé d'un scan QR."""

    success: bool
    equipement_id: int | None = None
    lien_equipement: str | None = None
    equipement: dict | None = None
    equipement_details_indisponibles: bool | None = None
    error: str | None = None
    method: str = "none"


class OcrService:
    """Orchestre le scan d'une photo de QR code jusqu'à la fiche équipement."""

    def __init__(
        self,
        settings: Settings,
        laravel_client: LaravelEquipementClient | None = None,
    ) -> None:
        self._settings = settings
        self._laravel = laravel_client

    async def scan(
        self,
        image_bytes: bytes,
        content_type: str | None = None,
    ) -> ScanOutcome:
        """Traite l'image d'une photo contenant un QR code.

        Returns
        -------
        ScanOutcome
            Succès (avec fiche équipement) ou échec (avec message clair).
        """

        if content_type and content_type not in self._settings.accepted_content_types:
            return ScanOutcome(
                success=False,
                error=f"Format non pris en charge : {content_type}",
            )

        # 1) Décodage (pyzbar puis OpenCV, multi-rotations)
        try:
            result = decode_qr_from_bytes(
                image_bytes,
                attempts=self._settings.decode_attempts,
                content_type=content_type,
            )
        except ValueError as exc:
            return ScanOutcome(success=False, error=str(exc))
        except RuntimeError as exc:  # pragma: no cover - aucun décodeur dispo
            return ScanOutcome(success=False, error=str(exc))

        if result.data is None:
            return ScanOutcome(
                success=False,
                error="Aucun QR code détecté dans l'image",
                method=result.method,
            )

        # 2) Validation anti-phishing + extraction id
        equipement_id = validate_qr_url(result.data, self._settings.allowed_hosts)
        if equipement_id is None:
            return ScanOutcome(
                success=False,
                error="URL non reconnue",
                method=result.method,
            )

        lien = result.data.strip()
        outcome = ScanOutcome(
            success=True,
            equipement_id=equipement_id,
            lien_equipement=lien,
            method=result.method,
        )

        # 3) Enrichissement Laravel (optionnel, tolérant)
        if self._laravel is None:
            outcome.equipement_details_indisponibles = True
            return outcome

        try:
            outcome.equipement = await self._laravel.fetch_equipement(equipement_id)
        except EquipementNotFoundError:
            return ScanOutcome(
                success=False,
                error="Équipement introuvable",
                method=result.method,
            )
        except EquipementUnavailableError as exc:
            logger.warning("Détails équipement indisponibles : %s", exc)
            outcome.equipement_details_indisponibles = True

        return outcome


__all__ = ["OcrService", "ScanOutcome"]

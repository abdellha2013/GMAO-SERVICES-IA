"""Configuration GMAO-OCR chargée depuis ``.env``.

Calquée sur le pattern des autres services du monorepo : les chemins et
valeurs sont résolus depuis l'environnement / ``.env`` du sous-projet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    """Paramètres runtime de GMAO-OCR."""

    # ── API elle-même ─────────────────────────────────────────────
    api_host: str = "127.0.0.1"
    api_port: int = 8400

    # ── API Laravel (fiche équipement) — enrichissement tolérant ──
    # Base de l'API Laravel, ex. "https://mondomaine.com".
    # Si vide, l'appel d'enrichissement est désactivé (lien brut seulement).
    laravel_api_url: str = ""

    # Timeout (secondes) de l'appel vers Laravel.
    laravel_timeout_s: float = 5.0

    # ── Validation anti-phishing de l'URL encodée dans le QR ──────
    # Hôtes autorisés (virgule). Vide = tout hôte valide HTTPS/HTTP accepté
    # (le chemin /api/equipements/{id} reste exigé). Ex. "mondomaine.com".
    qr_allowed_hosts: str = ""

    # ── Sécurité du fichier image reçu ─────────────────────────────
    max_image_bytes: int = 10 * 1024 * 1024  # 10 Mo
    accepted_content_types: tuple[str, ...] = ("image/jpeg", "image/png", "image/svg+xml", "application/postscript")

    # ── Décodage OCR ───────────────────────────────────────────────
    # Augmente le nombre d'essais en cas de multimodalité (rotation,
    # mise à l'échelle) pour les photos un peu floues / mal cadrées.
    decode_attempts: int = 2

    # Hôtes autorisés, listés.
    allowed_hosts: list[str] = field(default_factory=list)


def load_settings() -> Settings:
    """Construit les :class:`Settings` depuis l'environnement / le ``.env``."""

    allowed = os.getenv("QR_ALLOWED_HOSTS", "")
    host_list = [h.strip() for h in allowed.split(",") if h.strip()]

    return Settings(
        api_host=os.getenv("OCR_HOST", "127.0.0.1"),
        api_port=int(os.getenv("OCR_PORT", "8400")),
        laravel_api_url=os.getenv("LARAVEL_API_URL", "").rstrip("/"),
        laravel_timeout_s=float(os.getenv("LARAVEL_TIMEOUT_S", "5.0")),
        qr_allowed_hosts=os.getenv("QR_ALLOWED_HOSTS", ""),
        max_image_bytes=int(os.getenv("OCR_MAX_IMAGE_BYTES", str(10 * 1024 * 1024))),
        accepted_content_types=(
            os.getenv("OCR_ACCEPTED_CONTENT_TYPES", "image/jpeg,image/png,image/svg+xml,application/postscript")
            .split(",")
        ),
        decode_attempts=int(os.getenv("OCR_DECODE_ATTEMPTS", "2")),
        allowed_hosts=host_list,
    )


__all__ = ["Settings", "load_settings", "PROJECT_ROOT"]

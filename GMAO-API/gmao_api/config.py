"""Configuration GMAO-API chargée depuis ``.env``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    """Paramètres runtime de la passerelle."""

    # ── API elle-même ──────────────────────────────
    api_port: int = 8200

    # ── Modèle ML (GMAO-ML) ───────────────────────
    ml_api_url: str = "http://127.0.0.1:8100"
    ml_timeout_s: float = 10.0
    ml_retries: int = 2

    # ── Base de données (lecture table equipements) ──────────────
    equipements_db_url: str | None = None

    # ── Règle d'alerte ────────────────────────────
    critical_probability: float = 0.90


def load_settings() -> Settings:
    """Construit les :class:`Settings` depuis l'environnement / le ``.env``."""

    return Settings(
        api_port=int(os.getenv("API_PORT", "8200")),
        ml_api_url=os.getenv("ML_API_URL", "http://127.0.0.1:8100").rstrip("/"),
        ml_timeout_s=float(os.getenv("ML_TIMEOUT_S", "10")),
        ml_retries=int(os.getenv("ML_RETRIES", "2")),
        equipements_db_url=os.getenv("EQUIPEMENTS_DB_URL") or None,
        critical_probability=float(os.getenv("CRITICAL_PROBABILITY", "0.90")),
    )


__all__ = ["Settings", "load_settings", "PROJECT_ROOT"]

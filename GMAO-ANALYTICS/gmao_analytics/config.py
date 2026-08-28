"""Configuration GMAO-ANALYTICS chargée depuis ``.env``.

Calquée sur le pattern de ``gmao_api.config`` : les chemins et valeurs
sont résolus depuis l'environnement / le ``.env`` du sous-projet, avec
des défauts raisonnables pour le développement local.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    """Paramètres runtime de GMAO-ANALYTICS."""

    # ── API elle-même ──────────────────────────────────────────
    api_host: str = "127.0.0.1"
    api_port: int = 8300

    # ── Base de données MySQL (tables de maintenance, lecture seule) ─
    maintenance_db_url: str | None = None

    # ── Modèle prédictif (GMAO-ML) — enrichissement tolérant ──
    ml_api_url: str = "http://127.0.0.1:8100"
    ml_timeout_s: float = 5.0
    ml_retries: int = 1

    # ── Référentiel équipements (fallback si MySQL indisponible) ─
    catalog_equipements: bool = True


def load_settings() -> Settings:
    """Construit les :class:`Settings` depuis l'environnement / le ``.env``."""

    return Settings(
        api_host=os.getenv("ANALYTICS_HOST", "127.0.0.1"),
        api_port=int(os.getenv("ANALYTICS_PORT", "8300")),
        maintenance_db_url=os.getenv("MAINTENANCE_DB_URL") or None,
        ml_api_url=os.getenv("ML_API_URL", "http://127.0.0.1:8100").rstrip("/"),
        ml_timeout_s=float(os.getenv("ML_TIMEOUT_S", "5.0")),
        ml_retries=int(os.getenv("ML_RETRIES", "1")),
        catalog_equipements=os.getenv("CATALOG_EQUIPEMENTS", "true").lower() != "false",
    )


__all__ = ["Settings", "load_settings", "PROJECT_ROOT"]

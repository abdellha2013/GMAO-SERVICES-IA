"""Configuration GMAO-API chargée depuis ``.env``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Paramètres runtime de la passerelle."""

    # ── API elle-même ──────────────────────────────
    api_key: str = "gmao-api-dev-key"
    api_port: int = 8200

    # ── Modèle ML (GMAO-ML) ───────────────────────
    ml_api_url: str = "http://127.0.0.1:8100"
    ml_api_key: str = "gmao-ml-dev-key"
    ml_timeout_s: float = 10.0
    ml_retries: int = 2

    # ── Backend Laravel ────────────────────────────
    simulate_laravel: bool = True
    laravel_api_url: str = "http://127.0.0.1:9000"
    laravel_alerts_path: str = "/api/intervention-requests"
    laravel_api_token: str | None = None
    laravel_ia_user_id: int = 1

    # ── Base de données (lecture table equipements) ──────────────
    equipements_db_url: str | None = None

    # ── Règle d'alerte ────────────────────────────
    critical_probability: float = 0.90


def load_settings() -> Settings:
    """Construit les :class:`Settings` depuis l'environnement / le ``.env``."""

    return Settings(
        api_key=os.getenv("GMAO_API_KEY", "gmao-api-dev-key"),
        api_port=int(os.getenv("API_PORT", "8200")),
        ml_api_url=os.getenv("ML_API_URL", "http://127.0.0.1:8100").rstrip("/"),
        ml_api_key=os.getenv("ML_API_KEY", "gmao-ml-dev-key"),
        ml_timeout_s=float(os.getenv("ML_TIMEOUT_S", "10")),
        ml_retries=int(os.getenv("ML_RETRIES", "2")),
        simulate_laravel=_env_bool("SIMULATE_LARAVEL", True),
        laravel_api_url=os.getenv("LARAVEL_API_URL", "http://127.0.0.1:9000").rstrip("/"),
        laravel_alerts_path=os.getenv("LARAVEL_ALERTS_PATH", "/api/intervention-requests"),
        laravel_api_token=os.getenv("LARAVEL_API_TOKEN") or None,
        laravel_ia_user_id=int(os.getenv("LARAVEL_IA_USER_ID", "1")),
        equipements_db_url=os.getenv("EQUIPEMENTS_DB_URL") or None,
        critical_probability=float(os.getenv("CRITICAL_PROBABILITY", "0.90")),
    )


__all__ = ["Settings", "load_settings", "PROJECT_ROOT"]

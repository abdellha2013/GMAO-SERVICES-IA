"""
gmao_ml/config.py
=================

Configuration centralisée du sous-projet GMAO-ML.

Les valeurs sont lues depuis les variables d'environnement (fichier
``.env`` du sous-projet supporté via ``python-dotenv``) avec des
défauts raisonnables pour le développement local.

Les chemins relatifs sont résolus par rapport à la racine du
sous-projet ``GMAO-ML/`` (et non par rapport au répertoire courant),
afin que le comportement soit identique quel que soit le CWD.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

__all__ = ["Settings", "PROJECT_ROOT", "load_settings"]

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]

_DEFAULT_MODEL_DIR = "artifacts"
_DEFAULT_MLFLOW_DIR = "mlruns"


@dataclass(frozen=True, slots=True)
class Settings:
    """Paramètres de configuration de GMAO-ML.

    Attributes
    ----------
    api_key:
        Clé API pour protéger les endpoints (auth Bearer).
        ``None`` → authentification désactivée (mode dev).

    api_host / api_port:
        Interface et port d'écoute du service de prédiction.

    model_dir:
        Répertoire des artefacts sérialisés (hors repo).

    model_name:
        Nom logique du modèle (sous-répertoire de ``model_dir``).

    model_version:
        Version à charger : ``"latest"`` ou un identifiant exact.

    mlflow_tracking_uri:
        URI du serveur/backend MLflow (``file://…``, ``http://…``).

    mlflow_experiment_name:
        Nom de l'expérience MLflow.

    target_column:
        Colonne cible dans les CSV d'entraînement.

    test_size / random_state:
        Paramètres de découpage train/test reproductible.
    """

    api_host: str
    api_port: int

    model_dir: Path
    model_name: str
    model_version: str

    mlflow_tracking_uri: str
    mlflow_experiment_name: str

    target_column: str
    test_size: float
    random_state: int


def _resolve_path(raw: str) -> Path:
    """Résout un chemin relatif par rapport à la racine du sous-projet."""

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _resolve_tracking_uri(raw: str) -> str:
    """Normalise l'URI MLflow.

    Les schémas explicites (``http(s)://``, ``file://``, ``sqlite://``…)
    sont conservés tels quels ; une valeur sans schéma est interprétée
    comme un chemin local relatif au sous-projet et convertie en
    ``file://`` absolu (MLflow résout sinon par rapport au CWD).
    """

    for scheme in ("http://", "https://", "file://", "sqlite:", "postgresql:", "mysql:"):
        if raw.startswith(scheme):
            return raw

    return f"file://{_resolve_path(raw)}"


def load_settings() -> Settings:
    """Charge la configuration depuis l'environnement (+ ``GMAO-ML/.env``).

    Returns
    -------
    Settings
        Configuration immuable prête à l'emploi.
    """

    load_dotenv(PROJECT_ROOT / ".env", override=False)

    return Settings(
        api_host=os.getenv("ML_API_HOST", "127.0.0.1"),
        api_port=int(os.getenv("ML_API_PORT", "8100")),

        model_dir=_resolve_path(os.getenv("MODEL_DIR", _DEFAULT_MODEL_DIR)),
        model_name=os.getenv("MODEL_NAME", "gmao_state_classifier"),
        model_version=os.getenv("MODEL_VERSION", "latest"),

        mlflow_tracking_uri=_resolve_tracking_uri(
            os.getenv("MLFLOW_TRACKING_URI", _DEFAULT_MLFLOW_DIR)
        ),
        mlflow_experiment_name=os.getenv(
            "MLFLOW_EXPERIMENT_NAME", "gmao-ml-etat-machines"
        ),

        target_column=os.getenv("ML_TARGET_COLUMN", "gravite"),
        test_size=float(os.getenv("ML_TEST_SIZE", "0.2")),
        random_state=int(os.getenv("ML_RANDOM_STATE", "42")),
    )

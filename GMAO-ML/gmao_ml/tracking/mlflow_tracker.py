"""
gmao_ml/tracking/mlflow_tracker.py
==================================

Wrapper léger autour de MLflow.

Rôle :

- fixer l'URI de tracking et l'expérience une seule fois ;
- exposer une API minimale (runs, params, metrics, artefacts).

Le tracker est volontairement **non critique** : si MLflow devient
indisponible, l'orchestrateur d'entraînement doit pouvoir continuer
(le modèle reste sérialisé localement). C'est lui qui désactive le
tracking après la première erreur, pas ce module.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import mlflow

from gmao_ml.exceptions import TrackingError

__all__ = ["MlflowTracker"]

logger = logging.getLogger("gmao_ml.tracking")


class MlflowTracker:
    """Encapsule l'accès à MLflow (backend local fichier ou serveur distant).

    Parameters
    ----------
    tracking_uri:
        URI MLflow (``file://…`` par défaut, voir ``config``).

    experiment_name:
        Nom de l'expérience ; créée si absente.
    """

    def __init__(self, tracking_uri: str, experiment_name: str) -> None:
        self._tracking_uri = tracking_uri
        self._experiment_name = experiment_name
        mlflow.set_tracking_uri(tracking_uri)

        try:
            mlflow.set_experiment(experiment_name)
        except Exception as exc:
            raise TrackingError(
                message=f"Unable to initialize MLflow experiment '{experiment_name}'.",
                error_code="MLFLOW_INIT_ERROR",
                details={"tracking_uri": tracking_uri},
                original=exc,
            ) from exc

        logger.info("MLflow ready — uri=%s experiment=%s", tracking_uri, experiment_name)

    @property
    def experiment_name(self) -> str:
        """Nom de l'expérience configurée."""

        return self._experiment_name

    # ==========================================================
    # Run management
    # ==========================================================

    @contextmanager
    def start_run(self, run_name: str) -> Iterator[Any]:
        """Ouvre un run MLflow comme contexte manager.

        Raises
        ------
        TrackingError
            Si le backend MLflow refuse l'ouverture du run.
        """

        try:
            with mlflow.start_run(run_name=run_name) as run:
                yield run
        except TrackingError:
            raise
        except Exception as exc:
            raise TrackingError(
                message=f"MLflow run '{run_name}' failed.",
                error_code="MLFLOW_RUN_ERROR",
                details={"run_name": run_name},
                original=exc,
            ) from exc

    # ==========================================================
    # Logging helpers
    # ==========================================================

    def log_params(self, params: dict[str, Any]) -> None:
        """Journalise les hyperparamètres du run courant."""

        safe = {k: _stringify(v) for k, v in params.items()}
        mlflow.log_params(safe)

    def log_metrics(self, metrics: dict[str, float]) -> None:
        """Journalise les métriques du run courant."""

        mlflow.log_metrics({k: float(v) for k, v in metrics.items()})

    def log_artifact(self, path: str | Any) -> None:
        """Joint un artefact (modèle, métadonnées…) au run courant."""

        mlflow.log_artifact(str(path))


def _stringify(value: Any) -> str:
    """Convertit une valeur en chaîne acceptée par MLflow (≤500 caractères)."""

    text = str(value)
    return text[:500]

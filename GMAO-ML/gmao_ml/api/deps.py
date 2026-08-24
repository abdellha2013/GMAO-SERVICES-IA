"""Dependency injection for FastAPI.

The :class:`~gmao_ml.inference.Predictor` singleton is built once at
startup (model loading is expensive) and exposed to route handlers
through :func:`get_predictor`.

Startup is **tolerant**: if no trained model exists yet the service
still boots (health checks work) and prediction endpoints answer 503
until a first training has been run.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from gmao_ml.config import load_settings
from gmao_ml.exceptions import ModelNotFoundError, ModelSerializationError
from gmao_ml.inference import Predictor

__all__ = ["load_predictor", "get_predictor", "_container"]

logger = logging.getLogger("gmao_ml.api")


# =====================================================================
# Singleton container (populated at startup, read at request time)
# =====================================================================

class _Container:
    """Holds the singleton predictor instance."""

    predictor: Predictor | None = None


_container = _Container()


# =====================================================================
# Startup / per-request accessors
# =====================================================================

def load_predictor() -> Predictor | None:
    """Build the predictor at startup and store it in the container.

    Missing artifacts are tolerated (dev-friendly): the container keeps
    ``None`` and endpoints return 503 until a model is trained.
    """
    settings = load_settings()

    try:
        predictor = Predictor(
            model_dir=settings.model_dir,
            model_name=settings.model_name,
            version=settings.model_version,
        )
        predictor.load()
    except (ModelNotFoundError, ModelSerializationError) as exc:
        logger.warning("No model loaded at startup: %s", exc.message)
        _container.predictor = None
        return None

    _container.predictor = predictor
    return predictor


def get_predictor() -> Any:
    """FastAPI dependency returning the loaded predictor.

    Raises
    ------
    HTTPException
        503 when no model has been trained/loaded yet.
    """
    predictor = _container.predictor

    if predictor is None or not predictor.is_loaded:
        raise HTTPException(
            status_code=503,
            detail=(
                "No model available yet. Run scripts/train.py first "
                "(e.g. `uv run python GMAO-ML/scripts/train.py --data <csv>`)."
            ),
        )

    return predictor

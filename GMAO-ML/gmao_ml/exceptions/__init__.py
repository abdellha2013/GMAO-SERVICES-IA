"""Point d'entrée unique des exceptions du sous-projet GMAO-ML.

Import recommandé::

    from gmao_ml.exceptions import MLError, DatasetValidationError
"""

from __future__ import annotations

from gmao_ml.exceptions.base_exception import MLError
from gmao_ml.exceptions.data import (
    DataError,
    DatasetLoadError,
    DatasetValidationError,
)
from gmao_ml.exceptions.model import (
    InferenceValidationError,
    ModelError,
    ModelNotFoundError,
    ModelNotReadyError,
    ModelSerializationError,
    PredictionError,
)
from gmao_ml.exceptions.tracking import TrackingError
from gmao_ml.exceptions.training import (
    InvalidTrainingStrategyError,
    TrainingError,
    TrainingStrategyNotRegisteredError,
    TrainingValidationError,
)

__all__ = [
    "MLError",
    # --- data ---
    "DataError",
    "DatasetLoadError",
    "DatasetValidationError",
    # --- model / inference ---
    "ModelError",
    "ModelNotFoundError",
    "ModelNotReadyError",
    "ModelSerializationError",
    "PredictionError",
    "InferenceValidationError",
    # --- training ---
    "TrainingError",
    "TrainingValidationError",
    "InvalidTrainingStrategyError",
    "TrainingStrategyNotRegisteredError",
    # --- tracking ---
    "TrackingError",
]

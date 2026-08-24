"""Couche données GMAO-ML (chargement CSV, prétraitement)."""

from __future__ import annotations

from gmao_ml.data.augmentation import (
    AI4IRuleAugmenter,
    compute_power_w,
    machine_failure_from_rules,
)
from gmao_ml.data.feature_engineering import SensorFeatureEngineer
from gmao_ml.data.loader import DatasetLoader
from gmao_ml.data.preprocessing import (
    build_preprocessor,
    detect_column_types,
)

__all__ = [
    "AI4IRuleAugmenter",
    "DatasetLoader",
    "SensorFeatureEngineer",
    "detect_column_types",
    "build_preprocessor",
    "machine_failure_from_rules",
]

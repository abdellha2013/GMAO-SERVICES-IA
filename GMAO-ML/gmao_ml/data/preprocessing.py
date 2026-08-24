"""
gmao_ml/data/preprocessing.py
=============================

Prétraitement sklearn des features.

Le préprocesseur est construit sous forme de ``ColumnTransformer``
inséré dans un ``Pipeline`` avec le classifieur final. Il est donc
**sérialisé avec le modèle** : aucune divergence train/serving
possible (pas de scaler ou d'encodeur sauvegardé séparément).

Détection automatique :

- colonnes numériques → imputation médiane + standardisation ;
- colonnes catégorielles → imputation mode + one-hot encoding
  (catégories inconnues en production ignorées gracieusement).
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from gmao_ml.exceptions import DatasetValidationError

__all__ = ["detect_column_types", "build_preprocessor", "PREPROCESSOR_STEP", "CLASSIFIER_STEP"]

logger = logging.getLogger("gmao_ml.data")

PREPROCESSOR_STEP = "preprocessing"
CLASSIFIER_STEP = "classifier"


def detect_column_types(features: pd.DataFrame) -> dict[str, list[str]]:
    """Sépare les colonnes de features en numériques / catégorielles.

    Parameters
    ----------
    features:
        DataFrame contenant uniquement les colonnes explicatives.

    Returns
    -------
    dict[str, list[str]]
        ``{"numeric": [...], "categorical": [...]}``.

    Raises
    ------
    DatasetValidationError
        Si aucune colonne exploitable n'est détectée.
    """

    numeric = [
        col for col in features.select_dtypes(include="number").columns
        if features[col].notna().any()
    ]
    categorical = [
        col for col in features.columns
        if col not in numeric and features[col].notna().any()
    ]

    if not numeric and not categorical:
        raise DatasetValidationError(
            message="No usable feature column detected (numeric or categorical).",
            error_code="NO_FEATURE_COLUMNS",
            details={"columns": list(features.columns)},
        )

    logger.info(
        "Feature types detected — numeric=%d categorical=%d",
        len(numeric), len(categorical),
    )
    return {"numeric": numeric, "categorical": categorical}


def build_preprocessor(column_types: dict[str, list[str]]) -> ColumnTransformer:
    """Construit le ``ColumnTransformer`` correspondant aux types détectés.

    Parameters
    ----------
    column_types:
        Sortie de :func:`detect_column_types`.

    Returns
    -------
    ColumnTransformer
        Transformateur composite prêt à être inséré dans un Pipeline.
    """

    transformers: list[tuple[str, Any, list[str]]] = []

    if column_types["numeric"]:
        transformers.append((
            "numeric",
            Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]),
            column_types["numeric"],
        ))

    if column_types["categorical"]:
        transformers.append((
            "categorical",
            Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]),
            column_types["categorical"],
        ))

    return ColumnTransformer(transformers=transformers, remainder="drop")

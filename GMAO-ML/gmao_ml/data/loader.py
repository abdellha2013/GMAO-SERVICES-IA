"""
gmao_ml/data/loader.py
======================

Chargement et validation des datasets d'entraînement (CSV).

Contrats vérifiés :

- le fichier existe, est lisible et non vide ;
- la colonne cible est présente ;
- volume minimal atteint pour entraîner sérieusement ;
- colonnes entièrement vides supprimées (avec avertissement) ;
- ratio de valeurs manquantes signalé par colonne.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from gmao_ml.exceptions import DatasetLoadError, DatasetValidationError

__all__ = ["DatasetLoader"]

logger = logging.getLogger("gmao_ml.data")


class DatasetLoader:
    """Charge un CSV d'entraînement et applique les contrôles qualité.

    Parameters
    ----------
    target_column:
        Nom de la colonne cible attendue dans le fichier.

    min_rows:
        Nombre minimal de lignes utiles (défaut : 20).

    exclude_columns:
        Colonnes à retirer du dataset (fuites connues : identifiants,
        sous-labels de défaillance, etc.). Les noms absents sont ignorés.
    """

    def __init__(
        self,
        target_column: str,
        min_rows: int = 20,
        exclude_columns: tuple[str, ...] = (),
    ) -> None:
        self._target_column = target_column
        self._min_rows = min_rows
        self._exclude_columns = tuple(exclude_columns)

    @property
    def target_column(self) -> str:
        """Colonne cible configurée."""

        return self._target_column

    def load_csv(self, path: str | Path) -> pd.DataFrame:
        """Lit le CSV et retourne un DataFrame validé.

        Parameters
        ----------
        path:
            Chemin du fichier CSV.

        Returns
        -------
        pd.DataFrame
            Données brutes validées (aucune transformation métier ici).

        Raises
        ------
        DatasetLoadError
            Fichier absent ou illisible.
        DatasetValidationError
            Contrat de données non respecté.
        """

        file_path = Path(path)

        if not file_path.is_file():
            raise DatasetLoadError(
                message=f"Dataset file not found: {file_path}",
                error_code="DATASET_NOT_FOUND",
                details={"path": str(file_path)},
            )

        try:
            df = pd.read_csv(file_path)
        except Exception as exc:
            raise DatasetLoadError(
                message=f"Dataset file could not be parsed as CSV: {file_path}",
                error_code="DATASET_PARSE_ERROR",
                details={"path": str(file_path)},
                original=exc,
            ) from exc

        self._validate(df, file_path)
        return df

    # ==========================================================
    # Validation
    # ==========================================================

    def _validate(self, df: pd.DataFrame, source: Path) -> None:
        """Applique l'ensemble des contrôles qualité au DataFrame chargé."""

        if df.empty:
            raise DatasetValidationError(
                message="Dataset is empty.",
                error_code="DATASET_EMPTY",
                details={"path": str(source)},
            )

        if self._target_column not in df.columns:
            raise DatasetValidationError(
                message=f"Target column '{self._target_column}' is missing from the dataset.",
                error_code="TARGET_COLUMN_MISSING",
                details={
                    "path": str(source),
                    "expected": self._target_column,
                    "available_columns": list(df.columns),
                },
            )

        if len(df) < self._min_rows:
            raise DatasetValidationError(
                message=(
                    f"Dataset too small: {len(df)} rows "
                    f"(minimum required: {self._min_rows})."
                ),
                error_code="DATASET_TOO_SMALL",
                details={"rows": len(df), "min_rows": self._min_rows},
            )

        self._warn_missing_values(df)
        self._drop_empty_columns(df)
        self._drop_excluded_columns(df)

    def _drop_excluded_columns(self, df: pd.DataFrame) -> None:
        """Supprime sur place les colonnes explicitement exclues (fuites)."""

        present = [col for col in self._exclude_columns if col in df.columns]
        if present:
            df.drop(columns=present, inplace=True)
            logger.info(
                "Excluded leakage columns from dataset: %s", present
            )

    def _warn_missing_values(self, df: pd.DataFrame) -> None:
        """Journalise un avertissement par colonne très incomplète (>50 % NaN)."""

        ratios = df.isna().mean()
        for column, ratio in ratios[ratios > 0.5].items():
            logger.warning(
                "Column '%s' has %.1f%% missing values — check data quality.",
                column, ratio * 100,
            )

    def _drop_empty_columns(self, df: pd.DataFrame) -> None:
        """Supprime sur place les colonnes 100 % vides (avec avertissement)."""

        empty = [col for col in df.columns if df[col].isna().all()]
        if empty:
            df.drop(columns=empty, inplace=True)
            logger.warning("Dropped all-NaN columns: %s", empty)

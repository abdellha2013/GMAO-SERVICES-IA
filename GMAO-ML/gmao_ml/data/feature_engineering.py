"""
gmao_ml/data/feature_engineering.py
===================================

Ingénierie de features capteurs (schéma AI4I 2020), sérialisable
dans le Pipeline sklearn.

Transformations appliquées (toutes pilotées par configuration) :

1. **Capping doux** des colonnes indiquées aux quantiles appris sur le
   train uniquement (pas de fuite de données ; bornes recalculées à
   chaque fold de la CV car le transformer vit dans le Pipeline).
   On ne supprime jamais de lignes : chez AI4I, les valeurs extrêmes de
   couple/vitesse concentrent les défaillances PWF — ce sont du signal.

2. **Dérivation physique** :

   - ``temperature_delta_k`` = Process temperature − Air temperature
     (échauffement net du procédé, lié au mode HDF) ;
   - ``puissance_w`` = Torque × Rotational speed × 2π/60
     (puissance mécanique en watts, directement liée au mode PWF).

3. **Suppression des redondances** : une fois les dérivées créées, les
   colonnes d'origine fortement corrélées sont retirées
   (``Process temperature [K]``, ``Torque [Nm]``).

Comportement tolérant : si les colonnes sources du schéma AI4I sont
absentes (autre dataset), le transformer est un **passthrough** — cela
permet d'utiliser le même orchestrateur avec n'importe quel CSV.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

__all__ = ["SensorFeatureEngineer"]

logger = logging.getLogger("gmao_ml.data")

_DERIVED_TEMP = "temperature_delta_k"
_DERIVED_POWER = "puissance_w"


class SensorFeatureEngineer(BaseEstimator, TransformerMixin):
    """Capping + dérivation + déduplication de colonnes corrélées.

    Parameters
    ----------
    cap_columns:
        Colonnes numériques à plafonner.

    cap_quantiles:
        Bornes (bas, haut) apprises sur le train.

    temp_source / power_torque_source / power_rpm_source:
        Noms de colonnes sources pour les dérivations AI4I.

    drop_after_derive:
        Colonnes supprimées après création des dérivées.
    """

    def __init__(
        self,
        cap_columns: tuple[str, ...] = ("Rotational speed [rpm]", "Torque [Nm]"),
        cap_quantiles: tuple[float, float] = (0.005, 0.995),
        temp_sources: tuple[str, str] = (
            "Air temperature [K]",
            "Process temperature [K]",
        ),
        power_sources: tuple[str, str] = ("Torque [Nm]", "Rotational speed [rpm]"),
        drop_after_derive: tuple[str, ...] = (
            "Process temperature [K]",
            "Torque [Nm]",
        ),
    ) -> None:
        self.cap_columns = cap_columns
        self.cap_quantiles = cap_quantiles
        self.temp_sources = temp_sources
        self.power_sources = power_sources
        self.drop_after_derive = drop_after_derive

    # ==========================================================
    # Fit
    # ==========================================================

    def fit(self, X: pd.DataFrame, y: Any = None) -> "SensorFeatureEngineer":
        """Apprend les bornes de capping sur les données d'entraînement."""

        frame = pd.DataFrame(X)
        self.cap_bounds_: dict[str, tuple[float, float]] = {}

        for column in self.cap_columns:
            if column not in frame.columns:
                continue
            low_q, high_q = frame[column].quantile(list(self.cap_quantiles))
            self.cap_bounds_[column] = (float(low_q), float(high_q))
            logger.info(
                "Cap learned for '%s': [%0.3f, %0.3f]",
                column, low_q, high_q,
            )

        return self

    # ==========================================================
    # Transform
    # ==========================================================

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Applique capping, dérivations et suppressions.

        Returns
        -------
        pd.DataFrame
            Frame transformée (jamais la même instance que ``X``).
        """

        frame = pd.DataFrame(X).copy()

        # --- 1. Capping doux (bornes apprises en fit) ---
        for column, (low, high) in getattr(self, "cap_bounds_", {}).items():
            if column in frame.columns:
                frame[column] = frame[column].clip(lower=low, upper=high)

        # --- 2. Dérivations (si colonnes sources présentes) ---
        air_col, process_col = self.temp_sources
        if air_col in frame.columns and process_col in frame.columns:
            frame[_DERIVED_TEMP] = frame[process_col] - frame[air_col]

        torque_col, rpm_col = self.power_sources
        if torque_col in frame.columns and rpm_col in frame.columns:
            omega_rad_s = frame[rpm_col] * (2.0 * np.pi / 60.0)
            frame[_DERIVED_POWER] = frame[torque_col] * omega_rad_s

        # --- 3. Suppression des originaux devenus redondants ---
        to_drop = [col for col in self.drop_after_derive if col in frame.columns]
        if to_drop:
            frame.drop(columns=to_drop, inplace=True)

        return frame

    # ==========================================================
    # Introspection (utile aux métadonnées / notebook)
    # ==========================================================

    def get_params(self, deep: bool = True) -> dict[str, Any]:
        """Contrat sklearn ``BaseEstimator`` (requis pour ``clone``/CV)."""

        return {
            "cap_columns": self.cap_columns,
            "cap_quantiles": self.cap_quantiles,
            "temp_sources": self.temp_sources,
            "power_sources": self.power_sources,
            "drop_after_derive": self.drop_after_derive,
        }

    def describe(self) -> dict[str, Any]:
        """Résumé journalisable des transformations actives."""

        return {
            "cap_columns": ",".join(self.cap_columns),
            "cap_quantiles": "-".join(str(q) for q in self.cap_quantiles),
            "drop_after_derive": ",".join(self.drop_after_derive),
            "derived": f"{_DERIVED_TEMP},{_DERIVED_POWER}",
        }

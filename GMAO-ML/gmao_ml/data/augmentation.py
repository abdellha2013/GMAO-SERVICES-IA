"""
gmao_ml/data/augmentation.py
============================

Data augmentation par les règles génératrices du dataset AI4I 2020
(Stephan Matzka), validées empiriquement à 100 % sur les données réelles :

- PWF  : ``power < 3500 W`` ou ``power > 9000 W`` avec
         ``power = Torque × RPM × 2π/60`` ;
- OSF  : ``Torque × Tool wear`` supérieur au seuil du type
         (L : 11 000, M : 12 000, H : 13 000) ;
- HDF  : ``delta_T < 8.6 K`` et ``RPM < 1380 tr/min`` ;
- ``machine_failure = PWF ∨ HDF ∨ OSF`` (le RNF ne compte PAS dans la cible,
   bizarrerie du dataset d'origine reproduite ici).

Usage : rééquilibrage du SEUL jeu d'entraînement (jamais du test !) par
bootstrap des capteurs réels puis étiquetage par les règles — la vérité
terrain de ce dataset étant précisément ces règles.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from gmao_ml.exceptions import DataError

__all__ = [
    "AI4IRuleAugmenter",
    "compute_power_w",
    "rule_pwf",
    "rule_osf",
    "rule_hdf",
    "machine_failure_from_rules",
]

logger = logging.getLogger("gmao_ml.data.augmentation")

POWER_LOW_W = 3500.0
POWER_HIGH_W = 9000.0
HDF_MAX_DELTA_K = 8.6
HDF_MAX_RPM = 1380.0
OSF_LIMITS_NM_MIN: dict[str, float] = {"L": 11_000.0, "M": 12_000.0, "H": 13_000.0}

REQUIRED_COLUMNS: tuple[str, ...] = (
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
)


def compute_power_w(torque_nm: pd.Series, rpm: pd.Series) -> pd.Series:
    """Puissance mécanique en watts : ``Couple × ω``, ``ω = RPM × 2π/60``."""

    return torque_nm * rpm * (2.0 * np.pi / 60.0)


def rule_pwf(power_w: pd.Series) -> pd.Series:
    """Power Failure : puissance hors fenêtre ``]3500, 9000[`` W."""

    return (power_w < POWER_LOW_W) | (power_w > POWER_HIGH_W)


def rule_osf(torque_nm: pd.Series, tool_wear_min: pd.Series, machine_type: pd.Series) -> pd.Series:
    """Overstrain Failure : couple × usure dépasse le seuil du type."""

    limits = machine_type.map(OSF_LIMITS_NM_MIN)
    if limits.isna().any():
        unknown = sorted(machine_type[limits.isna()].unique())
        raise DataError(
            message=f"Unknown machine type(s) for OSF rule: {unknown}",
            error_code="AUGMENTATION_UNKNOWN_TYPE",
            details={"unknown_types": unknown, "known": list(OSF_LIMITS_NM_MIN)},
        )
    return (torque_nm * tool_wear_min) > limits


def rule_hdf(delta_k: pd.Series, rpm: pd.Series) -> pd.Series:
    """Heat Dissipation Failure : échauffement net faible ET rotation lente."""

    return (delta_k < HDF_MAX_DELTA_K) & (rpm < HDF_MAX_RPM)


def machine_failure_from_rules(df: pd.DataFrame) -> pd.Series:
    """Étiquette binaire reconstruite depuis les règles (PWF ∨ HDF ∨ OSF)."""

    _require_columns(df)
    power = compute_power_w(df["Torque [Nm]"], df["Rotational speed [rpm]"])
    delta = df["Process temperature [K]"] - df["Air temperature [K]"]

    failure = (
        rule_pwf(power)
        | rule_osf(df["Torque [Nm]"], df["Tool wear [min]"], df["Type"])
        | rule_hdf(delta, df["Rotational speed [rpm]"])
    )
    return failure.astype(int)


def _require_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataError(
            message="AI4I augmentation requires the raw sensor columns.",
            error_code="AUGMENTATION_MISSING_COLUMNS",
            details={"missing": missing},
        )


class AI4IRuleAugmenter:
    """Rééquilibre un jeu d'entraînement AI4I par génération fondée sur règles.

    Principe :
    1. ``fit`` mémorise le pool de bootstrap (lignes capteurs RÉELLES du train)
       et mesure la fidélité des règles sur ce même jeu ;
    2. ``transform`` génère uniquement des lignes **positives** supplémentaires
       (échantillonnées dans le pool, étiquetées par les règles) jusqu'à
       atteindre ``target_minority_share``, puis concatène et mélange.

    Le nombre de positives synthétiques est résolu analytiquement pour
    ``(p₀ + s) / (n₀ + s) = target`` ⇒ ``s = (t·n₀ − p₀(1−t)) / (1−t)``.
    """

    def __init__(
        self,
        target_minority_share: float = 0.25,
        random_state: int = 42,
        max_batches: int = 500,
        jitter_sigma_frac: float = 0.0,
        max_neg_per_pos: float | None = None,
    ) -> None:
        if not 0.0 < target_minority_share < 1.0:
            raise DataError(
                message="target_minority_share must be within (0, 1).",
                error_code="AUGMENTATION_INVALID_SHARE",
                details={"received": target_minority_share},
            )
        if jitter_sigma_frac < 0.0:
            raise DataError(
                message="jitter_sigma_frac must be >= 0.",
                error_code="AUGMENTATION_INVALID_JITTER",
                details={"received": jitter_sigma_frac},
            )
        if max_neg_per_pos is not None and max_neg_per_pos <= 0.0:
            raise DataError(
                message="max_neg_per_pos must be > 0 when provided.",
                error_code="AUGMENTATION_INVALID_UNDERSAMPLE",
                details={"received": max_neg_per_pos},
            )
        self.target_minority_share = float(target_minority_share)
        self.random_state = int(random_state)
        self.max_batches = int(max_batches)
        self.jitter_sigma_frac = float(jitter_sigma_frac)
        self.max_neg_per_pos = None if max_neg_per_pos is None else float(max_neg_per_pos)

        self._pool: pd.DataFrame | None = None
        self._numeric_std_: pd.Series | None = None
        self.rule_agreement_: float | None = None
        self.n_real_positive_: int | None = None
        self.n_real_negative_: int | None = None
        self.n_synthetic_positive_: int | None = None
        self.n_dropped_negative_: int | None = None

    # ------------------------------------------------------------------

    def fit(self, df: pd.DataFrame, target_column: str = "machine_failure") -> "AI4IRuleAugmenter":
        """Mémorise le pool réel et mesure la fidélité des règles."""

        _require_columns(df)
        if target_column not in df.columns:
            raise DataError(
                message=f"Target column '{target_column}' missing for augmentation.",
                error_code="AUGMENTATION_TARGET_MISSING",
                details={"expected": target_column},
            )

        self._pool = df.loc[:, list(REQUIRED_COLUMNS)].reset_index(drop=True)
        numeric_cols = [c for c in REQUIRED_COLUMNS if c != "Type"]
        self._numeric_std_ = self._pool[numeric_cols].std(ddof=0).replace(0.0, np.nan)
        self.n_real_positive_ = int((df[target_column] == 1).sum())
        self.n_real_negative_ = int((df[target_column] == 0).sum())

        rule_labels = machine_failure_from_rules(self._pool)
        self.rule_agreement_ = float((rule_labels == df[target_column].astype(int)).mean())

        base_share = self.n_real_positive_ / max(len(df), 1)
        if self.target_minority_share <= base_share:
            raise DataError(
                message="target_minority_share must exceed the current minority share.",
                error_code="AUGMENTATION_TARGET_TOO_LOW",
                details={
                    "current_share": round(base_share, 4),
                    "requested_share": self.target_minority_share,
                },
            )
        return self

    def transform(self, df: pd.DataFrame, target_column: str = "machine_failure") -> pd.DataFrame:
        """Retourne ``df`` + positives synthétiques, mélangé (seed fixe)."""

        if self._pool is None:
            raise DataError(
                message="AI4IRuleAugmenter must be fitted before transform.",
                error_code="AUGMENTATION_NOT_FITTED",
            )
        _require_columns(df)

        quota = self._synthetic_positive_quota()
        rng = np.random.default_rng(self.random_state)
        positives: list[pd.DataFrame] = []
        collected = 0
        batch_size = max(len(self._pool), 100)

        for _ in range(self.max_batches):
            sample = self._pool.sample(n=batch_size, replace=True, random_state=rng)
            if self.jitter_sigma_frac > 0.0 and self._numeric_std_ is not None:
                # Bruit gaussien contrôlé AVANT l'étiquetage : les points
                # bruités sont re-labellisés par les règles (cohérence
                # physique garantie, diversité accrue autour du réel).
                for column, std in self._numeric_std_.items():
                    if np.isfinite(std):
                        sample[column] = sample[column] + rng.normal(
                            0.0, self.jitter_sigma_frac * float(std), size=len(sample)
                        )
            mask = machine_failure_from_rules(sample) == 1
            hits = sample.loc[mask]
            if hits.empty:
                continue
            take = min(len(hits), quota - collected)
            positives.append(hits.iloc[:take])
            collected += take
            if collected >= quota:
                break

        if collected < quota:
            raise DataError(
                message="Not enough distinct rule-positive samples generated.",
                error_code="AUGMENTATION_QUOTA_UNREACHED",
                details={"collected": collected, "quota": quota},
            )

        synthetic = pd.concat(positives, ignore_index=True)
        # Les lignes générées sont étiquetées par construction (règles).
        synthetic[target_column] = 1
        self.n_synthetic_positive_ = len(synthetic)
        self.synthetic_rows_: pd.DataFrame | None = synthetic.copy()

        combined = pd.concat([df, synthetic], ignore_index=True)

        self.n_dropped_negative_ = 0
        if self.max_neg_per_pos is not None:
            total_pos = int((combined[target_column] == 1).sum())
            allowed_neg = int(np.ceil(self.max_neg_per_pos * total_pos))
            negative_idx = combined.index[combined[target_column] == 0].to_numpy()
            if allowed_neg < len(negative_idx):
                rng.shuffle(negative_idx)
                to_drop = negative_idx[allowed_neg:]
                combined = combined.drop(index=to_drop)
                self.n_dropped_negative_ = len(to_drop)

        combined = combined.sample(frac=1.0, random_state=self.random_state).reset_index(drop=True)

        logger.info(
            "Augmentation: +%d synthetic positives (agreement=%.3f, share %.3f→%.3f)",
            len(synthetic),
            self.rule_agreement_ or float("nan"),
            self.n_real_positive_ / max(len(df), 1),
            (self.n_real_positive_ + len(synthetic)) / len(combined),
        )
        return combined

    def fit_transform(self, df: pd.DataFrame, target_column: str = "machine_failure") -> pd.DataFrame:
        """Enchaîne :func:`fit` puis :func:`transform`."""

        return self.fit(df, target_column=target_column).transform(df, target_column=target_column)

    def summary(self) -> dict[str, Any]:
        """Résumé journalisable de l'opération d'augmentation."""

        return {
            "strategy": "ai4i_rule_bootstrap",
            "target_minority_share": self.target_minority_share,
            "random_state": self.random_state,
            "rule_agreement_on_real": self.rule_agreement_,
            "n_real_positive": self.n_real_positive_,
            "n_real_negative": self.n_real_negative_,
            "n_synthetic_positive": self.n_synthetic_positive_,
            "jitter_sigma_frac": self.jitter_sigma_frac,
            "max_neg_per_pos": self.max_neg_per_pos,
            "n_dropped_negative": self.n_dropped_negative_,
        }

    # ------------------------------------------------------------------

    def _synthetic_positive_quota(self) -> int:
        assert self.n_real_positive_ is not None and self.n_real_negative_ is not None
        p0, n0, t = self.n_real_positive_, self.n_real_negative_, self.target_minority_share
        quota_float = (t * n0 - p0 * (1.0 - t)) / (1.0 - t)
        return int(max(quota_float, 0.0))

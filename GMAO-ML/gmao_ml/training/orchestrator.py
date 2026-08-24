"""
gmao_ml/training/orchestrator.py
================================

Orchestrateur du pipeline d'entraînement.

Séquence exécutée par :meth:`TrainingOrchestrator.train` :

1. nettoyage ciblé (lignes sans cible) ;
2. split stratifié train/test reproductible ;
3. détection automatique des types de colonnes ;
4. pour chaque stratégie du registre : CV 5-fold + évaluation holdout
   (+ logging MLflow par candidat) ;
5. sélection du meilleur candidat (f1_macro holdout) ;
6. ré-entraînement sur l'intégralité des données, sérialisation de
   l'artefact (pipeline complet prétraitement inclus), écriture des
   métadonnées et du pointeur ``latest.json``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline

from gmao_ml.data.preprocessing import (
    CLASSIFIER_STEP,
    PREPROCESSOR_STEP,
    build_preprocessor,
    detect_column_types,
)
from gmao_ml.exceptions import (
    ModelSerializationError,
    TrainingError,
    TrainingValidationError,
)
from gmao_ml.tracking.mlflow_tracker import MlflowTracker
from gmao_ml.training.registry import TrainingStrategyRegistry, build_default_registry

__all__ = ["TrainingOrchestrator", "TrainingResult"]

logger = logging.getLogger("gmao_ml.training")

_LATEST_POINTER = "latest.json"


@dataclass(slots=True)
class TrainingResult:
    """Sortie complète d'une session d'entraînement.

    Attributes
    ----------
    model_name / version:
        Identifiants de l'artefact produit.

    model_path / metadata_path:
        Chemins des fichiers écrits sur disque.

    best_strategy:
        Nom de la stratégie retenue.

    classes:
        Libellés des classes cibles (triés).

    strategy_metrics:
        Métriques détaillées par stratégie candidate.

    best_confusion_matrix:
        Matrice de confusion du meilleur modèle sur le holdout.

    n_samples_train / n_samples_test:
        Volumes utilisés.
    """

    model_name: str
    version: str
    model_path: Path
    metadata_path: Path
    best_strategy: str
    classes: list[str]
    strategy_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    best_confusion_matrix: list[list[int]] = field(default_factory=list)
    n_samples_train: int = 0
    n_samples_test: int = 0


class TrainingOrchestrator:
    """Compare les stratégies d'entraînement et publie le meilleur modèle.

    Parameters
    ----------
    registry:
        Registre des stratégies disponibles.

    tracker:
        Tracker MLflow optionnel ; désactivé proprement en cas d'erreur
        backend (l'entraînement ne doit jamais échouer à cause du suivi).

    model_dir:
        Répertoire racine des artefacts.

    model_name:
        Sous-répertoire/logique de l'artefact.

        target_column:
            Colonne cible dans le DataFrame fourni.

        test_size / random_state:
            Paramètres du split et des estimateurs.

        balance_class_weights:
            Si ``True``, transmet ``class_weight="balanced"`` aux
            stratégies qui le supportent (rééquilibrage des classes rares).

        feature_engineer:
            Transformer sklearn optionnel inséré en tête de chaque
            pipeline candidat (ex : ``SensorFeatureEngineer``). Il est
            ré-ajusté à chaque fold de la CV (aucune fuite) et sérialisé
            avec le modèle final.
    """

    _IMBALANCE_ALERT_THRESHOLD = 0.10

    def __init__(
        self,
        registry: TrainingStrategyRegistry | None = None,
        tracker: MlflowTracker | None = None,
        *,
        model_dir: str | Path,
        model_name: str = "gmao_state_classifier",
        target_column: str = "gravite",
        test_size: float = 0.2,
        random_state: int = 42,
        balance_class_weights: bool = False,
        feature_engineer: Any | None = None,
    ) -> None:
        self._registry = registry or build_default_registry(random_state=random_state)
        self._tracker = tracker
        self._model_dir = Path(model_dir)
        self._model_name = model_name
        self._target_column = target_column
        self._test_size = test_size
        self._random_state = random_state
        self._balance_class_weights = balance_class_weights
        self._feature_engineer = feature_engineer

    @property
    def model_dir(self) -> Path:
        """Répertoire des artefacts."""

        return self._model_dir

    # ==========================================================
    # Public API
    # ==========================================================

    def train(
        self,
        df: pd.DataFrame,
        strategies: list[str] | None = None,
    ) -> TrainingResult:
        """Entraîne, compare et publie le meilleur modèle.

        Parameters
        ----------
        df:
            Dataset complet (features + colonne cible).

        strategies:
            Sous-ensemble de stratégies à évaluer ; défaut : toutes.

        Returns
        -------
        TrainingResult
            Résumé de la session (chemins, métriques, matrice…).
        """

        clean = self._prepare(df)
        y = clean[self._target_column]
        X = clean.drop(columns=[self._target_column])

        self._imbalance_ratio = float(y.value_counts(normalize=True).min())
        if self._imbalance_ratio < self._IMBALANCE_ALERT_THRESHOLD:
            logger.warning(
                "Class imbalance detected: minority class holds only %.2f%% of "
                "samples (< %.0f%%). Consider balance_class_weights=True and "
                "rely on f1_macro/recall rather than accuracy.",
                self._imbalance_ratio * 100,
                self._IMBALANCE_ALERT_THRESHOLD * 100,
            )

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=self._test_size,
            random_state=self._random_state,
            stratify=y,
        )

        if self._feature_engineer is not None:
            # Le schéma de sortie du feature engineer est déterministe :
            # on sonde la transformation pour détecter les types réels
            # tels qu'ils arriveront au préprocesseur.
            probe = clone(self._feature_engineer).fit_transform(X_train.head(200))
            column_types = detect_column_types(pd.DataFrame(probe))
        else:
            column_types = detect_column_types(X_train)

        requested = strategies or self._registry.supported_strategies()
        unknown = [name for name in requested if not self._registry.has(name)]
        if unknown:
            raise TrainingValidationError(
                message="Unknown training strategies requested.",
                error_code="UNKNOWN_STRATEGY",
                details={
                    "unknown": unknown,
                    "supported": self._registry.supported_strategies(),
                },
            )

        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        all_metrics: dict[str, dict[str, float]] = {}
        best_name: str | None = None
        best_f1 = -1.0
        best_cm: list[list[int]] = []

        for name in requested:
            logger.info("=== Training candidate '%s' ===", name)
            metrics, cm = self._evaluate_candidate(
                name, X_train, X_test, y_train, y_test, version, column_types
            )
            all_metrics[name] = metrics

            if metrics["holdout_f1_macro"] > best_f1:
                best_f1 = metrics["holdout_f1_macro"]
                best_name = name
                best_cm = cm

        assert best_name is not None  # au moins une stratégie demandée (validé plus haut)

        result = self._publish_best(
            best_name=best_name,
            version=version,
            column_types=column_types,
            X=X,
            y=y,
            X_test=X_test,
            y_test=y_test,
            all_metrics=all_metrics,
            cm=best_cm,
            n_train=len(X_train),
            n_test=len(X_test),
        )

        logger.info(
            "Training complete — best=%s f1_macro=%.4f artifact=%s",
            result.best_strategy,
            best_f1,
            result.model_path,
        )
        return result

    # ==========================================================
    # Internals
    # ==========================================================

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Nettoie les lignes sans cible et vérifie le volume restant."""

        if self._target_column not in df.columns:
            raise TrainingValidationError(
                message=f"Target column '{self._target_column}' is missing.",
                error_code="TARGET_COLUMN_MISSING",
                details={"columns": list(df.columns)},
            )

        before = len(df)
        clean = df.dropna(subset=[self._target_column]).copy()
        dropped = before - len(clean)

        if dropped:
            logger.warning("Dropped %d row(s) without target value.", dropped)

        if len(clean) < 20:
            raise TrainingValidationError(
                message=f"Not enough usable rows to train: {len(clean)} (< 20).",
                error_code="TRAINING_TOO_SMALL",
                details={"usable_rows": len(clean)},
            )

        return clean

    def _build_pipeline(self, strategy_name: str, column_types: dict[str, list[str]]) -> tuple[Pipeline, Any]:
        """Construit le Pipeline complet (features + prétraitement + classifieur)."""

        strategy = self._registry.get(strategy_name)(
            random_state=self._random_state,
            balance_class_weights=self._balance_class_weights,
        )
        estimator = strategy.create_estimator()

        steps: list[tuple[str, Any]] = []
        if self._feature_engineer is not None:
            steps.append(("features", clone(self._feature_engineer)))
        steps.extend([
            (PREPROCESSOR_STEP, build_preprocessor(column_types)),
            (CLASSIFIER_STEP, estimator),
        ])

        pipeline = Pipeline(steps)
        return pipeline, strategy

    def _evaluate_candidate(
        self,
        name: str,
        X_train: pd.DataFrame,
        X_test: pd.DataFrame,
        y_train: pd.Series,
        y_test: pd.Series,
        version: str,
        column_types: dict[str, list[str]],
    ) -> tuple[dict[str, float], list[list[int]]]:
        """CV 5-fold + holdout pour un candidat, avec logging MLflow."""

        pipeline, strategy = self._build_pipeline(name, column_types)

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=self._random_state)
        cv_scores = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring="f1_macro")

        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)

        metrics = {
            "cv_f1_macro_mean": float(cv_scores.mean()),
            "cv_f1_macro_std": float(cv_scores.std()),
            "holdout_accuracy": float(accuracy_score(y_test, y_pred)),
            "holdout_f1_macro": float(f1_score(y_test, y_pred, average="macro")),
            "holdout_precision_macro": float(precision_score(y_test, y_pred, average="macro", zero_division=0)),
            "holdout_recall_macro": float(recall_score(y_test, y_pred, average="macro", zero_division=0)),
        }

        cm = confusion_matrix(y_test, y_pred).tolist()

        self._track_run(name, version, strategy.get_params(), metrics)

        logger.info(
            "Candidate '%s' — cv_f1=%.4f±%.4f holdout_f1=%.4f acc=%.4f",
            name,
            metrics["cv_f1_macro_mean"],
            metrics["cv_f1_macro_std"],
            metrics["holdout_f1_macro"],
            metrics["holdout_accuracy"],
        )
        return metrics, cm

    # ==========================================================
    # MLflow (best effort)
    # ==========================================================

    def _track_run(
        self,
        strategy_name: str,
        version: str,
        params: dict[str, Any],
        metrics: dict[str, float],
    ) -> None:
        """Journalise un candidat dans MLflow ; désactive le tracking si indisponible."""

        if self._tracker is None:
            return

        try:
            with self._tracker.start_run(f"{self._model_name}-{strategy_name}-{version}"):
                self._tracker.log_params({
                    "model_name": self._model_name,
                    "version": version,
                    "strategy": strategy_name,
                    "target_column": self._target_column,
                    "test_size": self._test_size,
                    "random_state": self._random_state,
                    "balance_class_weights": self._balance_class_weights,
                    **params,
                })
                self._tracker.log_metrics(metrics)
        except Exception as exc:  # noqa: BLE001 — le tracking ne doit jamais bloquer l'entraînement
            logger.warning("MLflow tracking disabled for this session (%s)", exc)
            self._tracker = None

    # ==========================================================
    # Publication
    # ==========================================================

    def _publish_best(
        self,
        best_name: str,
        version: str,
        column_types: dict[str, list[str]],
        X: pd.DataFrame,
        y: pd.Series,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        all_metrics: dict[str, dict[str, float]],
        cm: list[list[int]],
        n_train: int,
        n_test: int,
    ) -> TrainingResult:
        """Ré-entraîne le meilleur candidat sur tout le dataset et sérialise."""

        pipeline, strategy = self._build_pipeline(best_name, column_types)

        try:
            pipeline.fit(X, y)
        except Exception as exc:
            raise TrainingError(
                message="Final fit of the best model failed.",
                error_code="FINAL_FIT_ERROR",
                details={"strategy": best_name},
                original=exc,
            ) from exc

        classes = [
            label if isinstance(label, str) else str(label)
            for label in getattr(
                pipeline.named_steps[CLASSIFIER_STEP],
                "classes_",
                [],
            )
        ]

        engineer_summary: Any = None
        if self._feature_engineer is not None:
            describe = getattr(self._feature_engineer, "describe", None)
            engineer_summary = (
                describe() if callable(describe) else str(self._feature_engineer)
            )

        metadata = {
            "name": self._model_name,
            "version": version,
            "strategy": best_name,
            "target_column": self._target_column,
            "classes": sorted(classes),
            "features": column_types,
            # Schéma BRUT attendu à l'inférence : avec un feature engineer
            # embarqué, les dérivées sont calculées PAR le pipeline, donc
            # l'API doit recevoir les colonnes sources (ex: Process
            # temperature, Torque) et non le schéma transformé.
            "input_features": list(X.columns),
            "metrics": all_metrics,
            "holdout_confusion_matrix": cm,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "n_samples_train": n_train,
            "n_samples_test": n_test,
            "n_samples_total": len(X),
            "class_imbalance_ratio": round(getattr(self, "_imbalance_ratio", float("nan")), 4),
            "balanced_class_weights": self._balance_class_weights,
            "feature_engineering": engineer_summary,
            "sklearn_version": sklearn.__version__,
            "strategy_params": strategy.get_params(),
        }

        model_dir = self._model_dir / self._model_name
        model_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / f"{version}.joblib"
        metadata_path = model_dir / f"{version}.metadata.json"
        latest_path = model_dir / _LATEST_POINTER

        try:
            joblib.dump({"pipeline": pipeline, "metadata": metadata}, model_path)
            metadata_path.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            latest_path.write_text(json.dumps({"version": version}), encoding="utf-8")
        except Exception as exc:
            raise ModelSerializationError(
                message="Failed to persist model artifacts.",
                error_code="ARTIFACT_WRITE_ERROR",
                details={"model_dir": str(model_dir)},
                original=exc,
            ) from exc

        return TrainingResult(
            model_name=self._model_name,
            version=version,
            model_path=model_path,
            metadata_path=metadata_path,
            best_strategy=best_name,
            classes=sorted(classes),
            strategy_metrics=all_metrics,
            best_confusion_matrix=cm,
            n_samples_train=n_train,
            n_samples_test=n_test,
        )

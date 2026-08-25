"""
gmao_ml/inference/predictor.py
==============================

Service d'inférence : chargement de l'artefact et prédiction.

L'artefact est un dict ``{"pipeline", "metadata"}`` produit par
l'orchestrateur d'entraînement ; le pipeline embarque son propre
prétraitement, donc les features brutes (dict JSON) suffisent en
entrée — aucune transformation côté client.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from gmao_ml.exceptions import (
    InferenceValidationError,
    ModelNotFoundError,
    ModelNotReadyError,
    ModelSerializationError,
    PredictionError,
    MLError,
)

__all__ = ["Predictor"]

logger = logging.getLogger("gmao_ml.inference")

_LATEST_POINTER = "latest.json"
_MAX_BATCH = 1000


class Predictor:
    """Charge un modèle sérialisé et expose des prédictions unitaires/lot.

    Parameters
    ----------
    model_dir:
        Répertoire racine des artefacts.

    model_name:
        Nom logique du modèle (sous-répertoire).

    version:
        Version à charger : ``"latest"`` (pointeur) ou identifiant exact.
        ``None`` → résolution paresseuse au premier appel.
    """

    def __init__(
        self,
        model_dir: str | Path,
        model_name: str = "gmao_state_classifier",
        version: str | None = None,
    ) -> None:
        self._model_dir = Path(model_dir)
        self._model_name = model_name
        self._requested_version = version or "latest"

        self._bundle: dict[str, Any] | None = None
        self._version: str | None = None
        self._metadata: dict[str, Any] | None = None
        self._expected_features: list[str] | None = None

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def is_loaded(self) -> bool:
        """Indique si un modèle est chargé en mémoire."""

        return self._bundle is not None

    @property
    def version(self) -> str | None:
        """Version effectivement chargée (``None`` si rien n'est chargé)."""

        return self._version

    @property
    def metadata(self) -> dict[str, Any]:
        """Métadonnées du modèle chargé.

        Raises
        ------
        ModelNotReadyError
            Si aucun modèle n'a été chargé.
        """

        if self._metadata is None:
            raise ModelNotReadyError(
                message="No model loaded yet.",
                error_code="MODEL_NOT_READY",
            )
        return self._metadata

    # ==========================================================
    # Loading
    # ==========================================================

    def load(self) -> bool:
        """Charge l'artefact demandé.

        Returns
        -------
        bool
            ``True`` si le chargement a réussi.

        Raises
        ------
        ModelNotFoundError
            Artefact ou pointeur introuvable.
        ModelSerializationError
            Fichier corrompu / incompatible.
        """

        model_dir = self._model_dir / self._model_name
        version = self._resolve_version(model_dir)

        artifact_path = model_dir / f"{version}.joblib"
        if not artifact_path.is_file():
            raise ModelNotFoundError(
                message="Model artifact not found.",
                error_code="ARTIFACT_NOT_FOUND",
                details={
                    "expected_path": str(artifact_path),
                    "model_name": self._model_name,
                    "requested_version": self._requested_version,
                },
            )

        try:
            bundle = joblib.load(artifact_path)
        except Exception as exc:
            raise ModelSerializationError(
                message=f"Failed to load model artifact: {artifact_path}",
                error_code="ARTIFACT_LOAD_ERROR",
                original=exc,
            ) from exc

        metadata = bundle.get("metadata") if isinstance(bundle, dict) else None
        pipeline = bundle.get("pipeline") if isinstance(bundle, dict) else None

        if not isinstance(metadata, dict) or pipeline is None:
            raise ModelSerializationError(
                message="Model artifact has an unexpected structure "
                        "(expected {'pipeline', 'metadata'}).",
                error_code="ARTIFACT_STRUCTURE_ERROR",
                details={"artifact": str(artifact_path)},
            )

        features = metadata.get("features", {})
        # Contrat d'entrée : schéma brut (input_features) s'il est publié
        # (pipeline avec feature engineer embarqué), sinon schéma transformé.
        input_features = metadata.get("input_features")
        self._expected_features = (
            list(input_features)
            if input_features
            else list(features.get("numeric", [])) + list(features.get("categorical", []))
        )

        self._bundle = bundle
        self._version = version
        self._metadata = metadata

        logger.info(
            "Model loaded — name=%s version=%s strategy=%s",
            self._model_name,
            version,
            metadata.get("strategy"),
        )
        return True

    def _resolve_version(self, model_dir: Path) -> str:
        """Résout ``latest`` via le fichier pointeur, sinon retourne la version brute."""

        if self._requested_version != "latest":
            return self._requested_version

        pointer_path = model_dir / _LATEST_POINTER
        if not pointer_path.is_file():
            raise ModelNotFoundError(
                message="No trained model available (latest pointer missing).",
                error_code="NO_MODEL_AVAILABLE",
                details={"model_dir": str(model_dir)},
            )

        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            version = pointer["version"]
        except Exception as exc:
            raise ModelSerializationError(
                message=f"Invalid latest pointer file: {pointer_path}",
                error_code="POINTER_READ_ERROR",
                original=exc,
            ) from exc

        return str(version)

    # ==========================================================
    # Prediction
    # ==========================================================

    def predict_one(self, features: dict[str, Any]) -> dict[str, Any]:
        """Prédit pour un vecteur de features brut.

        Returns
        -------
        dict
            ``{"prediction", "probabilities", "model_version"}``.

        Raises
        ------
        ModelNotReadyError
            Aucun modèle chargé.
        InferenceValidationError
            Features vides ou incompatibles avec le modèle.
        PredictionError
            Échec à l'exécution du pipeline.
        """

        frame = self._to_frame([features])
        result = self._run_pipeline(frame)[0]
        result["model_version"] = self.version  # type: ignore[union-attr]
        return result

    def predict_batch(self, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prédit pour un lot de vecteurs de features (max 1000)."""

        if not samples:
            raise InferenceValidationError(
                message="Batch must contain at least one sample.",
                error_code="EMPTY_BATCH",
            )

        if len(samples) > _MAX_BATCH:
            raise InferenceValidationError(
                message=f"Batch too large: {len(samples)} samples (max {_MAX_BATCH}).",
                error_code="BATCH_TOO_LARGE",
                details={"received": len(samples), "max": _MAX_BATCH},
            )

        frame = self._to_frame(samples)
        results = self._run_pipeline(frame)
        for result in results:
            result["model_version"] = self.version  # type: ignore[union-attr]
        return results

    # ==========================================================
    # Internals
    # ==========================================================

    def _to_frame(self, samples: list[dict[str, Any]]) -> pd.DataFrame:
        """Normalise une liste de dicts en DataFrame aligné sur le schéma du modèle."""

        if not self.is_loaded:
            raise ModelNotReadyError(
                message="No model loaded yet.",
                error_code="MODEL_NOT_READY",
            )

        if not all(isinstance(sample, dict) for sample in samples):
            raise InferenceValidationError(
                message="Each sample must be a mapping of feature name → value.",
                error_code="INVALID_SAMPLE_TYPE",
            )

        assert self._expected_features is not None
        frame = pd.DataFrame(samples)

        provided = set(frame.columns)
        expected_set = set(self._expected_features)
        extra = sorted(provided - expected_set)
        missing_all = [
            col for col in self._expected_features
            if col not in provided or frame[col].isna().all()
        ]

        if len(missing_all) == len(self._expected_features):
            raise InferenceValidationError(
                message="None of the expected features were provided.",
                error_code="NO_EXPECTED_FEATURES",
                details={"expected_features": self._expected_features},
            )

        if extra:
            logger.debug("Ignoring unexpected feature column(s): %s", extra)

        return frame.reindex(columns=self._expected_features)

    def _run_pipeline(self, frame: pd.DataFrame) -> list[dict[str, Any]]:
        """Exécute predict (+ predict_proba) et formate la sortie.

        Si les métadonnées publient ``decision_threshold`` (binaire), la
        prédiction est dérivée des probabilités : ``classe positive`` dès que
        ``P(positive) >= seuil`` — sinon le 0.5 interne du pipeline s'applique.
        """

        assert self._bundle is not None
        pipeline = self._bundle["pipeline"]
        metadata = self._bundle["metadata"]

        threshold = metadata.get("decision_threshold")
        proba_method = getattr(pipeline, "predict_proba", None)

        probabilities_per_row: list[dict[str, float] | None]
        predictions: Any

        if threshold is not None and callable(proba_method):
            try:
                probas = proba_method(frame)
                classes = list(pipeline.named_steps["classifier"].classes_)
                class_labels = [c if isinstance(c, str) else str(c) for c in classes]

                if len(classes) != 2:
                    logger.warning(
                        "decision_threshold ignored: expected binary classifier, got %d classes.",
                        len(classes),
                    )
                    predictions = pipeline.predict(frame)
                    probabilities_per_row = [
                        {cls: float(score) for cls, score in zip(class_labels, row)}
                        for row in probas
                    ]
                else:
                    positive_raw = metadata.get("positive_class", classes[1])
                    pos_col = classes.index(positive_raw) if positive_raw in classes else 1
                    neg_col = 1 - pos_col

                    positive_scores = probas[:, pos_col]
                    predictions = np.where(
                        positive_scores >= float(threshold),
                        classes[pos_col],
                        classes[neg_col],
                    )
                    probabilities_per_row = [
                        {cls: float(score) for cls, score in zip(class_labels, row)}
                        for row in probas
                    ]
            except MLError:
                raise
            except Exception as exc:  # noqa: BLE001 — fallback prédict standard
                logger.warning("Threshold-based prediction failed (%s); falling back.", exc)
                predictions = pipeline.predict(frame)
                probabilities_per_row = [None] * len(frame)
        else:
            try:
                predictions = pipeline.predict(frame)
            except Exception as exc:
                raise PredictionError(
                    message="Model inference failed.",
                    error_code="INFERENCE_FAILED",
                    original=exc,
                ) from exc

            if callable(proba_method):
                try:
                    probas = proba_method(frame)
                    classes = [
                        c if isinstance(c, str) else str(c)
                        for c in pipeline.named_steps["classifier"].classes_
                    ]
                    probabilities_per_row = [
                        {cls: float(score) for cls, score in zip(classes, row)}
                        for row in probas
                    ]
                except Exception:  # noqa: BLE001 — probabilités optionnelles
                    probabilities_per_row = [None] * len(frame)
            else:
                probabilities_per_row = [None] * len(frame)

        results: list[dict[str, Any]] = []
        for raw_prediction, probabilities in zip(predictions, probabilities_per_row):
            prediction = raw_prediction.item() if hasattr(raw_prediction, "item") else raw_prediction
            results.append({
                "prediction": prediction,
                "probabilities": probabilities,
            })

        return results

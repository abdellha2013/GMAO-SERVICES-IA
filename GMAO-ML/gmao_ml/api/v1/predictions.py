"""Prediction endpoints (single sample and batch)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from gmao_ml.api.auth import verify_api_key
from gmao_ml.api.deps import get_predictor
from gmao_ml.inference import Predictor
from gmao_ml.models.schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    PredictionItem,
)

router = APIRouter(tags=["predictions"])


@router.post("/predict", response_model=PredictResponse)
async def predict(
    request: PredictRequest,
    predictor: Annotated[Predictor, Depends(get_predictor)],
    _token: Annotated[str, Depends(verify_api_key)],
) -> PredictionItem:
    """Predict the machine state for a single feature vector."""
    result = predictor.predict_one(request.features)
    return PredictionItem(
        prediction=result["prediction"],
        probabilities=result.get("probabilities"),
        model_version=result["model_version"],
    )


@router.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch(
    request: BatchPredictRequest,
    predictor: Annotated[Predictor, Depends(get_predictor)],
    _token: Annotated[str, Depends(verify_api_key)],
) -> BatchPredictResponse:
    """Predict the machine state for a batch of feature vectors."""
    results = predictor.predict_batch(request.samples)

    items = [
        PredictionItem(
            prediction=result["prediction"],
            probabilities=result.get("probabilities"),
            model_version=result["model_version"],
        )
        for result in results
    ]
    return BatchPredictResponse(
        predictions=items,
        count=len(items),
        model_version=items[0].model_version,
    )


@router.get("/model/info", response_model=ModelInfoResponse)
async def model_info(
    predictor: Annotated[Predictor, Depends(get_predictor)],
    _token: Annotated[str, Depends(verify_api_key)],
) -> ModelInfoResponse:
    """Expose metadata of the currently loaded model."""
    metadata = predictor.metadata

    return ModelInfoResponse(
        name=metadata["name"],
        version=predictor.version,
        strategy=metadata["strategy"],
        target_column=metadata["target_column"],
        classes=[str(c) for c in metadata["classes"]],
        features=metadata["features"],
        metrics=metadata["metrics"],
        trained_at=metadata["trained_at"],
        n_training_samples=(
            metadata.get("n_samples_total")
            or metadata.get("n_training_samples")
            or 0
        ),
        sklearn_version=metadata["sklearn_version"],
    )

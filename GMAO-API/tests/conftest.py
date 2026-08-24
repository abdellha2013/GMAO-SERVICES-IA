"""Fixtures communes aux tests GMAO-API."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from gmao_api.config import Settings
from gmao_api.api.main import create_app


def fake_ml_handler(prediction_for: Any = None):
    """Transport ML simulé : prédiction 1 si torque >= 80 (sinon 0)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/healthz":
            return httpx.Response(200, json={"status": "ok", "model_loaded": True})
        if request.url.path == "/api/v1/predict":
            features = json.loads(request.content)["features"]
            prediction = 1 if float(features["Torque [Nm]"]) >= 80 else 0
            probability = 0.95 if prediction == 1 else 0.02
            return httpx.Response(
                200,
                json={
                    "prediction": prediction,
                    "probabilities": {"0": round(1 - probability, 4), "1": probability},
                    "model_version": "test-v1",
                },
            )
        return httpx.Response(404)

    return handler


def failing_ml_handler():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return handler


def make_settings(**overrides: Any) -> Settings:
    base = dict(
        api_key="test-key",
        ml_api_url="http://ml.test",
        ml_api_key="ml-key",
        ml_retries=0,
        simulate_laravel=True,
        laravel_api_url="http://laravel.test",
        laravel_ia_user_id=1,
        critical_probability=0.90,
    )
    base.update(overrides)
    return Settings(**base)


def make_app(ml_handler=None, settings: Settings | None = None, laravel_transport=None):
    transport = httpx.MockTransport(ml_handler or fake_ml_handler())
    app = create_app(
        settings=settings or make_settings(),
        ml_transport=transport,
        laravel_transport=laravel_transport,
    )
    return app


AUTH = {"Authorization": "Bearer test-key"}


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    with TestClient(make_app()) as test_client:
        yield test_client

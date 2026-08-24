"""Client HTTP asynchrone vers l'API de prédiction GMAO-ML."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from gmao_api.config import Settings
from gmao_api.exceptions import MlAuthError, MlUpstreamError

logger = logging.getLogger("gmao_api.ml_client")


class MlClient:
    """Wrapper ``/api/v1/predict`` et ``/healthz`` de GMAO-ML.

    ``transport`` permet d'injecter un ``httpx.MockTransport`` (tests).
    """

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.ml_api_url,
            timeout=settings.ml_timeout_s,
            headers={"Authorization": f"Bearer {settings.ml_api_key}"},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        """Ping non authentifié du service ML (healthz)."""

        try:
            response = await self._client.get("/api/v1/healthz")
            return response.status_code == 200 and bool(response.json().get("model_loaded"))
        except httpx.HTTPError:
            return False

    async def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """Prédiction unitaire. Retourne ``{prediction, probabilities, model_version}``.

        Raises
        ------
        MlAuthError
            Clé refusée (401).
        MlUpstreamError
            Injoignable après retries, statut inattendu ou corps invalide.
        """

        payload = {"features": features}
        attempts = max(1, self._settings.ml_retries + 1)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                started = time.perf_counter()
                response = await self._client.post("/api/v1/predict", json=payload)
                elapsed_ms = (time.perf_counter() - started) * 1000

                if response.status_code == 200:
                    body = response.json()
                    logger.info(
                        "ML prediction ok en %.1f ms — prediction=%s version=%s",
                        elapsed_ms,
                        body.get("prediction"),
                        body.get("model_version"),
                    )
                    return {
                        "prediction": body["prediction"],
                        "probabilities": body.get("probabilities") or {},
                        "model_version": body.get("model_version"),
                    }

                if response.status_code == 401:
                    raise MlAuthError(
                        "Clé ML_API_KEY refusée par GMAO-ML.",
                        details={"status": 401},
                    )

                raise MlUpstreamError(
                    f"GMAO-ML a répondu {response.status_code}.",
                    details={"status": response.status_code, "body": _safe_json(response)},
                )

            except MlAuthError:
                raise
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt < attempts:
                    await asyncio.sleep(0.25 * attempt)

        raise MlUpstreamError(
            "GMAO-ML injoignable après plusieurs tentatives.",
            details={
                "url": str(self._client.base_url).rstrip("/") + "/api/v1/predict",
                "attempts": attempts,
                "last_error": str(last_error),
            },
        )


def positive_probability(probabilities: dict[str, float]) -> float:
    """P(classe positive = '1') ; fallback sur le max si clés inhabituelles."""

    if not probabilities:
        return 0.0
    value = probabilities.get("1", probabilities.get("1.0"))
    if value is None:
        return max(float(v) for v in probabilities.values())
    return float(value)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:200]


__all__ = ["MlClient", "positive_probability"]

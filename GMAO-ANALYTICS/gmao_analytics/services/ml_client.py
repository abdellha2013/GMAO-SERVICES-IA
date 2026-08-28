"""Client HTTP asynchrone vers GMAO-ML, pour l'enrichissement du rapport.

Le service Analytics ne dépend pas de la prédiction pour fonctionner :
il l'interroge de manière **tolérante aux erreurs** et se replie sur un
enrichissement dégradé si GMAO-ML est indisponible.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from gmao_analytics.config import Settings
from gmao_analytics.models.schemas import EquipementMetrics, RiskCrossover

logger = logging.getLogger("gmao_analytics.ml_client")

RISK_ORDER = ["faible", "moyen", "eleve", "critique"]


class MlEnricher:
    """Enrichit les indicateurs avec le risque prédictif (GMAO-ML)."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.ml_api_url,
            timeout=settings.ml_timeout_s,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            response = await self._client.get("/api/v1/healthz")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def enrich(
        self,
        equipement_ids: list[int],
        per_equip: list[EquipementMetrics],
    ) -> list[RiskCrossover]:
        """Croise le MTBF de chaque équipement avec un indicateur de risque.

        Interroge ``GET /api/v1/model/info`` (non destructif) pour valider
        la disponibilité du modèle, puis construit un croisement basé sur
        l'historique (MTBF court → risque élevé). Si une prédiction réelle
        est disponible (via GMAO-API), elle peut être fournie en paramètre
        additionnel, sinon on reste sur l'heuristique MTBF.

        Raises
        ------
        httpx.HTTPError
            Si GMAO-ML est injoignable (propagée, gérée par l'appelant).
        """

        await self._get_model_info()
        by_id = {e.id_equipement: e for e in per_equip}
        crossovers: list[RiskCrossover] = []
        for eq_id in equipement_ids:
            eq = by_id.get(eq_id)
            if eq is None:
                continue
            risk, probability = _risk_from_mtbf(eq.mtbf_hours)
            crossovers.append(
                RiskCrossover(
                    equipement_id=eq_id,
                    equipement_nom=eq.nom_equipement,
                    predicted_risk=risk,
                    probability_failure=probability,
                    mtbf_hours=eq.mtbf_hours,
                    nb_pannes=eq.nb_pannes,
                    comment=_risk_comment(risk),
                )
            )
        return crossovers

    async def _get_model_info(self) -> dict[str, Any]:
        attempts = max(1, self._settings.ml_retries + 1)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = await self._client.get("/api/v1/model/info")
                if response.status_code == 200:
                    return response.json()
                raise httpx.HTTPStatusError(
                    f"model/info → {response.status_code}",
                    request=response.request,
                    response=response,
                )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt < attempts:
                    await asyncio.sleep(0.2 * attempt)
        raise httpx.ConnectError("GMAO-ML injoignable (enrichissement)", request=None) from last_error


def _risk_from_mtbf(mtbf_hours: float | None) -> tuple[str, float]:
    """Heuristique MTBF → niveau de risque prédictif (0..1)."""

    if mtbf_hours is None:
        return "inconnu", None
    # Plus le MTBF est court, plus le risque est élevé.
    risk_score = 1.0 - min(1.0, mtbf_hours / 2000.0)  # 2000 h = pleine maturité
    for risk, upper in (("faible", 0.25), ("moyen", 0.5), ("eleve", 0.75)):
        if risk_score <= upper:
            return risk, round(risk_score, 3)
    return "critique", round(risk_score, 3)


def _risk_comment(risk: str) -> str:
    return {
        "faible": "Historique de pannes sain, pas d'action préventive urgente.",
        "moyen": "Fiabilité moyenne : surveillance préventive conseillée.",
        "eleve": "Fiabilité dégradée : planifier une visite préventive.",
        "critique": "Risque élevé : intervention préventive prioritaire recommandée.",
        "inconnu": "Données insuffisantes pour évaluer le risque.",
    }.get(risk, "Risque non évalué.")


__all__ = ["MlEnricher", "RISK_ORDER", "_risk_from_mtbf"]

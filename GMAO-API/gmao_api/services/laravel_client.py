"""Construction et livraison des alertes « demande d'intervention » vers Laravel.

Le payload respecte strictement la structure de la table
``demande_interventions`` (voir db/schema_gmao.sql) :

* ``titre`` VARCHAR · ``description`` TEXT ;
* ``priorite`` ENUM(faible|moyenne|elevee|critique) — ici selon P(panne) ;
* ``statut`` ENUM(...) — toujours ``en_attente`` côté IA ;
* ``id_equipement`` INT · ``id_utilisateur`` INT (= utilisateur IA) ;

``date_creation`` est laissé au défaut Laravel/DB, ``date_validation`` non envoyé.

Chaque échange HTTP (requête + réponse + timing) est enregistré dans le
``ChannelJournal`` pour consultation via ``GET /api/v1/channels``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import httpx

from gmao_api.config import Settings
from gmao_api.exceptions import LaravelDeliveryError
from gmao_api.models.schemas import ChannelExchange, SensorReading
from gmao_api.services import equipment_catalog
from gmao_api.services.channel_journal import ChannelJournal
from gmao_api.services.ml_client import positive_probability

logger = logging.getLogger("gmao_api.laravel_client")

PRIORITES_VALIDES = ("faible", "moyenne", "elevee", "critique")
STATUTS_VALIDES = ("en_attente", "validee", "refusee", "en_cours", "terminee")


def build_demande_intervention(
    *,
    reading: SensorReading,
    probability_failure: float,
    model_version: str | None,
    settings: Settings,
    ml_prediction_raw: int = 1,
) -> dict[str, Any]:
    """Construit le payload conforme à la table ``demande_interventions``."""

    equipement = equipment_catalog.get_equipement(reading.equipement_id)
    nom = (
        equipement["nom_equipement"]
        if equipement
        else f"Équipement #{reading.equipement_id}"
    )
    localisation = equipement["localisation"] if equipement else "inconnue"

    priorite = (
        "critique"
        if probability_failure >= settings.critical_probability
        else "elevee"
    )

    titre = f"[IA] Risque de panne détecté — {nom} (#{reading.equipement_id})"
    description = (
        f"Demande générée automatiquement par GMAO-API : le modèle de maintenance "
        f"prédictive prédit un risque de panne (P={probability_failure:.2f}, "
        f"modèle {model_version or 'n/a'}). "
        f"Équipement : {nom} — {localisation}. Relevés : "
        f"T_air={reading.air_temperature_k} K, T_process={reading.process_temperature_k} K, "
        f"RPM={reading.rotational_speed_rpm:.0f}, Torque={reading.torque_nm} Nm, "
        f"Usure outil={reading.tool_wear_min} min."
    )

    return {
        "titre": titre,
        "description": description,
        "priorite": priorite,
        "statut": "en_attente",
        "id_equipement": reading.equipement_id,
        "id_utilisateur": settings.laravel_ia_user_id,
        "_meta": {
            "ml_prediction": ml_prediction_raw,
            "probability_failure": round(probability_failure, 4),
            "model_version": model_version,
        },
    }


class LaravelClient:
    """Livraison des demandes d'intervention.

    Modes de livraison :
    * ``sent``      — POST HTTP réussi vers ``LARAVEL_API_URL`` ;
    * ``simulated`` — ``SIMULATE_LARAVEL=true`` : log structuré, aucun appel ;
    * ``failed``    — appel tenté mais échoué (non bloquant pour le pipeline).

    Chaque échange est enregistré dans le ``ChannelJournal`` si fourni.
    """

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        channel_journal: ChannelJournal | None = None,
    ) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.laravel_api_url,
            timeout=10.0,
            transport=transport,
        )
        self._channel_journal = channel_journal
        self._simulated_interventions: list[dict[str, Any]] = []

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def mode(self) -> str:
        return "simulated" if self._settings.simulate_laravel else "real"

    def _record(
        self,
        *,
        method: str,
        url: str,
        request_body: dict[str, Any] | None,
        response_status: int | None,
        response_body: dict[str, Any] | None,
        duration_ms: float,
        mode: str,
        error: str | None = None,
    ) -> None:
        """Enregistre un échange dans le journal réseau."""
        if self._channel_journal is None:
            return
        self._channel_journal.add(
            ChannelExchange(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                method=method,
                url=url,
                request_body=request_body,
                response_status=response_status,
                response_body=response_body,
                duration_ms=round(duration_ms, 2),
                mode=mode,
                error=error,
            )
        )

    async def send_alert(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        """Envoie la demande. Retourne ``(delivery, response_body|None)`` — ne lève jamais.

        Les clés internes (``_meta``) sont retirées du payload transmis :
        seul le schéma de ``demande_interventions`` part sur le réseau.
        """

        url = self._settings.laravel_alerts_path

        if self._settings.simulate_laravel:
            logger.warning(
                "[SIMULATION LARAVEL] demande_intervention → %s",
                {k: v for k, v in payload.items() if k != "_meta"},
            )
            simulated = {
                "created": True,
                "data": {
                    "id_demande": 0,
                    **{k: v for k, v in payload.items() if k != "_meta"},
                    "date_creation": None,
                },
                "simulated": True,
            }
            self._record(
                method="POST",
                url=url,
                request_body={k: v for k, v in payload.items() if k != "_meta"},
                response_status=201,
                response_body=simulated,
                duration_ms=0.0,
                mode="simulated",
            )
            self._simulated_interventions.append(simulated["data"])
            return "simulated", simulated

        http_payload = {k: v for k, v in payload.items() if not k.startswith("_")}

        t0 = time.monotonic()
        try:
            response = await self._client.post(
                url, json=http_payload, headers={"Content-Type": "application/json"}
            )
            duration_ms = (time.monotonic() - t0) * 1000
        except httpx.HTTPError as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            logger.error("Laravel injoignable : %s", exc)
            self._record(
                method="POST",
                url=url,
                request_body=http_payload,
                response_status=None,
                response_body=None,
                duration_ms=duration_ms,
                mode="failed",
                error=str(exc),
            )
            return "failed", {"error": str(exc)}

        try:
            body: dict[str, Any] | None = response.json()
        except ValueError:
            body = {"raw": response.text[:200]}

        if 200 <= response.status_code < 300:
            self._record(
                method="POST",
                url=url,
                request_body=http_payload,
                response_status=response.status_code,
                response_body=body,
                duration_ms=duration_ms,
                mode="sent",
            )
            return "sent", body

        # Erreur applicative Laravel : non bloquant mais tracé.
        error = LaravelDeliveryError(
            f"Laravel a répondu {response.status_code}.",
            details={"status": response.status_code},
        )
        logger.error("%s", error.message)
        self._record(
            method="POST",
            url=url,
            request_body=http_payload,
            response_status=response.status_code,
            response_body=body,
            duration_ms=duration_ms,
            mode="failed",
            error=error.message,
        )
        return "failed", error.to_body()


    async def fetch_interventions(self) -> dict[str, Any]:
        """Récupère les demandes côté Laravel (proxy lecture pour le dashboard).

        En mode simulated : retourne les interventions stockées en mémoire.
        Ne lève jamais : retourne ``{"reachable": bool, ...}``.
        """

        if self._settings.simulate_laravel:
            return {
                "reachable": True,
                "status": 200,
                "mode": "simulated",
                "body": {
                    "count": len(self._simulated_interventions),
                    "data": self._simulated_interventions,
                },
            }

        url = self._settings.laravel_alerts_path
        t0 = time.monotonic()
        try:
            response = await self._client.get(url)
            duration_ms = (time.monotonic() - t0) * 1000
        except httpx.HTTPError as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            self._record(
                method="GET",
                url=url,
                request_body=None,
                response_status=None,
                response_body=None,
                duration_ms=duration_ms,
                mode="failed",
                error=str(exc),
            )
            return {"reachable": False, "error": str(exc)}

        try:
            body: Any = response.json()
        except ValueError:
            body = {"raw": response.text[:500]}

        self._record(
            method="GET",
            url=url,
            request_body=None,
            response_status=response.status_code,
            response_body=body,
            duration_ms=duration_ms,
            mode="sent",
        )
        return {"reachable": True, "status": response.status_code, "body": body}


__all__ = [
    "LaravelClient",
    "build_demande_intervention",
    "PRIORITES_VALIDES",
    "STATUTS_VALIDES",
    "positive_probability",
]

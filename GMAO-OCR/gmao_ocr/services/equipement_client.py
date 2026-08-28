"""Client HTTP vers l'API Laravel pour l'enrichissement de la fiche équipement.

L'appel est **tolérant aux erreurs** : en cas d'échec (timeout, réseau,
HTTP >= 400), on lève une exception dédiée capturée par la route, qui
retourne alors le lien brut avec ``equipement_details_indisponibles=true``
plutôt qu'une erreur globale.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("gmao_ocr.equipement_client")


class EquipementUnavailableError(Exception):
    """Levée lorsque l'appel Laravel échoue (réseau / timeout / statut)."""


class EquipementNotFoundError(EquipementUnavailableError):
    """Levée lorsque Laravel répond 404 (l'équipement n'existe pas)."""


class LaravelEquipementClient:
    """Client minimal vers l'API Laravel des équipements."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url requis pour LaravelEquipementClient")
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_s,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_equipement(self, equipement_id: int) -> dict:
        """Récupère la fiche équipement depuis Laravel.

        Returns
        -------
        dict
            Le corps JSON de la réponse (attendu : la fiche équipement).

        Raises
        ------
        EquipementUnavailableError
            Si l'API est injoignable, en timeout ou renvoie une erreur.
        """

        client = self._get_client()
        url = f"/api/equipements/{equipement_id}"
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("Laravel injoignable (%s) : %s", url, exc)
            raise EquipementUnavailableError(str(exc)) from exc

        if response.status_code == 404:
            logger.warning("Laravel %s → HTTP 404 (équipement introuvable)", url)
            raise EquipementNotFoundError(f"HTTP {response.status_code}")

        if response.status_code >= 400:
            logger.warning("Laravel %s → HTTP %s", url, response.status_code)
            raise EquipementUnavailableError(f"HTTP {response.status_code}")

        data = response.json()
        if not isinstance(data, dict):
            data = {"data": data}
        return data

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaravelEquipementClient {self._base_url!r}>"


__all__ = ["LaravelEquipementClient", "EquipementUnavailableError", "EquipementNotFoundError"]

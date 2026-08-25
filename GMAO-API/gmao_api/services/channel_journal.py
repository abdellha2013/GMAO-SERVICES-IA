"""Journal réseau des échanges HTTP entre GMAO-API et Laravel.

Chaque requête envoyée (POST / GET) et chaque réponse reçue sont enregistrées
avec timestamp, body complet, status HTTP et latence.  Consultable via
``GET /api/v1/channels`` et affiché dans le dashboard sous « Canal GMAO ↔ Laravel ».
"""

from __future__ import annotations


_MAX_RECORDS = 200


class ChannelJournal:
    """Stockage volatile des échanges HTTP (redémarrage = remise à zéro)."""

    def __init__(self, max_records: int = _MAX_RECORDS) -> None:
        self._exchanges: list = []
        self._max = max_records

    def add(self, exchange) -> None:
        self._exchanges.append(exchange)
        if len(self._exchanges) > self._max:
            self._exchanges = self._exchanges[-self._max:]

    def all(self):
        return list(self._exchanges)

    def __len__(self) -> int:
        return len(self._exchanges)


__all__ = ["ChannelJournal"]

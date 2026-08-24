"""Journal en mémoire des alertes émises (inspection via GET /api/v1/alerts)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from gmao_api.models.schemas import AlertRecord

_MAX_RECORDS = 500


class AlertJournal:
    """Stockage volatile (redémarrage = remise à zéro)."""

    def __init__(self, max_records: int = _MAX_RECORDS) -> None:
        self._records: list[AlertRecord] = []
        self._max = max_records

    def add(
        self,
        *,
        equipement_id: int,
        equipement_nom: str,
        probability_failure: float,
        delivery: str,
        demande_intervention: dict[str, Any],
        laravel_response: dict[str, Any] | None = None,
        model_version: str | None = None,
    ) -> AlertRecord:
        record = AlertRecord(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            equipement_id=equipement_id,
            equipement_nom=equipement_nom,
            probability_failure=round(probability_failure, 4),
            delivery=delivery,
            demande_intervention=demande_intervention,
            laravel_response=laravel_response,
            model_version=model_version,
        )
        self._records.append(record)
        if len(self._records) > self._max:
            self._records = self._records[-self._max :]
        return record

    def all(self) -> list[AlertRecord]:
        return list(self._records)

    def __len__(self) -> int:
        return len(self._records)


__all__ = ["AlertJournal"]

"""Service d'accès à la table ``equipements`` (MySQL, lecture seule).

Charge la liste des équipements depuis la base de données au démarrage,
avec cache en mémoire et fallback sur le catalogue Python si la base
est indisponible.

Usage dans le reste du code : ``app.state.equipment_service``.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from gmao_api.services import equipment_catalog

logger = logging.getLogger("gmao_api.equipment_service")


class EquipmentService:
    """Service de lecture de la table ``equipements``."""

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self._engine = engine
        self._cache: list[dict[str, Any]] | None = None

    # ── API publique ────────────────────────────────────────────

    async def get_all(self) -> list[dict[str, Any]]:
        """Tous les équipements (DB si configurée, sinon catalogue Python)."""

        if self._cache is None:
            await self._reload()
        return list(self._cache) if self._cache else list(equipment_catalog.EQUIPEMENTS)

    async def equipment_ids(self) -> list[int]:
        """Liste des IDs d'équipements pour le simulateur."""

        rows = await self.get_all()
        return [row["id_equipement"] for row in rows]

    async def get_equipement(self, equipement_id: int) -> dict[str, Any] | None:
        """Retourne l'équipement par son ID ou ``None``."""

        rows = await self.get_all()
        return next((r for r in rows if r["id_equipement"] == equipement_id), None)

    async def describe(self, equipement_id: int) -> str:
        """Nom lisible : ``'Tour CNC (#5)'``."""

        eq = await self.get_equipement(equipement_id)
        if eq is None:
            return f"Équipement #{equipement_id}"
        nom = eq.get("nom_equipement") or f"Équipement #{equipement_id}"
        return f"{nom} (#{equipement_id})"

    async def close(self) -> None:
        """Ferme le moteur SQL si présent."""

        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

    # ── Chargement ──────────────────────────────────────────────

    async def _reload(self) -> None:
        """Charge depuis MySQL ; en cas d'échec → fallback catalogue Python."""

        if self._engine is None:
            logger.info("Pas de moteur DB → fallback catalogue Python (%d équipements)", len(equipment_catalog.EQUIPEMENTS))
            self._cache = None
            return

        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT id_equipement, nom_equipement, localisation, "
                        "criticite, etat, marque, modele "
                        "FROM equipements "
                        "ORDER BY id_equipement"
                    )
                )
                self._cache = [dict(row._mapping) for row in result]
            logger.info("Équipements chargés depuis MySQL : %d enregistrement(s)", len(self._cache))
        except Exception as exc:
            logger.warning("Échec lecture MySQL (%s) → fallback catalogue Python", exc)
            self._cache = None

    async def reload(self) -> None:
        """Recharge explicite (utile après modification de la table)."""

        self._cache = None
        await self._reload()


__all__ = ["EquipmentService"]

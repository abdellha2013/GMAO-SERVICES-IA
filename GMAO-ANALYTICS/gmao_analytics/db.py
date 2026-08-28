"""Accès MySQL (lecture seule) aux tables de maintenance.

Reprend le pattern de ``gmao_api.services.equipment_service`` : moteur
SQLAlchemy async, cache mémoire, et fallback sur un référentiel Python
si la base est absente. En revanche, ici l'accès concerne les tables
de maintenance (``pannes``, ``ordre_travails``, ``equipements``) qui
alimentent le calcul MTBF/MTTR.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("gmao_analytics.db")

# Référentiel minimal de repli (12 équipements du schéma de référence).
_CATALOG: list[dict[str, Any]] = [
    {"id_equipement": 1, "nom_equipement": "Compresseur industriel", "localisation": "Atelier A - Zone 1", "criticite": "elevee", "marque": "Atlas Copco", "modele": "GA 75"},
    {"id_equipement": 2, "nom_equipement": "Pompe hydraulique", "localisation": "Atelier A - Zone 2", "criticite": "critique", "marque": "Bosch Rexroth", "modele": "A10VSO"},
    {"id_equipement": 3, "nom_equipement": "Moteur électrique", "localisation": "Ligne de production 1", "criticite": "moyenne", "marque": "Siemens", "modele": "1LE1001"},
    {"id_equipement": 4, "nom_equipement": "Convoyeur industriel", "localisation": "Ligne de production 1", "criticite": "elevee", "marque": "SEW-Eurodrive", "modele": "DRN"},
    {"id_equipement": 5, "nom_equipement": "Tour CNC", "localisation": "Atelier d'usinage", "criticite": "critique", "marque": "Mazak", "modele": "QT-200"},
    {"id_equipement": 6, "nom_equipement": "Fraiseuse CNC", "localisation": "Atelier d'usinage", "criticite": "elevee", "marque": "Haas", "modele": "VF-2"},
    {"id_equipement": 7, "nom_equipement": "Chaudière industrielle", "localisation": "Salle énergétique", "criticite": "critique", "marque": "Bosch", "modele": "Uni 3000"},
    {"id_equipement": 8, "nom_equipement": "Ventilateur industriel", "localisation": "Atelier B - Zone 1", "criticite": "moyenne", "marque": "ABB", "modele": "ACH580"},
    {"id_equipement": 9, "nom_equipement": "Groupe électrogène", "localisation": "Local énergie", "criticite": "critique", "marque": "Caterpillar", "modele": "C18"},
    {"id_equipement": 10, "nom_equipement": "Robot industriel", "localisation": "Ligne robotisée", "criticite": "critique", "marque": "ABB", "modele": "IRB 2600"},
    {"id_equipement": 11, "nom_equipement": "Machine de soudage", "localisation": "Atelier soudage", "criticite": "elevee", "marque": "Fronius", "modele": "TPS 500i"},
    {"id_equipement": 12, "nom_equipement": "Presse hydraulique", "localisation": "Atelier B - Zone 3", "criticite": "critique", "marque": "Schuler", "modele": "HP 500"},
]


class MaintenanceSource:
    """Source de données de maintenance : MySQL si configuré, sinon catalogue vide."""

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self._engine = engine
        self._equipements_cache: list[dict[str, Any]] | None = None

    @property
    def is_mysql(self) -> bool:
        return self._engine is not None

    # ── API publique ────────────────────────────────────────────

    async def equipements(self) -> list[dict[str, Any]]:
        if self._engine is None:
            return list(_CATALOG)
        if self._equipements_cache is None:
            await self._reload_equipements()
        return list(self._equipements_cache) if self._equipements_cache else list(_CATALOG)

    async def panne_df(self) -> pd.DataFrame:
        """Historique des pannes : id_equipement, date_detection."""

        if self._engine is None:
            return pd.DataFrame(columns=["id_equipement", "date_detection"])
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text("SELECT id_equipement, date_detection FROM pannes ORDER BY date_detection")
            )
            return pd.DataFrame([dict(r._mapping) for r in result])

    async def ot_df(self) -> pd.DataFrame:
        """Ordonnances de travail : id_equipement, statut, date_debut, date_fin, temps_reel."""

        if self._engine is None:
            return pd.DataFrame(
                columns=["id_equipement", "statut", "date_debut", "date_fin", "temps_reel"]
            )
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT id_equipement, statut, date_debut, date_fin, temps_reel "
                    "FROM ordre_travails"
                )
            )
            return pd.DataFrame([dict(r._mapping) for r in result])

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

    # ── Chargement ──────────────────────────────────────────────

    async def _reload_equipements(self) -> None:
        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT id_equipement, nom_equipement, localisation, criticite, "
                        "marque, modele FROM equipements ORDER BY id_equipement"
                    )
                )
                self._equipements_cache = [dict(r._mapping) for r in result]
            logger.info("Équipements chargés depuis MySQL : %d", len(self._equipements_cache))
        except Exception as exc:  # pragma: no cover - dépend de l'infra
            logger.warning("Échec lecture équipements MySQL (%s) → catalogue Python", exc)
            self._equipements_cache = None


def recent_cutoff(days: int = 365) -> datetime:
    """Borne temporelle pour les rapports (ex. 12 derniers mois)."""

    return datetime.now() - timedelta(days=days)


__all__ = ["MaintenanceSource", "recent_cutoff"]

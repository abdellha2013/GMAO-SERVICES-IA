"""Fixtures communes aux tests GMAO-ANALYTICS.

Contrairement à GMAO-API, on n'a pas besoin d'un transport HTTP simulant
un modèle : le service fonctionne sur des données de maintenance en
mémoire (source simulée) et un enricheur ML optionnel simulé.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gmao_analytics.api.main import create_app
from gmao_analytics.config import Settings
from gmao_analytics.db import MaintenanceSource


class FakeSource(MaintenanceSource):
    """Source de maintenance en mémoire (pas de MySQL)."""

    def __init__(
        self,
        equipements: list[dict],
        panne_dates: list[tuple[int, datetime]],
        ot_rows: list[dict],
    ) -> None:
        super().__init__(engine=None)
        self._eq = equipements
        self._panne_df = pd.DataFrame(panne_dates, columns=["id_equipement", "date_detection"])
        self._ot_df = pd.DataFrame(ot_rows)

    async def equipements(self):
        return list(self._eq)

    async def panne_df(self):
        return self._panne_df.copy()

    async def ot_df(self):
        return self._ot_df.copy()


def sample_equipements() -> list[dict]:
    return [
        {"id_equipement": 1, "nom_equipement": "Tour CNC", "localisation": "Atelier", "criticite": "critique", "marque": "Mazak", "modele": "QT-200"},
        {"id_equipement": 2, "nom_equipement": "Pompe hydraulique", "localisation": "Atelier A", "criticite": "elevee", "marque": "Bosch", "modele": "A10VSO"},
    ]


def sample_panne_dates() -> list[tuple[int, datetime]]:
    now = datetime.now()
    return [
        (1, now - timedelta(days=100)),
        (1, now - timedelta(days=60)),
        (1, now - timedelta(days=20)),
        (2, now - timedelta(days=80)),
        (2, now - timedelta(days=30)),
    ]


def sample_ot_rows() -> list[dict]:
    now = datetime.now()
    return [
        {"id_equipement": 1, "statut": "termine", "date_debut": now - timedelta(days=99), "date_fin": now - timedelta(days=98), "temps_reel": 240},
        {"id_equipement": 1, "statut": "termine", "date_debut": now - timedelta(days=59), "date_fin": now - timedelta(days=58), "temps_reel": None},
        {"id_equipement": 1, "statut": "planifie", "date_debut": None, "date_fin": None, "temps_reel": None},
        {"id_equipement": 2, "statut": "termine", "date_debut": now - timedelta(days=79), "date_fin": now - timedelta(days=78), "temps_reel": 360},
        {"id_equipement": 2, "statut": "termine", "date_debut": now - timedelta(days=29), "date_fin": now - timedelta(days=28), "temps_reel": 600},
    ]


def make_settings(**overrides):
    base = dict(
        api_host="127.0.0.1",
        api_port=8300,
        maintenance_db_url=None,
        ml_api_url="http://ml.test",
        ml_timeout_s=5.0,
        ml_retries=0,
    )
    base.update(overrides)
    return Settings(**base)


def make_app(equipements=None, panne_dates=None, ot_rows=None, ml_handler=None, ml_api_url="http://ml.test"):
    from gmao_analytics.api.main import create_app as _create_app

    settings = make_settings(ml_api_url=ml_api_url)
    source = FakeSource(
        equipements=equipements or sample_equipements(),
        panne_dates=panne_dates or sample_panne_dates(),
        ot_rows=ot_rows or sample_ot_rows(),
    )
    transport = None
    if ml_handler is not None:
        import httpx

        transport = httpx.MockTransport(ml_handler)
    return _create_app(settings, source=source, ml_transport=transport)


def fake_ml_handler():
    def handler(request):
        import httpx

        if request.url.path == "/api/v1/model/info":
            return httpx.Response(200, json={"model_name": "gmao_state_classifier", "model_version": "test-v1"})
        return httpx.Response(404)

    return handler


@pytest.fixture()
def client():
    with TestClient(make_app()) as test_client:
        yield test_client


@pytest.fixture()
def client_with_ml():
    with TestClient(make_app(ml_handler=fake_ml_handler())) as test_client:
        yield test_client

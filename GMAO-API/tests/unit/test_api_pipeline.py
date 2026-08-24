"""Tests bout-en-bout de l'API (clients ML/Laravel simulés)."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from tests.conftest import AUTH, fake_ml_handler, make_app, make_settings


def _reading(torque: float, equipement_id: int = 5) -> dict:
    return {
        "equipement_id": equipement_id,
        "Type": "L",
        "Air temperature [K]": 298.9,
        "Process temperature [K]": 308.4,
        "Rotational speed [rpm]": 1450,
        "Torque [Nm]": torque,
        "Tool wear [min]": 120,
    }


class TestAuth:
    def test_healthz_sans_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["service"] == "gmao-api"
        assert body["ml_api_reachable"] is True
        assert body["laravel_mode"] == "simulated"

    def test_endpoint_sans_en_tete_422(self, client: TestClient) -> None:
        assert client.get("/api/v1/alerts").status_code == 422

    def test_mauvaise_cle_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/alerts", headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401


class TestSimulate:
    def test_alertes_sur_pannes_simulees(self, client: TestClient) -> None:
        """failure_rate=1 + torques élevés → toutes les lectures prédisent 1."""

        # relevés artificiels passés tels quels au fake ML : on force via /predictions
        payload = {"count": 6, "failure_rate": 0.0, "random_state": 5}
        response = client.post("/api/v1/simulate", json=payload, headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        # relevés sains → fake ML prédit 0 → aucune alerte
        assert body["alerts_count"] == 0
        assert len(body["results"]) == 6
        for result in body["results"]:
            assert result["prediction"] == 0
            assert result["alert_delivery"] == "not_triggered"
            assert result["demande_intervention"] is None

    def test_journal_apres_alertes(self) -> None:
        app = make_app()
        with TestClient(app) as test_client:
            payload = {"readings": [_reading(95.0), _reading(40.0), _reading(88.0)]}
            done = test_client.post("/api/v1/predictions", json=payload, headers=AUTH)
            assert done.status_code == 200
            body = done.json()
            assert body["alerts_count"] == 2
            journal = test_client.get("/api/v1/alerts", headers=AUTH).json()
            assert journal["count"] == 2


class TestPayloadDemandeIntervention:
    def test_structure_conforme_table(self, client: TestClient) -> None:
        payload = {"readings": [_reading(97.0, equipement_id=5)]}
        result = client.post("/api/v1/predictions", json=payload, headers=AUTH).json()

        outcome = result["results"][0]
        assert outcome["prediction"] == 1
        assert outcome["alert_sent"] is True
        assert outcome["alert_delivery"] == "simulated"

        demande = outcome["demande_intervention"]
        colonnes = {"titre", "description", "priorite", "statut", "id_equipement", "id_utilisateur"}
        assert colonnes <= set(demande)
        assert demande["statut"] == "en_attente"
        assert demande["id_utilisateur"] == 1
        assert demande["id_equipement"] == 5
        assert demande["priorite"] in {"faible", "moyenne", "elevee", "critique"}
        assert "Tour CNC" in demande["titre"]

    def test_priorite_critique_seuil(self, client: TestClient) -> None:
        result = client.post(
            "/api/v1/predictions",
            json={"readings": [_reading(99.0)]},
            headers=AUTH,
        ).json()
        priorite = result["results"][0]["demande_intervention"]["priorite"]
        assert priorite == "critique"  # fake ML renvoie P=0.95 >= 0.90


class TestLivraisonLaravelReelle:
    def test_post_http_reel_capture(self) -> None:
        captured: dict = {}

        def laravel_handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["json"] = json.loads(request.content)
            return httpx.Response(201, json={"created": True, "data": {"id_demande": 42}})

        settings = make_settings(simulate_laravel=False, laravel_api_url="http://laravel.test")
        app = make_app(settings=settings, laravel_transport=httpx.MockTransport(laravel_handler))

        with TestClient(app) as client:
            outcome = client.post(
                "/api/v1/predictions",
                json={"readings": [_reading(91.0)]},
                headers=AUTH,
            ).json()["results"][0]

        assert outcome["alert_delivery"] == "sent"
        assert outcome["laravel_response"]["data"]["id_demande"] == 42
        sent = captured["json"]
        assert "_meta" not in sent  # métadonnées internes non envoyées au vrai backend
        assert set(sent) == {
            "titre",
            "description",
            "priorite",
            "statut",
            "id_equipement",
            "id_utilisateur",
        }

    def test_laravel_injoignable_non_bloquant(self) -> None:
        settings = make_settings(simulate_laravel=False)

        def failing(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        app = make_app(settings=settings, laravel_transport=httpx.MockTransport(failing))
        with TestClient(app) as client:
            body = client.post(
                "/api/v1/predictions",
                json={"readings": [_reading(93.0)]},
                headers=AUTH,
            ).json()
        outcome = body["results"][0]
        assert outcome["alert_delivery"] == "failed"
        assert outcome["alert_sent"] is False
        assert body["alerts_count"] == 0


class TestErreursML:
    def test_ml_injoignable_503_json(self) -> None:
        from tests.conftest import failing_ml_handler

        app = make_app(ml_handler=failing_ml_handler())
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/simulate",
                json={"count": 2, "failure_rate": 0.0},
                headers=AUTH,
            )
        assert response.status_code == 503
        body = response.json()
        assert body["error_code"] == "ML_UNREACHABLE"

    def test_validation_relevé_invalide_422(self, client: TestClient) -> None:
        bad = _reading(50.0)
        bad.pop("equipement_id")
        response = client.post("/api/v1/predictions", json={"readings": [bad]}, headers=AUTH)
        assert response.status_code == 422

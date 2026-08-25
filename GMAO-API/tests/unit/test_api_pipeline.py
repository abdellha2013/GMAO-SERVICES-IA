"""Tests bout-en-bout de l'API (client ML simulé)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import failing_ml_handler, fake_ml_handler, make_app, make_settings


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


class TestHealthz:
    def test_healthz(self, client: TestClient) -> None:
        response = client.get("/api/v1/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["service"] == "gmao-api"
        assert body["ml_api_reachable"] is True


class TestPredictions:
    def test_panne_predite_haute_probabilite(self, client: TestClient) -> None:
        payload = {"readings": [_reading(95.0)]}
        response = client.post("/api/v1/predictions", json=payload)
        assert response.status_code == 200
        body = response.json()
        outcome = body["results"][0]
        assert outcome["prediction"] == 1
        assert outcome["probability_failure"] == 0.95
        assert outcome["model_version"] == "test-v1"

    def test_saine_faible_probabilite(self, client: TestClient) -> None:
        payload = {"readings": [_reading(40.0)]}
        response = client.post("/api/v1/predictions", json=payload)
        assert response.status_code == 200
        outcome = response.json()["results"][0]
        assert outcome["prediction"] == 0
        assert outcome["probability_failure"] == 0.02

    def test_plusieurs_releves(self, client: TestClient) -> None:
        payload = {"readings": [_reading(95.0), _reading(40.0), _reading(88.0)]}
        response = client.post("/api/v1/predictions", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert len(body["results"]) == 3
        predictions = [r["prediction"] for r in body["results"]]
        assert predictions == [1, 0, 1]

    def test_validation_releve_invalide_422(self, client: TestClient) -> None:
        bad = _reading(50.0)
        bad.pop("equipement_id")
        response = client.post("/api/v1/predictions", json={"readings": [bad]})
        assert response.status_code == 422


class TestSimulate:
    def test_simulate_retourne_resultats(self, client: TestClient) -> None:
        payload = {"count": 6, "failure_rate": 0.0, "random_state": 5}
        response = client.post("/api/v1/simulate", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert len(body["results"]) == 6
        for result in body["results"]:
            assert result["prediction"] == 0

    def test_simulate_retourne_readings(self, client: TestClient) -> None:
        payload = {"count": 3, "failure_rate": 0.5, "random_state": 42}
        response = client.post("/api/v1/simulate", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["readings"] is not None
        assert len(body["readings"]) == 3
        for reading in body["readings"]:
            assert "equipement_id" in reading
            assert "Torque [Nm]" in reading


class TestErreursML:
    def test_ml_injoignable_503_json(self) -> None:
        app = make_app(ml_handler=failing_ml_handler())
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/simulate",
                json={"count": 2, "failure_rate": 0.0},
            )
        assert response.status_code == 503
        body = response.json()
        assert body["error_code"] == "ML_UNREACHABLE"

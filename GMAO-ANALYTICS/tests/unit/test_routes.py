"""Tests des routes API de GMAO-ANALYTICS."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    fake_ml_handler,
    make_app,
    sample_equipements,
    sample_ot_rows,
    sample_panne_dates,
)


class TestHealthz:
    def test_healthz(self, client: TestClient) -> None:
        response = client.get("/api/v1/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["service"] == "gmao-analytics"
        assert body["equipements_count"] == 2


class TestMetrics:
    def test_metrics_global_et_per_equipement(self, client: TestClient) -> None:
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200
        body = response.json()
        assert len(body["per_equipement"]) == 2
        global_ = body["global"]
        assert global_["nb_pannes"] == 5
        assert global_["nb_interventions"] == 4
        assert global_["mtbf_hours"] is not None
        assert global_["mttr_hours"] > 0

    def test_metrics_par_equipement_filtre(self, client: TestClient) -> None:
        response = client.get("/api/v1/metrics/equipement/1")
        assert response.status_code == 200
        body = response.json()
        assert len(body["per_equipement"]) == 1
        assert body["per_equipement"][0]["id_equipement"] == 1

    def test_metrics_equipement_inconnu_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/metrics/equipement/999")
        assert response.status_code == 404

    def test_metrics_equipements_alias(self, client: TestClient) -> None:
        response = client.get("/api/v1/metrics/equipements")
        assert response.status_code == 200
        assert "per_equipement" in response.json()


class TestReport:
    def test_report_json(self, client: TestClient) -> None:
        response = client.get("/api/v1/report")
        assert response.status_code == 200
        body = response.json()
        assert "global_metrics" in body
        assert "per_equipement" in body
        assert "text" in body
        assert body["global_metrics"]["nb_pannes"] == 5

    def test_report_markdown(self, client: TestClient) -> None:
        response = client.get("/api/v1/report?format=markdown")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert "# Rapport de maintenance" in response.text

    def test_report_csv(self, client: TestClient) -> None:
        response = client.get("/api/v1/report?format=csv")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "nom_equipement" in response.text


class TestReportAvecML:
    def test_report_enrichi_risque(self) -> None:
        app = make_app(ml_handler=fake_ml_handler())
        with TestClient(app) as client:
            response = client.get("/api/v1/report")
        assert response.status_code == 200
        body = response.json()
        assert body["risk"] is not None
        assert len(body["risk"]) == 2
        risk_risks = {r["predicted_risk"] for r in body["risk"]}
        assert risk_risks <= {"faible", "moyen", "eleve", "critique", "inconnu"}


class TestOpenapi:
    def test_routes_documentees(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/metrics" in paths
        assert "/api/v1/report" in paths
        assert "/api/v1/healthz" in paths

    def test_dashboard_hors_schema(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/" not in paths


class TestDashboard:
    def test_racine_sert_le_html(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "GMAO" in response.text
        assert 'API = "/api/v1"' in response.text

"""Tests du dashboard (GET /)."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestDashboard:
    def test_racine_sert_le_html(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "GMAO-API" in response.text
        assert "Dashboard de test" in response.text
        assert "Démarrer" in response.text
        assert "toggleRun" in response.text

    def test_racine_absente_de_l_openapi(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/" not in paths

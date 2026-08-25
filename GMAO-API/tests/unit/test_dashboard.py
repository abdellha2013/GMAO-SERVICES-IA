"""Tests du dashboard (GET /) et du proxy boîte de réception Laravel."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from tests.conftest import AUTH, make_app


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


class TestInboxLaravel:
    def test_auth_requise(self, client: TestClient) -> None:
        assert client.get("/api/v1/laravel/interventions").status_code == 401

    def test_backend_injoignable_reponse_degradee(self) -> None:
        def failing(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        app = make_app(laravel_transport=httpx.MockTransport(failing))
        with TestClient(app) as test_client:
            body = test_client.get(
                "/api/v1/laravel/interventions", headers=AUTH
            ).json()
        assert body["reachable"] is True
        assert body["mode"] == "simulated"
        assert body["body"]["data"] == []

    def test_proxy_lecture_mode_reel(self) -> None:
        def laravel_handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/intervention-requests"
            return httpx.Response(200, json={"data": [{"id_demande": 7, "priorite": "critique"}]})

        from tests.conftest import make_settings

        settings = make_settings(simulate_laravel=False)
        app = make_app(
            settings=settings,
            laravel_transport=httpx.MockTransport(laravel_handler),
        )
        with TestClient(app) as test_client:
            body = test_client.get(
                "/api/v1/laravel/interventions", headers=AUTH
            ).json()
        assert body["mode"] == "real"
        assert body["reachable"] is True
        assert body["body"]["data"][0]["id_demande"] == 7

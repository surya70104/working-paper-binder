"""The API starts and answers the health check without touching a database."""

from __future__ import annotations

from fastapi.testclient import TestClient

from oak_binder import __version__


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "module": "working-paper-binder",
        "version": __version__,
    }

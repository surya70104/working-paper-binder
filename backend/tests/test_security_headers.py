"""Every response carries the headers that keep audit-file content out of caches and away
from browser type-guessing (D24). No database: the health check is enough."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_every_response_is_uncacheable_and_unsniffable(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    missing = client.get("/api/binders/not-a-uuid")
    assert missing.status_code == 422
    assert missing.headers["Cache-Control"] == "no-store"

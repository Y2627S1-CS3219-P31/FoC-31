# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""User-service onboarding to the shared observability layer."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.observability import OBS

CLIENT = {"X-User-Id": "user1", "X-User-Role": "client"}


def _client() -> TestClient:
    return TestClient(app)


def test_metrics_endpoint_exposes_prefixed_families():
    client = _client()
    client.get("/users/me", headers=CLIENT)
    body = client.get("/metrics").text

    assert "user_http_requests_total" in body
    assert 'service="user-service"' in body
    assert 'route="/users/me"' in body


def test_readiness_checks_the_database_only():
    client = _client()
    resp = client.get("/health/ready")
    body = resp.json()

    # user-service publishes through an outbox and holds no consumer
    # connection, so readiness is DB-only instead of permanently degraded.
    assert resp.status_code == 200
    assert body["status"] == "ready"
    assert body["checks"] == {"database": "ok"}


def test_request_id_is_echoed():
    client = _client()
    resp = client.get("/users/me", headers={**CLIENT, "x-request-id": "trace-9"})
    assert resp.headers["x-request-id"] == "trace-9"
    # The request is recorded under its route template regardless of the status
    # code (this fixture has no matching user row, so it is a 4xx).
    rows = OBS.table(OBS.http_requests)
    assert any(row.get("route") == "/users/me" for row in rows)

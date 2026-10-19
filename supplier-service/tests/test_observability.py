# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Supplier-service onboarding to the shared observability layer."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app
from app.observability import OBS

CLIENT = {"X-User-Id": "user1", "X-User-Role": "client"}


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[TestClient, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
    await engine.dispose()


def test_metrics_endpoint_exposes_prefixed_families(client):
    client.get("/suppliers", headers=CLIENT)
    body = client.get("/metrics").text

    assert "supplier_http_requests_total" in body
    assert 'service="supplier-service"' in body
    # Route templates, never raw ids.
    assert 'route="/suppliers"' in body


def test_error_envelope_code_is_counted(client):
    before = OBS.value(OBS.http_errors, code="not_found")

    resp = client.get("/suppliers/does-not-exist", headers=CLIENT)
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"

    assert OBS.value(OBS.http_errors, code="not_found") == before + 1


def test_readiness_reports_database_and_broker(client):
    resp = client.get("/health/ready")
    body = resp.json()

    # The broker is not connected in unit tests, so readiness is degraded but
    # the database check still runs.
    assert resp.status_code == 503
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["broker"] == "unavailable"


def test_request_id_is_echoed(client):
    resp = client.get("/suppliers", headers={**CLIENT, "x-request-id": "trace-7"})
    assert resp.headers["x-request-id"] == "trace-7"

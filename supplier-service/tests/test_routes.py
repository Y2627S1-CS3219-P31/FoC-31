from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app

ADMIN = {"X-User-Id": "admin1", "X-User-Role": "admin"}
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
    # Do not enter the lifespan context: tables are created above against the
    # in-memory engine, so we avoid init_db() hitting a real Postgres.
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
    await engine.dispose()


def _create(client: TestClient, **overrides) -> dict:
    body = {"name": "Cool Spot", "category": "Food", "building": "Com2"}
    body.update(overrides)
    resp = client.post("/api/suppliers", json=body, headers=ADMIN)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_requires_admin(client):
    resp = client.post(
        "/api/suppliers",
        json={"name": "X", "category": "Food", "building": "Y"},
        headers=CLIENT,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_create_requires_auth(client):
    resp = client.post("/api/suppliers", json={"name": "X", "category": "Food", "building": "Y"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


def test_create_returns_201_camelcase(client):
    created = _create(client, locationDescription="Opp LT16")
    assert created["id"].startswith("sup_")
    assert created["active"] is True
    assert created["locationDescription"] == "Opp LT16"


def test_create_validation_error(client):
    resp = client.post(
        "/api/suppliers", json={"name": "X", "category": "Drinks", "building": "Y"}, headers=ADMIN
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_get_detail_and_404(client):
    created = _create(client)
    ok = client.get(f"/api/suppliers/{created['id']}", headers=CLIENT)
    assert ok.status_code == 200
    assert ok.json()["id"] == created["id"]

    missing = client.get("/api/suppliers/sup_missing", headers=CLIENT)
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
    assert "sup_missing" in missing.json()["message"]


def test_list_pagination_envelope(client):
    for i in range(3):
        _create(client, name=f"Spot {i}")
    resp = client.get("/api/suppliers?page=1&page_size=2", headers=CLIENT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["pageSize"] == 2
    assert len(body["items"]) == 2


def test_list_filter_and_search(client):
    _create(client, name="Anna's Soup", category="Food", building="Central Library")
    _create(client, name="NUS Co-op", category="Shopping", building="Central Library")

    by_cat = client.get("/api/suppliers?category=Shopping", headers=CLIENT).json()
    assert by_cat["total"] == 1

    by_zone = client.get("/api/suppliers?zone=Central", headers=CLIENT).json()
    assert by_zone["total"] == 2

    by_q = client.get("/api/suppliers?q=soup", headers=CLIENT).json()
    assert by_q["total"] == 1


def test_list_excludes_deactivated(client):
    created = _create(client)
    client.post(f"/api/suppliers/{created['id']}/deactivate", headers=ADMIN)
    listing = client.get("/api/suppliers", headers=CLIENT).json()
    assert listing["total"] == 0


def test_update_admin_only(client):
    created = _create(client)
    forbidden = client.patch(
        f"/api/suppliers/{created['id']}", json={"name": "New"}, headers=CLIENT
    )
    assert forbidden.status_code == 403

    ok = client.patch(f"/api/suppliers/{created['id']}", json={"name": "New"}, headers=ADMIN)
    assert ok.status_code == 200
    assert ok.json()["name"] == "New"


def test_update_missing_404(client):
    resp = client.patch("/api/suppliers/sup_missing", json={"name": "New"}, headers=ADMIN)
    assert resp.status_code == 404


def test_deactivate_flow(client):
    created = _create(client)
    ok = client.post(f"/api/suppliers/{created['id']}/deactivate", headers=ADMIN)
    assert ok.status_code == 200
    assert ok.json()["active"] is False

    conflict = client.post(f"/api/suppliers/{created['id']}/deactivate", headers=ADMIN)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "conflict"

    # still retrievable
    detail = client.get(f"/api/suppliers/{created['id']}", headers=CLIENT)
    assert detail.status_code == 200
    assert detail.json()["active"] is False


def test_deactivate_missing_404(client):
    resp = client.post("/api/suppliers/sup_missing/deactivate", headers=ADMIN)
    assert resp.status_code == 404

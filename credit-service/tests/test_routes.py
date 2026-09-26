# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app
from app.services.credit_service import CreditService

ADMIN = {"X-User-Id": "admin-1", "X-User-Role": "admin"}
CLIENT = {"X-User-Id": "user-1", "X-User-Role": "client"}


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[TestClient, None]:
    from app import models  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    async with maker() as s:
        await CreditService(s).ensure_account("user-1")
        await CreditService(s).ensure_account("user-2")

    # Do not enter the lifespan context: no Postgres init, no RabbitMQ consumer.
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
    await engine.dispose()


def _reserve(client: TestClient, *, amount: int = 30, order_id: str = "order-1"):
    resp = client.post(
        "/credits/reservations",
        json={"user_id": "user-1", "order_id": order_id, "amount": amount},
        headers=CLIENT,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── balance (F1.3 / F1.4) ──────────────────────────────────────────────────


def test_balance_requires_authentication(client):
    resp = client.get("/credits/user-1/balance")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


def test_balance_returns_own_available_and_reserved(client):
    _reserve(client, amount=30)
    resp = client.get("/credits/user-1/balance", headers=CLIENT)
    assert resp.status_code == 200
    assert resp.json() == {
        "user_id": "user-1",
        "available_balance": 70,
        "reserved_balance": 30,
    }


def test_balance_of_other_user_forbidden_for_client(client):
    resp = client.get("/credits/user-2/balance", headers=CLIENT)
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_balance_of_other_user_allowed_for_admin(client):
    resp = client.get("/credits/user-2/balance", headers=ADMIN)
    assert resp.status_code == 200
    assert resp.json()["available_balance"] == 100


def test_balance_unknown_user_404(client):
    resp = client.get("/credits/ghost/balance", headers=ADMIN)
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


# ── reservation (F2) ───────────────────────────────────────────────────────


def test_reserve_creates_reservation(client):
    created = _reserve(client, amount=30)
    assert created["status"] == "reserved"
    assert created["amount"] == 30
    assert created["user_id"] == "user-1"
    assert created["order_id"] == "order-1"


def test_reserve_requires_authentication(client):
    resp = client.post(
        "/credits/reservations",
        json={"user_id": "user-1", "order_id": "order-1", "amount": 30},
    )
    assert resp.status_code == 401


def test_reserve_for_other_user_forbidden(client):
    resp = client.post(
        "/credits/reservations",
        json={"user_id": "user-2", "order_id": "order-1", "amount": 30},
        headers=CLIENT,
    )
    assert resp.status_code == 403


def test_reserve_insufficient_credits(client):
    resp = client.post(
        "/credits/reservations",
        json={"user_id": "user-1", "order_id": "order-1", "amount": 999},
        headers=CLIENT,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "insufficient_credits"


def test_reserve_validation_error(client):
    resp = client.post(
        "/credits/reservations",
        json={"user_id": "user-1", "order_id": "order-1", "amount": 0},
        headers=CLIENT,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ── amendment (F2.3) ───────────────────────────────────────────────────────


def test_amend_reservation(client):
    created = _reserve(client, amount=30)
    resp = client.post(
        f"/credits/reservations/{created['id']}/amend",
        json={"amount": 50},
        headers=CLIENT,
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == 50
    balance = client.get("/credits/user-1/balance", headers=CLIENT).json()
    assert balance["available_balance"] == 50
    assert balance["reserved_balance"] == 50


def test_amend_by_non_owner_forbidden(client):
    created = _reserve(client)
    resp = client.post(
        f"/credits/reservations/{created['id']}/amend",
        json={"amount": 50},
        headers={"X-User-Id": "user-2", "X-User-Role": "client"},
    )
    assert resp.status_code == 403


# ── transfer (F3) ──────────────────────────────────────────────────────────


def test_transfer_to_courier(client):
    created = _reserve(client, amount=30)
    resp = client.post(
        f"/credits/reservations/{created['id']}/transfer",
        json={"courier_id": "user-2"},
        headers=CLIENT,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "transferred"

    courier = client.get("/credits/user-2/balance", headers=ADMIN).json()
    assert courier["available_balance"] == 130


def test_transfer_is_idempotent(client):
    created = _reserve(client, amount=30)
    for _ in range(2):
        resp = client.post(
            f"/credits/reservations/{created['id']}/transfer",
            json={"courier_id": "user-2"},
            headers=CLIENT,
        )
        assert resp.status_code == 200
    courier = client.get("/credits/user-2/balance", headers=ADMIN).json()
    assert courier["available_balance"] == 130  # not 160


# ── release (F4) ───────────────────────────────────────────────────────────


def test_release_returns_credits(client):
    created = _reserve(client, amount=30)
    resp = client.post(f"/credits/reservations/{created['id']}/release", headers=CLIENT)
    assert resp.status_code == 200
    assert resp.json()["status"] == "released"
    balance = client.get("/credits/user-1/balance", headers=CLIENT).json()
    assert balance["available_balance"] == 100
    assert balance["reserved_balance"] == 0


# ── history (F5.2) ─────────────────────────────────────────────────────────


def test_transaction_history(client):
    _reserve(client, amount=30)
    resp = client.get("/credits/user-1/transactions", headers=CLIENT)
    assert resp.status_code == 200
    kinds = sorted(t["kind"] for t in resp.json())
    assert kinds == ["allocation", "reservation"]
    reservation = next(t for t in resp.json() if t["kind"] == "reservation")
    assert reservation["amount"] == -30
    assert reservation["order_id"] == "order-1"


def test_transaction_history_of_other_user_forbidden(client):
    resp = client.get("/credits/user-2/transactions", headers=CLIENT)
    assert resp.status_code == 403

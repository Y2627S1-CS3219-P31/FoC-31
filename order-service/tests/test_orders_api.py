# AI-INFLUENCED: Sprint 1 Order Service API tests generated with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.error_handlers import register_exception_handlers
from app.api.routes import orders as order_routes
from app.db import get_session
from app.services.errors import (
    OrderAccessDeniedError,
    OrderNotFoundError,
    OrderStateConflictError,
)
from app.services.lifecycle import OrderStatus


@pytest.fixture
def fake_session() -> object:
    return object()


@pytest.fixture
def client(fake_session: object):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(order_routes.router)

    async def override_get_session():
        yield fake_session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _payload() -> dict[str, Any]:
    return {
        "name": "Collect lunch",
        "details": "One vegetarian rice bowl",
        "reward": 5,
        "deadline": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        "supplier_id": "sup_001",
        "pickup_location": "The Deck",
        "delivery_location": "COM3",
    }


def _stored_order(
    *,
    order_id: str = "order-1",
    requester_id: str = "user-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        order_id=order_id,
        requester_id=requester_id,
        courier_id=None,
        status=OrderStatus.OPEN,
        created_at=datetime.now(UTC),
        **_payload(),
    )


def test_create_order_returns_created_order(
    client: TestClient,
    fake_session: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_create_order(*, new_order, requester_id, session):
        assert new_order.name == "Collect lunch"
        assert requester_id == "user-1"
        assert session is fake_session
        return _stored_order(requester_id=requester_id)

    monkeypatch.setattr(order_routes.order_service, "create_order", fake_create_order)

    response = client.post(
        "/orders",
        headers={"X-User-Id": "user-1"},
        json=_payload(),
    )

    assert response.status_code == 201
    assert response.json()["order_id"] == "order-1"
    assert response.json()["status"] == "OPEN"


def test_list_orders_returns_available_orders(
    client: TestClient,
    fake_session: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list_orders(session, requester_id):
        assert session is fake_session
        assert requester_id == "courier-1"
        return [_stored_order(requester_id="user-1")]

    monkeypatch.setattr(
        order_routes.order_service,
        "list_available_orders",
        fake_list_orders,
    )

    response = client.get("/orders", headers={"X-User-Id": "courier-1"})

    assert response.status_code == 200
    assert [order["order_id"] for order in response.json()] == ["order-1"]


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (OrderNotFoundError("order-1"), 404, "order_not_found"),
        (OrderAccessDeniedError("order-1"), 403, "order_access_denied"),
    ],
)
def test_get_order_uses_centralized_error_handler(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    async def fake_get_order(_session, _order_id, _requester_id):
        raise error

    monkeypatch.setattr(
        order_routes.order_service,
        "get_order_for_requester",
        fake_get_order,
    )

    response = client.get("/orders/order-1", headers={"X-User-Id": "user-1"})

    assert response.status_code == status_code
    assert response.json()["code"] == code


def test_delete_order_returns_no_content(
    client: TestClient,
    fake_session: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_delete_order(session, order_id, requester_id):
        assert session is fake_session
        assert order_id == "order-1"
        assert requester_id == "user-1"

    monkeypatch.setattr(
        order_routes.order_service,
        "delete_order_for_requester",
        fake_delete_order,
    )

    response = client.delete(
        "/orders/order-1",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 204
    assert response.content == b""


def test_delete_order_uses_state_conflict_handler(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_delete_order(_session, order_id, _requester_id):
        raise OrderStateConflictError(order_id, "Order cannot be deleted.")

    monkeypatch.setattr(
        order_routes.order_service,
        "delete_order_for_requester",
        fake_delete_order,
    )

    response = client.delete(
        "/orders/order-1",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "invalid_order_state",
        "message": "Order cannot be deleted.",
    }

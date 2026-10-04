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


def test_list_orders_returns_requester_orders(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list(_session, requester_id):
        assert requester_id == "user-1"
        return [stored_order(requester_id=requester_id)]

    monkeypatch.setattr(order_routes.order_service, "list_requester_orders", fake_list)

    response = client.get("/orders", headers={"X-User-Id": "user-1"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1]
    assert all(item["requester_id"] == "user-1" for item in response.json())


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_code"),
    [
        (
            order_routes.order_service.SupplierNotFoundError("Supplier 'missing' was not found."),
            422,
            "supplier_not_found",
        ),
        (
            order_routes.order_service.SupplierInactiveError("Supplier 'sup_001' is deactivated."),
            409,
            "supplier_inactive",
        ),
        (
            order_routes.order_service.CreditReservationError("Insufficient credits."),
            409,
            "credit_reservation_failed",
        ),
    ],
)
def test_create_order_maps_business_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    service_error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    async def fake_create(*_args):
        raise service_error

    monkeypatch.setattr(order_routes.order_service, "create_order", fake_create)

    response = client.post(
        "/orders",
        headers={"X-User-Id": "user-1"},
        json=order_payload(),
    )

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code


def test_create_order_maps_dependency_failure_to_service_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_create(*_args):
        raise order_routes.order_service.DependencyUnavailableError(
            "credit",
            "Credit Service could not be reached.",
        )

    monkeypatch.setattr(order_routes.order_service, "create_order", fake_create)

    response = client.post(
        "/orders",
        headers={"X-User-Id": "user-1"},
        json=order_payload(),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "credit_service_unavailable"


def test_get_order_maps_access_denial_to_error_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(_session, order_id, _requester_id):
        raise order_routes.order_service.OrderAccessDeniedError(order_id)

    monkeypatch.setattr(order_routes.order_service, "get_order_for_requester", fake_get)

    response = client.get("/orders/1", headers={"X-User-Id": "user-2"})

    assert response.status_code == 403
    assert response.json() == {
        "code": "forbidden",
        "message": "You do not have permission to access order '1'.",
    }


def test_delete_order_returns_no_content(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_delete(_session, order_id, requester_id):
        assert order_id == 1
        assert requester_id == "user-1"

    monkeypatch.setattr(order_routes.order_service, "delete_order_for_requester", fake_delete)

    response = client.delete("/orders/1", headers={"X-User-Id": "user-1"})

    assert response.status_code == 204
    assert response.content == b""

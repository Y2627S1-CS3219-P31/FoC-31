# AI-INFLUENCED: Sprint 1 Order Service API tests generated with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.error_handlers import register_exception_handlers
from app.api.routes import orders as order_routes
from app.db import get_session
from app.services.errors import (
    OrderAcceptanceError,
    OrderAccessDeniedError,
    OrderDeliveryError,
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


def test_accept_uses_gateway_identity(client, fake_session, monkeypatch):
    order = _stored_order()
    order.courier_id = "courier-1"
    order.status = OrderStatus.ACCEPTED
    accept = AsyncMock(return_value=order)
    monkeypatch.setattr(order_routes.order_service, "accept_order", accept)
    response = client.post(
        "/orders/order-1/accept",
        headers={"X-User-Id": "courier-1", "X-User-Role": "client"},
        json={"courier_id": "someone-else", "role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["courier_id"] == "courier-1"
    assert response.json()["status"] == "ACCEPTED"
    accept.assert_awaited_once_with(fake_session, "order-1", "courier-1")


def test_withdraw_requires_and_forwards_idempotency_key(client, fake_session, monkeypatch):
    order = _stored_order()
    withdraw = AsyncMock(return_value=order)
    monkeypatch.setattr(order_routes.order_service, "withdraw_order", withdraw)
    headers = {"X-User-Id": "courier-1", "X-User-Role": "client"}

    missing = client.post("/orders/order-1/withdraw", headers=headers)
    assert missing.status_code == 422
    withdraw.assert_not_awaited()

    response = client.post(
        "/orders/order-1/withdraw",
        headers={**headers, "Idempotency-Key": "withdrawal-1"},
    )
    assert response.status_code == 200
    withdraw.assert_awaited_once_with(fake_session, "order-1", "courier-1", "withdrawal-1")


def test_pickup_uses_gateway_courier_identity(client, fake_session, monkeypatch):
    order = _stored_order()
    order.courier_id = "courier-1"
    order.status = OrderStatus.PICKED_UP
    pickup = AsyncMock(return_value=order)
    monkeypatch.setattr(order_routes.order_service, "pickup_order", pickup)

    response = client.post(
        "/orders/order-1/pickup",
        headers={"X-User-Id": "courier-1", "X-User-Role": "client"},
    )
    assert response.status_code == 200
    pickup.assert_awaited_once_with(fake_session, "order-1", "courier-1")


@pytest.mark.parametrize("role", ["client", "admin"])
def test_deliver_accepts_both_gateway_roles(client, fake_session, monkeypatch, role):
    order = _stored_order(requester_id="requester-1")
    order.courier_id = "courier-1"
    order.status = OrderStatus.AWAITING_APPROVAL
    deliver = AsyncMock(return_value=order)
    monkeypatch.setattr(order_routes.order_service, "deliver_order", deliver)

    response = client.post(
        "/orders/order-1/deliver",
        headers={"X-User-Id": "courier-1", "X-User-Role": role},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "AWAITING_APPROVAL"
    deliver.assert_awaited_once_with(fake_session, "order-1", "courier-1")


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({}, 422),
        ({"X-User-Id": "courier-1"}, 422),
        ({"X-User-Role": "client"}, 422),
        ({"X-User-Id": "courier-1", "X-User-Role": "courier"}, 403),
    ],
)
def test_deliver_requires_identity_and_supported_role(
    client, monkeypatch, headers, expected_status
):
    deliver = AsyncMock()
    monkeypatch.setattr(order_routes.order_service, "deliver_order", deliver)

    response = client.post("/orders/order-1/deliver", headers=headers)

    assert response.status_code == expected_status
    deliver.assert_not_awaited()


def test_deliver_maps_database_failure(client, monkeypatch):
    monkeypatch.setattr(
        order_routes.order_service,
        "deliver_order",
        AsyncMock(side_effect=OrderDeliveryError("order-1")),
    )

    response = client.post(
        "/orders/order-1/deliver",
        headers={"X-User-Id": "courier-1", "X-User-Role": "admin"},
    )

    assert response.status_code == 500
    assert response.json()["code"] == "order_delivery_failed"


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, 422),
        ({"X-User-Id": "courier-1"}, 422),
        ({"X-User-Role": "client"}, 422),
        ({"X-User-Id": "", "X-User-Role": "client"}, 422),
        ({"X-User-Id": "courier-1", "X-User-Role": "admin"}, 403),
        ({"X-User-Id": "courier-1", "X-User-Role": "courier"}, 403),
    ],
)
def test_accept_requires_trusted_client_headers(client, monkeypatch, headers, expected):
    accept = AsyncMock()
    monkeypatch.setattr(order_routes.order_service, "accept_order", accept)
    response = client.post("/orders/order-1/accept", headers=headers)
    assert response.status_code == expected
    accept.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (OrderNotFoundError("order-1"), 404, "order_not_found"),
        (OrderStateConflictError("order-1", "Pending update"), 409, "invalid_order_state"),
        (OrderAcceptanceError("order-1"), 500, "order_acceptance_failed"),
    ],
)
def test_accept_maps_domain_errors(client, monkeypatch, error, expected_status, expected_code):
    monkeypatch.setattr(order_routes.order_service, "accept_order", AsyncMock(side_effect=error))
    response = client.post(
        "/orders/order-1/accept",
        headers={"X-User-Id": "courier-1", "X-User-Role": "client"},
    )
    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code


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


def test_list_assigned_orders_uses_courier_identity(
    client: TestClient,
    fake_session: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = _stored_order(requester_id="requester-1")
    order.courier_id = "courier-1"
    order.status = OrderStatus.ACCEPTED
    listing = AsyncMock(return_value=[order])
    monkeypatch.setattr(order_routes.order_service, "list_assigned_orders", listing)

    response = client.get(
        "/orders/assigned",
        headers={"X-User-Id": "courier-1", "X-User-Role": "client"},
    )

    assert response.status_code == 200
    assert [item["order_id"] for item in response.json()] == ["order-1"]
    listing.assert_awaited_once_with(fake_session, "courier-1")


def test_list_assigned_orders_returns_empty_array_when_none_match(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        order_routes.order_service,
        "list_assigned_orders",
        AsyncMock(return_value=[]),
    )

    response = client.get(
        "/orders/assigned",
        headers={"X-User-Id": "courier-1", "X-User-Role": "client"},
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({"X-User-Id": "courier-1"}, 422),
        ({"X-User-Role": "client"}, 422),
        ({"X-User-Id": "courier-1", "X-User-Role": "admin"}, 403),
    ],
)
def test_list_assigned_orders_requires_client_identity(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    expected_status: int,
) -> None:
    listing = AsyncMock()
    monkeypatch.setattr(order_routes.order_service, "list_assigned_orders", listing)

    response = client.get("/orders/assigned", headers=headers)

    assert response.status_code == expected_status
    listing.assert_not_awaited()


@pytest.mark.parametrize(
    ("path", "service_method", "role"),
    [
        ("/orders/requested/ongoing", "list_requested_ongoing_orders", None),
        ("/orders/requested/completed", "list_requested_completed_orders", None),
        ("/orders/assigned/completed", "list_assigned_completed_orders", "client"),
    ],
)
def test_participant_lists_use_gateway_identity_and_return_summaries(
    client: TestClient,
    fake_session: object,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    service_method: str,
    role: str | None,
) -> None:
    order = _stored_order(requester_id="requester-1")
    order.courier_id = "courier-1"
    order.status = OrderStatus.COMPLETED
    listing = AsyncMock(return_value=[order])
    monkeypatch.setattr(order_routes.order_service, service_method, listing)
    headers = {"X-User-Id": "user-1"}
    if role:
        headers["X-User-Role"] = role

    response = client.get(
        path,
        headers=headers,
        params={"requester_id": "other-user", "courier_id": "other-user"},
    )

    assert response.status_code == 200
    assert [item["order_id"] for item in response.json()] == ["order-1"]
    listing.assert_awaited_once_with(fake_session, "user-1")


@pytest.mark.parametrize(
    ("path", "service_method"),
    [
        ("/orders/requested/ongoing", "list_requested_ongoing_orders"),
        ("/orders/requested/completed", "list_requested_completed_orders"),
        ("/orders/assigned/completed", "list_assigned_completed_orders"),
    ],
)
def test_participant_lists_require_user_id_and_return_empty_list(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    service_method: str,
) -> None:
    listing = AsyncMock(return_value=[])
    monkeypatch.setattr(order_routes.order_service, service_method, listing)
    headers = {"X-User-Role": "client"}

    assert client.get(path, headers=headers).status_code == 422
    listing.assert_not_awaited()

    response = client.get(path, headers={**headers, "X-User-Id": "user-1"})
    assert response.status_code == 200
    assert response.json() == []


def test_completed_assigned_list_requires_client_role(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = AsyncMock()
    monkeypatch.setattr(order_routes.order_service, "list_assigned_completed_orders", listing)

    response = client.get(
        "/orders/assigned/completed",
        headers={"X-User-Id": "courier-1", "X-User-Role": "admin"},
    )

    assert response.status_code == 403
    listing.assert_not_awaited()


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


def test_delete_order_returns_accepted_task(
    client: TestClient,
    fake_session: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_delete_order(session, order_id, requester_id):
        assert session is fake_session
        assert order_id == "order-1"
        assert requester_id == "user-1"
        return SimpleNamespace(task_id="task-1", order_id=order_id, status="pending")

    monkeypatch.setattr(
        order_routes.order_service,
        "delete_order_for_requester",
        fake_delete_order,
    )

    response = client.delete(
        "/orders/order-1",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "task_id": "task-1",
        "order_id": "order-1",
        "status": "pending",
        "failure_reason": None,
    }


def test_cancel_order_returns_accepted_task(
    client: TestClient,
    fake_session: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = SimpleNamespace(task_id="task-1", order_id="order-1", status="pending")
    cancel = AsyncMock(return_value=task)
    monkeypatch.setattr(order_routes.order_service, "cancel_order_for_requester", cancel)

    response = client.post(
        "/orders/order-1/cancel",
        headers={"X-User-Id": "user-1"},
        json={"reason": "Requester changed their mind"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "task_id": "task-1",
        "order_id": "order-1",
        "status": "pending",
        "failure_reason": None,
    }
    cancel.assert_awaited_once_with(
        fake_session,
        "order-1",
        "user-1",
        "Requester changed their mind",
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"reason": ""},
        {"reason": "cancel", "unexpected": True},
    ],
)
def test_cancel_order_validates_reason(client: TestClient, payload: dict[str, Any]) -> None:
    response = client.post(
        "/orders/order-1/cancel",
        headers={"X-User-Id": "user-1"},
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_get_deletion_reports_completion_to_owner(
    client: TestClient, fake_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get_deletion(session, task_id, requester_id):
        assert session is fake_session
        assert (task_id, requester_id) == ("task-1", "user-1")
        return SimpleNamespace(task_id=task_id, order_id="order-1", status="completed")

    monkeypatch.setattr(order_routes.order_service, "get_deletion_for_requester", fake_get_deletion)
    response = client.get("/orders/deletions/task-1", headers={"X-User-Id": "user-1"})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_patch_returns_pending_task_and_can_be_polled(client, fake_session, monkeypatch):
    task = SimpleNamespace(
        task_id="task-1",
        order_id="order-1",
        status="pending",
        last_error=None,
    )

    async def fake_update_order(*, order_id, updated_order, requester_id, session):
        assert (order_id, requester_id) == ("order-1", "user-1")
        assert updated_order.reward == 5
        assert session is fake_session
        return task

    async def fake_get_update(session, task_id, requester_id):
        assert (session, task_id, requester_id) == (fake_session, "task-1", "user-1")
        return task

    monkeypatch.setattr(order_routes.order_service, "update_order", fake_update_order)
    monkeypatch.setattr(order_routes.order_service, "get_update_for_requester", fake_get_update)

    response = client.patch("/orders/order-1", headers={"X-User-Id": "user-1"}, json=_payload())
    assert response.status_code == 202
    assert response.json()["task_id"] == "task-1"
    assert response.json()["status"] == "pending"

    poll = client.get("/orders/updates/task-1", headers={"X-User-Id": "user-1"})
    assert poll.status_code == 200
    assert poll.json()["status"] == "pending"


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

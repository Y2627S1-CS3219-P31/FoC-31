# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import orders as order_routes
from app.db import get_session
from app.main import app
from app.models.orders import Order


@pytest.fixture
def fake_session() -> object:
    return object()


@pytest.fixture
def client(fake_session: object) -> TestClient:
    async def override_get_session():
        yield fake_session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def order_payload() -> dict[str, Any]:
    return {
        "name": "Collect lunch",
        "details": "One vegetarian rice bowl",
        "reward": 5,
        "deadline": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        "supplier_id": "sup_001",
        "pickup_location": "The Deck",
        "delivery_location": "COM3",
    }


def stored_order(*, requester_id: str = "user-1", status: str = "OPEN") -> Order:
    payload = order_payload()
    return Order(
        id=1,
        **payload,
        requester_id=requester_id,
        courier_id=None,
        status=status,
    )


def test_create_order_uses_collection_url_and_authenticated_requester(
    client: TestClient,
    fake_session: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_create(session, order, requester_id):
        captured.update(session=session, order=order, requester_id=requester_id)
        return stored_order(requester_id=requester_id)

    monkeypatch.setattr(order_routes.order_service, "create_order", fake_create)

    response = client.post(
        "/orders",
        headers={"X-User-Id": "user-1"},
        json=order_payload(),
    )

    assert response.status_code == 201
    assert response.json()["requester_id"] == "user-1"
    assert response.json()["status"] == "OPEN"
    assert captured["session"] is fake_session
    assert captured["requester_id"] == "user-1"
    assert captured["order"].name == "Collect lunch"
    assert client.post("/orders/order", headers={"X-User-Id": "user-1"}).status_code == 405


def test_create_order_rejects_past_deadline(client: TestClient) -> None:
    payload = order_payload()
    payload["deadline"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()

    response = client.post(
        "/orders",
        headers={"X-User-Id": "user-1"},
        json=payload,
    )

    assert response.status_code == 422

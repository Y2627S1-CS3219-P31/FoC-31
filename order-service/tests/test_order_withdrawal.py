# AI-INFLUENCED: Verify withdrawal idempotency and pickup state conflicts.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.orders import OrderResponse
from app.services import event_worker, orders
from app.services.errors import OrderNotFoundError, OrderStateConflictError
from app.services.lifecycle import OrderStatus
from foc_shared.events import OrderEvent, OrderEventType


class _Session:
    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


def _order() -> SimpleNamespace:
    return SimpleNamespace(
        order_id="order-1",
        name="Lunch",
        details="Bring lunch",
        reward=5,
        deadline=datetime.now(UTC) + timedelta(hours=1),
        supplier_id="supplier-1",
        requester_id="requester-1",
        courier_id="courier-1",
        reservation_id="reservation-1",
        pickup_location="Library",
        delivery_location="Dorm",
        status=OrderStatus.ACCEPTED,
        created_at=datetime.now(UTC),
    )


def _mocks(monkeypatch: pytest.MonkeyPatch, order: SimpleNamespace) -> dict[str, AsyncMock]:
    mocks = {
        "lock_key": AsyncMock(),
        "get_request": AsyncMock(return_value=None),
        "get_order": AsyncMock(return_value=order),
        "pending_action": AsyncMock(return_value=None),
        "save_request": AsyncMock(),
        "outbox": AsyncMock(),
    }

    async def unassign(_session, current):
        current.status = OrderStatus.OPEN
        current.courier_id = None

    async def set_status(_session, current, status):
        current.status = status

    monkeypatch.setattr(orders.request_repository, "lock_request_id", mocks["lock_key"])
    monkeypatch.setattr(orders.request_repository, "get_request", mocks["get_request"])
    monkeypatch.setattr(orders.request_repository, "save_request", mocks["save_request"])
    monkeypatch.setattr(orders.order_repository, "get_order_for_update", mocks["get_order"])
    monkeypatch.setattr(orders.order_repository, "unassign_courier", unassign)
    monkeypatch.setattr(orders.order_repository, "set_status", set_status)
    monkeypatch.setattr(orders.release_tasks, "get_for_order", mocks["pending_action"])
    monkeypatch.setattr(orders.event_outbox_repository, "create_event", mocks["outbox"])
    return mocks


async def test_withdrawal_saves_result_and_order_fact(monkeypatch):
    order = _order()
    mocks = _mocks(monkeypatch, order)

    result = await orders.withdraw_order(_Session(), "order-1", "courier-1", "key-1")

    assert result.status == OrderStatus.OPEN
    assert result.courier_id is None
    assert order.reservation_id == "reservation-1"
    mocks["get_order"].assert_awaited_once()
    mocks["save_request"].assert_awaited_once()
    assert mocks["save_request"].await_args.kwargs["response"]["status"] == "OPEN"
    event = mocks["outbox"].await_args.args[1]
    assert isinstance(event, OrderEvent)
    assert event.event_type == OrderEventType.COURIER_WITHDRAWN
    assert event.courier_id == "courier-1"
    assert event_worker._parse_event(event.model_dump(mode="json")) == event


async def test_duplicate_key_replays_original_result_without_touching_order(monkeypatch):
    order = _order()
    mocks = _mocks(monkeypatch, order)
    saved = OrderResponse.model_validate(order).model_copy(
        update={"status": OrderStatus.OPEN, "courier_id": None}
    )
    mocks["get_request"].return_value = SimpleNamespace(
        action="withdraw",
        order_id="order-1",
        actor_id="courier-1",
        response=saved.model_dump(mode="json"),
    )

    result = await orders.withdraw_order(_Session(), "order-1", "courier-1", "key-1")

    assert result == saved
    mocks["get_order"].assert_not_awaited()
    mocks["save_request"].assert_not_awaited()
    mocks["outbox"].assert_not_awaited()


async def test_reused_key_for_other_request_is_rejected(monkeypatch):
    mocks = _mocks(monkeypatch, _order())
    mocks["get_request"].return_value = SimpleNamespace(
        action="withdraw", order_id="other-order", actor_id="courier-1", response={}
    )

    with pytest.raises(OrderStateConflictError, match="Idempotency key"):
        await orders.withdraw_order(_Session(), "order-1", "courier-1", "key-1")

    mocks["get_order"].assert_not_awaited()
    mocks["outbox"].assert_not_awaited()


async def test_pickup_and_withdrawal_require_opposite_locked_states(monkeypatch):
    order = _order()
    mocks = _mocks(monkeypatch, order)

    await orders.pickup_order(_Session(), "order-1", "courier-1")
    with pytest.raises(OrderStateConflictError, match="accepted order"):
        await orders.withdraw_order(_Session(), "order-1", "courier-1", "key-1")

    assert order.status == OrderStatus.PICKED_UP
    assert mocks["get_order"].await_count == 2
    assert mocks["outbox"].await_count == 1
    assert mocks["outbox"].await_args.args[1].event_type == OrderEventType.ORDER_PICKED_UP
    mocks["save_request"].assert_not_awaited()


@pytest.mark.parametrize("status", [OrderStatus.CANCELLED, OrderStatus.PICKED_UP])
async def test_pickup_rejects_orders_no_longer_accepted(monkeypatch, status):
    order = _order()
    order.status = status
    mocks = _mocks(monkeypatch, order)

    with pytest.raises(OrderStateConflictError, match="Only an accepted order"):
        await orders.pickup_order(_Session(), "order-1", "courier-1")

    assert order.status == status
    mocks["outbox"].assert_not_awaited()


async def test_pickup_rejects_pending_cancellation_without_an_event(monkeypatch):
    order = _order()
    mocks = _mocks(monkeypatch, order)
    mocks["pending_action"].return_value = SimpleNamespace(action="cancel")

    with pytest.raises(OrderStateConflictError, match="terminal action is pending"):
        await orders.pickup_order(_Session(), "order-1", "courier-1")

    assert order.status == OrderStatus.ACCEPTED
    mocks["outbox"].assert_not_awaited()


async def test_pickup_rejects_missing_order_without_an_event(monkeypatch):
    mocks = _mocks(monkeypatch, _order())
    mocks["get_order"].return_value = None

    with pytest.raises(OrderNotFoundError):
        await orders.pickup_order(_Session(), "missing", "courier-1")

    mocks["outbox"].assert_not_awaited()

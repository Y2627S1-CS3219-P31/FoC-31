# AI-influenced: Order delivery workflow tests added with Codex.
from __future__ import annotations

from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services import orders
from app.services.errors import (
    OrderAccessDeniedError,
    OrderDeliveryError,
    OrderNotFoundError,
    OrderStateConflictError,
)
from app.services.lifecycle import OrderStatus


@pytest.fixture
def delivery(monkeypatch):
    order = SimpleNamespace(
        order_id="order-1",
        requester_id="requester-1",
        courier_id="courier-1",
        status=OrderStatus.PICKED_UP,
    )
    session = MagicMock()
    session.begin.return_value = AsyncMock()
    get_order = AsyncMock(return_value=order)
    set_status = AsyncMock()
    create_event = AsyncMock()
    monkeypatch.setattr(orders.order_repository, "get_order_for_update", get_order)
    monkeypatch.setattr(orders.order_repository, "set_status", set_status)
    monkeypatch.setattr(orders.event_outbox_repository, "create_event", create_event)
    return SimpleNamespace(
        order=order,
        session=session,
        get_order=get_order,
        set_status=set_status,
        create_event=create_event,
    )


async def test_delivery_transitions_order_and_records_event(delivery):
    result = await orders.deliver_order(delivery.session, "order-1", "courier-1")

    assert result is delivery.order
    delivery.get_order.assert_awaited_once_with(delivery.session, "order-1")
    delivery.set_status.assert_awaited_once_with(
        delivery.session, delivery.order, OrderStatus.AWAITING_APPROVAL
    )
    event = delivery.create_event.await_args.args[1]
    assert event.event_type == "OrderDelivered"
    assert (event.order_id, event.requester_id, event.courier_id) == (
        "order-1",
        "requester-1",
        "courier-1",
    )
    assert event.timestamp.tzinfo == UTC


async def test_delivery_requires_existing_order(delivery):
    delivery.get_order.return_value = None

    with pytest.raises(OrderNotFoundError):
        await orders.deliver_order(delivery.session, "missing", "courier-1")

    delivery.set_status.assert_not_awaited()
    delivery.create_event.assert_not_awaited()


async def test_delivery_requires_assigned_courier(delivery):
    with pytest.raises(OrderAccessDeniedError):
        await orders.deliver_order(delivery.session, "order-1", "another-courier")

    delivery.set_status.assert_not_awaited()
    delivery.create_event.assert_not_awaited()


@pytest.mark.parametrize(
    "status",
    [
        OrderStatus.OPEN,
        OrderStatus.ACCEPTED,
        OrderStatus.AWAITING_APPROVAL,
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    ],
)
async def test_delivery_requires_picked_up_status(delivery, status):
    delivery.order.status = status

    with pytest.raises(OrderStateConflictError, match="Only a picked-up order"):
        await orders.deliver_order(delivery.session, "order-1", "courier-1")

    delivery.set_status.assert_not_awaited()
    delivery.create_event.assert_not_awaited()


@pytest.mark.parametrize("failure_point", ["outbox", "commit"])
async def test_delivery_database_failures_are_translated(delivery, failure_point):
    failure = SQLAlchemyError("database failed")
    if failure_point == "outbox":
        delivery.create_event.side_effect = failure
    else:
        delivery.session.begin.return_value.__aexit__.side_effect = failure

    with pytest.raises(OrderDeliveryError):
        await orders.deliver_order(delivery.session, "order-1", "courier-1")

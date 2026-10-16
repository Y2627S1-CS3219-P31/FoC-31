# AI-INFLUENCED: Order acceptance validation tests implemented with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services import orders
from app.services.errors import OrderAcceptanceError, OrderNotFoundError, OrderStateConflictError
from app.services.lifecycle import OrderStatus


@pytest.fixture
def acceptance(monkeypatch):
    order = SimpleNamespace(
        order_id="order-1",
        requester_id="requester-1",
        courier_id=None,
        status=OrderStatus.OPEN,
        deadline=datetime.now(UTC) + timedelta(hours=1),
    )
    session = MagicMock()
    session.begin.return_value = AsyncMock()
    mocks = SimpleNamespace(order=order, session=session)
    for repository, name, result in (
        (orders.order_repository, "lock_courier_acceptance", None),
        (orders.order_repository, "get_order_for_update", order),
        (orders.order_repository, "count_ongoing_for_courier", 0),
        (orders.order_repository, "assign_courier", None),
        (orders.update_outbox_repository, "get_pending_for_order", None),
        (orders.deletion_outbox_repository, "get_for_order", None),
        (orders.event_outbox_repository, "create_event", None),
    ):
        mock = AsyncMock(return_value=result)
        monkeypatch.setattr(repository, name, mock)
        setattr(mocks, name, mock)
    return mocks


async def test_acceptance_records_shared_event(acceptance):
    result = await orders.accept_order(acceptance.session, "order-1", "courier-1")
    assert result is acceptance.order
    acceptance.assign_courier.assert_awaited_once_with(
        acceptance.session, acceptance.order, "courier-1"
    )
    event = acceptance.create_event.await_args.args[1]
    assert event.event_type == "OrderAccepted"
    assert (event.order_id, event.requester_id, event.courier_id) == (
        "order-1",
        "requester-1",
        "courier-1",
    )
    assert event.timestamp.tzinfo == UTC


async def test_missing_order_is_not_found(acceptance):
    acceptance.get_order_for_update.return_value = None
    with pytest.raises(OrderNotFoundError):
        await orders.accept_order(acceptance.session, "missing", "courier-1")
    acceptance.create_event.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("requester_id", "courier-1", "own order"),
        ("courier_id", "courier-2", "assigned courier"),
        ("status", OrderStatus.CANCELLED, "not available"),
        ("deadline", datetime(2020, 1, 1, tzinfo=UTC), "expired"),
    ],
)
async def test_invalid_order_cannot_be_accepted(acceptance, field, value, message):
    setattr(acceptance.order, field, value)
    with pytest.raises(OrderStateConflictError, match=message):
        await orders.accept_order(acceptance.session, "order-1", "courier-1")
    acceptance.assign_courier.assert_not_awaited()
    acceptance.create_event.assert_not_awaited()


async def test_deadline_equal_to_now_is_expired(acceptance, monkeypatch):
    now = datetime(2026, 10, 16, tzinfo=UTC)
    monkeypatch.setattr(orders, "datetime", SimpleNamespace(now=lambda _tz: now))
    acceptance.order.deadline = now
    with pytest.raises(OrderStateConflictError, match="expired"):
        await orders.accept_order(acceptance.session, "order-1", "courier-1")


@pytest.mark.parametrize("published_at", [None, datetime(2026, 10, 16, tzinfo=UTC)])
async def test_pending_update_blocks_acceptance_even_after_publication(acceptance, published_at):
    acceptance.get_pending_for_order.return_value = SimpleNamespace(
        status="pending", published_at=published_at
    )
    with pytest.raises(OrderStateConflictError, match="update is still pending"):
        await orders.accept_order(acceptance.session, "order-1", "courier-1")
    acceptance.assign_courier.assert_not_awaited()
    acceptance.create_event.assert_not_awaited()


@pytest.mark.parametrize("status", ["pending", "processing", "failed", "completed"])
async def test_any_deletion_task_blocks_acceptance(acceptance, status):
    acceptance.get_for_order.return_value = SimpleNamespace(status=status)
    with pytest.raises(OrderStateConflictError, match="deletion"):
        await orders.accept_order(acceptance.session, "order-1", "courier-1")
    acceptance.create_event.assert_not_awaited()


@pytest.mark.parametrize("count", [3, 4])
async def test_courier_limit_blocks_acceptance(acceptance, count):
    acceptance.count_ongoing_for_courier.return_value = count
    with pytest.raises(OrderStateConflictError, match="3 ongoing orders"):
        await orders.accept_order(acceptance.session, "order-1", "courier-1")
    acceptance.create_event.assert_not_awaited()


@pytest.mark.parametrize("failing_call", ["create_event", "commit"])
async def test_database_failure_is_translated(acceptance, failing_call):
    failure = SQLAlchemyError("database failed")
    if failing_call == "commit":
        acceptance.session.begin.return_value.__aexit__.side_effect = failure
    else:
        acceptance.create_event.side_effect = failure
    with pytest.raises(OrderAcceptanceError):
        await orders.accept_order(acceptance.session, "order-1", "courier-1")

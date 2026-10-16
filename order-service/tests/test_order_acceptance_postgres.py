# AI-INFLUENCED: PostgreSQL acceptance atomicity and concurrency tests added with Codex.
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models.order_event_outbox import OrderEventOutbox
from app.models.order_release_tasks import OrderReleaseTask, ReleaseAction
from app.models.order_update_tasks import OrderUpdateTask
from app.models.orders import OrderTable
from app.repositories import orders as order_repository
from app.services import event_worker, orders
from app.services.errors import OrderAcceptanceError, OrderStateConflictError
from app.services.lifecycle import OrderStatus


def _order(order_id, *, status=OrderStatus.OPEN, courier_id=None):
    return OrderTable(
        order_id=order_id,
        name="Lunch",
        details="Bring lunch",
        reward=5,
        deadline=datetime.now(UTC) + timedelta(hours=1),
        supplier_id="supplier-1",
        requester_id="requester-1",
        reservation_id=f"reservation-{order_id}",
        pickup_location="Library",
        delivery_location="Dorm",
        status=status,
        courier_id=courier_id,
    )


async def _seed(sessions, *rows):
    async with sessions() as session, session.begin():
        session.add_all(rows)


async def _accept(sessions, order_id="order-1", courier_id="courier-1"):
    async with sessions() as session:
        return await orders.accept_order(session, order_id, courier_id)


async def test_assignment_and_event_commit_together(postgres_sessions):
    await _seed(postgres_sessions, _order("order-1"))
    before = datetime.now(UTC)
    await _accept(postgres_sessions)
    async with postgres_sessions() as session:
        order = await session.get(OrderTable, "order-1")
        assert (order.status, order.courier_id) == (OrderStatus.ACCEPTED, "courier-1")
        task = (await session.scalars(select(OrderEventOutbox))).one()
        assert task.payload["event_type"] == "OrderAccepted"
        assert task.payload["order_id"] == "order-1"
        assert task.payload["requester_id"] == "requester-1"
        assert task.payload["courier_id"] == "courier-1"
        assert datetime.fromisoformat(task.payload["timestamp"]) >= before
        assert task.published_at is None
    with pytest.raises(OrderStateConflictError, match="assigned courier"):
        await _accept(postgres_sessions)


@pytest.mark.parametrize("failure_stage", ["event", "commit"])
async def test_failure_rolls_back_assignment_and_event(
    postgres_sessions, monkeypatch, failure_stage
):
    await _seed(postgres_sessions, _order("order-1"))
    async with postgres_sessions() as session:
        if failure_stage == "event":
            monkeypatch.setattr(
                orders.event_outbox_repository,
                "create_event",
                AsyncMock(side_effect=SQLAlchemyError("insert failed")),
            )
        else:

            def fail_commit(_session):
                raise SQLAlchemyError("commit failed")

            event.listen(session.sync_session, "before_commit", fail_commit)
        with pytest.raises(OrderAcceptanceError):
            await orders.accept_order(session, "order-1", "courier-1")
    async with postgres_sessions() as session:
        order = await session.get(OrderTable, "order-1")
        assert (order.status, order.courier_id) == (OrderStatus.OPEN, None)
        assert await session.scalar(select(func.count()).select_from(OrderEventOutbox)) == 0


@pytest.mark.parametrize("status", ["pending", "completed", "rejected"])
async def test_outbox_status_controls_acceptance(postgres_sessions, status):
    await _seed(
        postgres_sessions,
        _order("order-1"),
        OrderUpdateTask(
            order_id="order-1",
            requester_id="requester-1",
            reservation_id="reservation-order-1",
            proposed_order={"reward": 10},
            status=status,
        ),
    )
    if status == "pending":
        with pytest.raises(OrderStateConflictError, match="pending"):
            await _accept(postgres_sessions)
    else:
        await _accept(postgres_sessions)


@pytest.mark.parametrize(("status", "blocks_acceptance"), [("pending", True), ("failed", False)])
async def test_only_pending_deletion_blocks_acceptance(
    postgres_sessions, status, blocks_acceptance
):
    await _seed(
        postgres_sessions,
        _order("order-1"),
        OrderReleaseTask(
            order_id="order-1",
            requester_id="requester-1",
            reservation_id="reservation-order-1",
            action=ReleaseAction.DELETE.value,
            status=status,
        ),
    )
    if blocks_acceptance:
        with pytest.raises(OrderStateConflictError, match="deletion"):
            await _accept(postgres_sessions)
    else:
        await _accept(postgres_sessions)


async def test_only_ongoing_orders_count_toward_limit(postgres_sessions):
    await _seed(
        postgres_sessions,
        *[_order(status.value, status=status, courier_id="courier-1") for status in OrderStatus],
        _order("order-1"),
    )
    async with postgres_sessions() as session:
        assert await order_repository.count_ongoing_for_courier(session, "courier-1") == 3
    with pytest.raises(OrderStateConflictError, match="3 ongoing"):
        await _accept(postgres_sessions)


@pytest.mark.parametrize("same_order", [True, False])
async def test_concurrent_acceptance_is_serialized(postgres_sessions, monkeypatch, same_order):
    rows = [_order("order-1"), _order("order-2")]
    if not same_order:
        rows += [
            _order("active-1", status=OrderStatus.PICKED_UP, courier_id="courier-1"),
            _order("active-2", status=OrderStatus.AWAITING_APPROVAL, courier_id="courier-1"),
        ]
    await _seed(postgres_sessions, *rows)
    first_validated = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()
    assign = order_repository.assign_courier

    async def hold_first_assignment(session, order, courier_id):
        if order.order_id == "order-1" and courier_id == "courier-1":
            first_validated.set()
            await release_first.wait()
        await assign(session, order, courier_id)

    monkeypatch.setattr(order_repository, "assign_courier", hold_first_assignment)
    first = asyncio.create_task(_accept(postgres_sessions))
    second = None
    try:
        await asyncio.wait_for(first_validated.wait(), timeout=5)

        async def competing_acceptance():
            second_started.set()
            return await _accept(
                postgres_sessions,
                "order-1" if same_order else "order-2",
                "courier-2" if same_order else "courier-1",
            )

        second = asyncio.create_task(competing_acceptance())
        await second_started.wait()
        done, _ = await asyncio.wait({second}, timeout=0.2)
        assert not done, "Competing acceptance bypassed the transaction lock"
    finally:
        release_first.set()
        results = await asyncio.wait_for(
            asyncio.gather(*[task for task in (first, second) if task], return_exceptions=True),
            timeout=5,
        )
    assert isinstance(results[0], OrderTable)
    assert isinstance(results[1], OrderStateConflictError)
    async with postgres_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OrderEventOutbox)) == 1
        assert await order_repository.count_ongoing_for_courier(session, "courier-1") == (
            1 if same_order else 3
        )


async def test_parallel_publishers_only_publish_locked_event_once(postgres_sessions, monkeypatch):
    await _seed(postgres_sessions, _order("order-1"))
    await _accept(postgres_sessions)
    monkeypatch.setattr(event_worker, "SessionLocal", postgres_sessions)
    publishing = asyncio.Event()
    release = asyncio.Event()

    async def hold_publication(*args, **kwargs):
        publishing.set()
        await release.wait()

    publish = AsyncMock(side_effect=hold_publication)
    monkeypatch.setattr(event_worker, "publish_order_event", publish)
    first = asyncio.create_task(event_worker.publish_pending_events())
    try:
        await asyncio.wait_for(publishing.wait(), timeout=5)
        await asyncio.wait_for(event_worker.publish_pending_events(), timeout=5)
        assert publish.await_count == 1
    finally:
        release.set()
        await asyncio.wait_for(first, timeout=5)

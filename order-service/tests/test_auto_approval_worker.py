# AI-INFLUENCED: Verify due-time approval and independent requester workflow.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.order_approval_tasks import FAILED, PENDING, OrderApprovalTask
from app.models.order_event_outbox import OrderEventOutbox
from app.models.orders import OrderTable
from app.services import auto_approval_worker, orders
from app.services.errors import OrderStateConflictError
from app.services.lifecycle import OrderStatus


@pytest.fixture
async def approval_store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def add_postgres_string_functions(connection, _record):
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.create_function("char_length", 1, len)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(auto_approval_worker, "SessionLocal", sessions)
    yield sessions
    await engine.dispose()


def _order(order_id: str, *, status: OrderStatus, waiting_since: datetime) -> OrderTable:
    return OrderTable(
        order_id=order_id,
        name="Lunch",
        details="Bring lunch",
        reward=5,
        deadline=datetime.now(UTC) + timedelta(hours=1),
        supplier_id="supplier-1",
        requester_id="requester-1",
        courier_id="courier-1",
        reservation_id=f"reservation-{order_id}",
        pickup_location="Library",
        delivery_location="Dorm",
        status=status,
        awaiting_approval_at=waiting_since,
    )


async def test_sweeper_completes_only_due_orders_once(approval_store):
    now = datetime.now(UTC)
    async with approval_store() as session, session.begin():
        session.add_all(
            [
                _order(
                    "due",
                    status=OrderStatus.AWAITING_APPROVAL,
                    waiting_since=now - timedelta(hours=25),
                ),
                _order(
                    "early",
                    status=OrderStatus.AWAITING_APPROVAL,
                    waiting_since=now - timedelta(hours=23),
                ),
                _order(
                    "picked-up",
                    status=OrderStatus.PICKED_UP,
                    waiting_since=now - timedelta(hours=25),
                ),
            ]
        )

    assert await auto_approval_worker.auto_approve_due_orders() == 1
    assert await auto_approval_worker.auto_approve_due_orders() == 0

    async with approval_store() as session:
        tasks = list((await session.scalars(select(OrderApprovalTask))).all())
        events = list((await session.scalars(select(OrderEventOutbox))).all())
        due_order = await session.get(OrderTable, "due")
    assert len(tasks) == 1
    assert len(events) == 2
    assert tasks[0].status == PENDING
    assert {event.payload["event_type"] for event in events} == {
        "OrderApprovalRequested",
        "OrderApproved",
    }
    assert {event.payload["task_id"] for event in events} == {tasks[0].task_id}
    assert due_order.status == OrderStatus.COMPLETED

    async with approval_store() as session:
        with pytest.raises(OrderStateConflictError):
            await orders.approve_order_for_requester(session, "due", "requester-1")


async def test_sweeper_completes_orders_with_failed_prior_approval(approval_store):
    now = datetime.now(UTC)
    async with approval_store() as session, session.begin():
        session.add(
            _order(
                "failed",
                status=OrderStatus.AWAITING_APPROVAL,
                waiting_since=now - timedelta(hours=25),
            )
        )
        session.add(
            OrderApprovalTask(
                order_id="failed",
                reservation_id="reservation-failed",
                requester_id="requester-1",
                courier_id="courier-1",
                status=FAILED,
            )
        )

    assert await auto_approval_worker.auto_approve_due_orders() == 1
    async with approval_store() as session:
        tasks = list((await session.scalars(select(OrderApprovalTask))).all())
        events = list((await session.scalars(select(OrderEventOutbox))).all())
        order = await session.get(OrderTable, "failed")
    assert len(tasks) == 2
    assert len(events) == 2
    assert order.status == OrderStatus.COMPLETED


async def test_outbox_failure_rolls_back_auto_approval_task(approval_store, monkeypatch):
    async with approval_store() as session, session.begin():
        session.add(
            _order(
                "due",
                status=OrderStatus.AWAITING_APPROVAL,
                waiting_since=datetime.now(UTC) - timedelta(hours=25),
            )
        )
    monkeypatch.setattr(
        auto_approval_worker.event_outbox_repository,
        "create_event",
        AsyncMock(side_effect=SQLAlchemyError("outbox failed")),
    )

    with pytest.raises(SQLAlchemyError):
        await auto_approval_worker.auto_approve_due_orders()

    async with approval_store() as session:
        assert (await session.scalars(select(OrderApprovalTask))).all() == []
        assert (await session.scalars(select(OrderEventOutbox))).all() == []
        assert (await session.get(OrderTable, "due")).status == OrderStatus.AWAITING_APPROVAL

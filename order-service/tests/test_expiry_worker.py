# AI-INFLUENCED: Direct batched order expiry workflow tests added with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.order_event_outbox import OrderEventOutbox
from app.models.order_release_tasks import OrderReleaseTask
from app.models.orders import OrderTable
from app.services import expiry_worker
from app.services.lifecycle import OrderStatus


@pytest.fixture
async def expiry_store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def add_postgres_string_functions(connection, _record):
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.create_function("char_length", 1, len)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(expiry_worker, "SessionLocal", sessions)
    yield sessions
    await engine.dispose()


def _order(order_id: str, *, deadline: datetime, status: OrderStatus) -> OrderTable:
    return OrderTable(
        order_id=order_id,
        name="Lunch",
        details="Bring lunch",
        reward=5,
        deadline=deadline,
        supplier_id="supplier-1",
        requester_id="requester-1",
        courier_id="courier-1" if status == OrderStatus.ACCEPTED else None,
        reservation_id=f"reservation-{order_id}",
        pickup_location="Library",
        delivery_location="Dorm",
        status=status,
    )


async def test_expiry_marks_only_due_open_orders_and_writes_outbox_atomically(
    expiry_store,
) -> None:
    now = datetime.now(UTC)
    async with expiry_store() as session, session.begin():
        session.add_all(
            [
                _order("due-open", deadline=now - timedelta(minutes=1), status=OrderStatus.OPEN),
                _order("future-open", deadline=now + timedelta(minutes=1), status=OrderStatus.OPEN),
                _order(
                    "due-accepted",
                    deadline=now - timedelta(minutes=1),
                    status=OrderStatus.ACCEPTED,
                ),
            ]
        )

    assert await expiry_worker.expire_due_orders() == 1

    async with expiry_store() as session:
        orders = {
            order.order_id: order.status
            for order in (await session.scalars(select(OrderTable))).all()
        }
        events = (await session.scalars(select(OrderEventOutbox))).all()
        tasks = (await session.scalars(select(OrderReleaseTask))).all()

    assert orders == {
        "due-open": OrderStatus.EXPIRED,
        "future-open": OrderStatus.OPEN,
        "due-accepted": OrderStatus.ACCEPTED,
    }
    assert len(events) == 1
    assert events[0].payload["event_type"] == "OrderExpired"
    assert events[0].payload["order_id"] == "due-open"
    assert tasks == []


async def test_expiry_sweeper_drains_multiple_batches(expiry_store) -> None:
    now = datetime.now(UTC)
    async with expiry_store() as session, session.begin():
        session.add_all(
            [
                _order(
                    f"due-{index:03d}",
                    deadline=now - timedelta(minutes=1, seconds=index),
                    status=OrderStatus.OPEN,
                )
                for index in range(205)
            ]
        )

    assert await expiry_worker.expire_due_orders() == 205

    async with expiry_store() as session:
        expired_count = await session.scalar(
            select(func.count())
            .select_from(OrderTable)
            .where(OrderTable.status == OrderStatus.EXPIRED)
        )
        event_count = await session.scalar(select(func.count()).select_from(OrderEventOutbox))

    assert expired_count == 205
    assert event_count == 205

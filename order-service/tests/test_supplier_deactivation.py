# AI-INFLUENCED: Verify supplier-deactivation cancellations, retries, and atomic facts with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.order_event_outbox import OrderEventOutbox
from app.models.orders import OrderTable
from app.models.supplier_deactivation_inbox import SupplierDeactivationInbox
from app.schemas.supplier_events import SupplierDeactivatedEvent
from app.services import supplier_consumer, supplier_deactivation
from app.services.lifecycle import OrderStatus
from foc_shared.events import OrderEvent, OrderEventType


@pytest.fixture
async def order_store():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sqlalchemy_event.listens_for(engine.sync_engine, "connect")
    def add_postgres_string_functions(connection, _record):
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.create_function("char_length", 1, len)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield sessions
    await engine.dispose()


def _order(order_id: str, status: OrderStatus, supplier_id: str = "supplier-1") -> OrderTable:
    return OrderTable(
        order_id=order_id,
        name="Lunch",
        details="Bring lunch",
        reward=5,
        deadline=datetime.now(UTC) + timedelta(hours=1),
        supplier_id=supplier_id,
        requester_id="requester-1",
        courier_id="courier-1" if status != OrderStatus.OPEN else None,
        reservation_id=f"reservation-{order_id}",
        pickup_location="Library",
        delivery_location="Dorm",
        status=status,
    )


def _event(event_id: str = "supplier-event-1") -> SupplierDeactivatedEvent:
    return SupplierDeactivatedEvent(
        event_id=event_id,
        supplier_id="supplier-1",
        timestamp=datetime.now(UTC),
    )


async def test_cancels_only_pre_pickup_orders_and_deduplicates(order_store) -> None:
    async with order_store() as session, session.begin():
        session.add_all(
            [
                _order("open", OrderStatus.OPEN),
                _order("accepted", OrderStatus.ACCEPTED),
                _order("picked-up", OrderStatus.PICKED_UP),
                _order("awaiting", OrderStatus.AWAITING_APPROVAL),
                _order("completed", OrderStatus.COMPLETED),
                _order("other-supplier", OrderStatus.OPEN, "supplier-2"),
            ]
        )

    async with order_store() as session:
        assert await supplier_deactivation.process_supplier_deactivated(session, _event()) == 2
    async with order_store() as session:
        assert await supplier_deactivation.process_supplier_deactivated(session, _event()) == 0

    async with order_store() as session:
        statuses = {
            row.order_id: row.status for row in (await session.scalars(select(OrderTable))).all()
        }
        facts = (await session.scalars(select(OrderEventOutbox))).all()
        inbox = (await session.scalars(select(SupplierDeactivationInbox))).all()

    assert statuses == {
        "open": OrderStatus.CANCELLED,
        "accepted": OrderStatus.CANCELLED,
        "picked-up": OrderStatus.PICKED_UP,
        "awaiting": OrderStatus.AWAITING_APPROVAL,
        "completed": OrderStatus.COMPLETED,
        "other-supplier": OrderStatus.OPEN,
    }
    assert len(facts) == 2
    assert {fact.payload["order_id"] for fact in facts} == {"open", "accepted"}
    assert {fact.payload["event_type"] for fact in facts} == {"OrderCancelled"}
    assert all("supplier-1" in fact.payload["reason"] for fact in facts)
    assert all(
        OrderEvent.model_validate(fact.payload).event_type == OrderEventType.ORDER_CANCELLED
        for fact in facts
    )
    assert len(inbox) == 1 and inbox[0].event_id == "supplier-event-1"


async def test_drains_multiple_batches(order_store, monkeypatch) -> None:
    monkeypatch.setattr(supplier_deactivation, "BATCH_SIZE", 1)
    async with order_store() as session, session.begin():
        session.add_all([_order(f"open-{index}", OrderStatus.OPEN) for index in range(3)])

    async with order_store() as session:
        assert await supplier_deactivation.process_supplier_deactivated(session, _event()) == 3

    async with order_store() as session:
        assert len((await session.scalars(select(OrderEventOutbox))).all()) == 3


async def test_outbox_failure_rolls_back_cancellation(order_store, monkeypatch) -> None:
    async with order_store() as session, session.begin():
        session.add(_order("open", OrderStatus.OPEN))

    async def fail_outbox_write(_session, _events):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(supplier_deactivation.event_outbox, "create_events", fail_outbox_write)
    async with order_store() as session:
        with pytest.raises(RuntimeError, match="outbox unavailable"):
            await supplier_deactivation.process_supplier_deactivated(session, _event())

    async with order_store() as session:
        assert (await session.get(OrderTable, "open")).status == OrderStatus.OPEN
        assert (await session.scalars(select(OrderEventOutbox))).all() == []
        assert (await session.scalars(select(SupplierDeactivationInbox))).all() == []


async def test_consumer_acks_only_after_successful_processing(order_store, monkeypatch) -> None:
    monkeypatch.setattr(supplier_consumer, "SessionLocal", order_store)
    async with order_store() as session, session.begin():
        session.add(_order("open", OrderStatus.OPEN))

    supplier_event = _event()
    message = type("Message", (), {})()
    message.body = supplier_event.model_dump_json().encode()
    message.routing_key = "SupplierDeactivated"
    message.ack = AsyncMock()
    message.nack = AsyncMock()

    await supplier_consumer._handle_message(message)
    message.ack.assert_awaited_once()
    message.nack.assert_not_awaited()

    async with order_store() as session:
        assert (await session.get(OrderTable, "open")).status == OrderStatus.CANCELLED


async def test_consumer_requeues_transient_database_failure(monkeypatch) -> None:
    async def fail_processing(_session, _event):
        raise RuntimeError("database unavailable")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(supplier_consumer, "SessionLocal", FakeSession)
    monkeypatch.setattr(supplier_consumer, "process_supplier_deactivated", fail_processing)
    message = type("Message", (), {})()
    message.body = _event().model_dump_json().encode()
    message.routing_key = "SupplierDeactivated"
    message.ack = AsyncMock()
    message.nack = AsyncMock()

    await supplier_consumer._handle_message(message)

    message.nack.assert_awaited_once_with(requeue=True)
    message.ack.assert_not_awaited()

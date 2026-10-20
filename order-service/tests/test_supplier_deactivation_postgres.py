# AI-INFLUENCED: Verify pickup and supplier cancellation serialize on PostgreSQL with Codex.
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.order_event_outbox import OrderEventOutbox
from app.models.orders import OrderTable
from app.schemas.supplier_events import SupplierDeactivatedEvent
from app.services import orders, supplier_deactivation
from app.services.errors import OrderStateConflictError
from app.services.lifecycle import OrderStatus


def _accepted_order() -> OrderTable:
    return OrderTable(
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
    )


def _fact() -> SupplierDeactivatedEvent:
    return SupplierDeactivatedEvent(
        event_id="fact-1", supplier_id="supplier-1", timestamp=datetime.now(UTC)
    )


async def test_deactivation_winning_row_lock_blocks_pickup(postgres_sessions, monkeypatch) -> None:
    async with postgres_sessions() as session, session.begin():
        session.add(_accepted_order())

    cancellation_locked = asyncio.Event()
    release_cancellation = asyncio.Event()
    original_create_events = supplier_deactivation.event_outbox.create_events

    async def hold_cancellation(session, facts):
        cancellation_locked.set()
        await release_cancellation.wait()
        await original_create_events(session, facts)

    monkeypatch.setattr(supplier_deactivation.event_outbox, "create_events", hold_cancellation)

    async def cancel():
        async with postgres_sessions() as session:
            return await supplier_deactivation.process_supplier_deactivated(session, _fact())

    async def pickup():
        async with postgres_sessions() as session:
            return await orders.pickup_order(session, "order-1", "courier-1")

    cancellation = asyncio.create_task(cancel())
    try:
        await asyncio.wait_for(cancellation_locked.wait(), 5)
        pickup_attempt = asyncio.create_task(pickup())
        try:
            await asyncio.sleep(0.05)
            release_cancellation.set()
            assert await asyncio.wait_for(cancellation, 5) == 1
            with pytest.raises(OrderStateConflictError):
                await asyncio.wait_for(pickup_attempt, 5)
        finally:
            pickup_attempt.cancel()
    finally:
        release_cancellation.set()
        cancellation.cancel()

    async with postgres_sessions() as session:
        order = await session.get(OrderTable, "order-1")
        events = (await session.scalars(select(OrderEventOutbox))).all()
    assert order.status == OrderStatus.CANCELLED
    assert [event.payload["event_type"] for event in events] == ["OrderCancelled"]

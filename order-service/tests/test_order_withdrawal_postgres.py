# AI-INFLUENCED: Verify withdrawal idempotency and pickup races on PostgreSQL.
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.order_event_outbox import OrderEventOutbox
from app.models.order_requests import OrderRequest
from app.models.orders import OrderTable
from app.services import orders
from app.services.errors import OrderAccessDeniedError, OrderStateConflictError
from app.services.lifecycle import OrderStatus


def _accepted_order(order_id: str) -> OrderTable:
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
        status=OrderStatus.ACCEPTED,
    )


async def test_withdrawal_retry_cannot_withdraw_later_assignment(postgres_sessions):
    async with postgres_sessions() as session, session.begin():
        session.add(_accepted_order("order-1"))

    async with postgres_sessions() as session:
        first = await orders.withdraw_order(session, "order-1", "courier-1", "key-1")
    async with postgres_sessions() as session:
        await orders.accept_order(session, "order-1", "courier-1")
    async with postgres_sessions() as session:
        repeated = await orders.withdraw_order(session, "order-1", "courier-1", "key-1")

    assert repeated == first
    async with postgres_sessions() as session:
        order = await session.get(OrderTable, "order-1")
        request = await session.get(OrderRequest, "key-1")
        event_types = list((await session.scalars(select(OrderEventOutbox.payload))).all())
        assert order.status == OrderStatus.ACCEPTED
        assert order.courier_id == "courier-1"
        assert request.response["status"] == "OPEN"
        assert [item["event_type"] for item in event_types].count("CourierWithdrawn") == 1


async def test_pickup_and_withdrawal_cannot_both_commit(postgres_sessions):
    async with postgres_sessions() as session, session.begin():
        session.add(_accepted_order("order-1"))

    async def pickup():
        async with postgres_sessions() as session:
            return await orders.pickup_order(session, "order-1", "courier-1")

    async def withdraw():
        async with postgres_sessions() as session:
            return await orders.withdraw_order(session, "order-1", "courier-1", "key-1")

    results = await asyncio.gather(pickup(), withdraw(), return_exceptions=True)
    rejected = sum(
        isinstance(result, (OrderAccessDeniedError, OrderStateConflictError)) for result in results
    )
    assert rejected == 1
    async with postgres_sessions() as session:
        order = await session.get(OrderTable, "order-1")
        event_count = await session.scalar(select(func.count()).select_from(OrderEventOutbox))
        assert order.status in {OrderStatus.OPEN, OrderStatus.PICKED_UP}
        assert event_count == 1

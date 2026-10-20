# AI-influenced: Available-order deadline filtering test added with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models.order_release_tasks import OrderReleaseTask
from app.models.order_update_tasks import OrderUpdateTask
from app.models.orders import OrderTable
from app.repositories.orders import (
    list_assigned_completed_orders,
    list_available_orders,
    list_requested_completed_orders,
    list_requested_ongoing_orders,
)
from app.services.lifecycle import OrderStatus


class _AsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def scalars(self, statement):
        return self.session.scalars(statement)


def _open_order(order_id: str, deadline: datetime) -> OrderTable:
    return OrderTable(
        order_id=order_id,
        name="Collect lunch",
        details="Pick up lunch",
        reward=5,
        deadline=deadline,
        supplier_id="supplier-1",
        courier_id=None,
        requester_id="requester-1",
        reservation_id=f"reservation-{order_id}",
        pickup_location="The Deck",
        delivery_location="COM3",
        status=OrderStatus.OPEN,
    )


async def test_available_orders_exclude_overdue_open_orders() -> None:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def register_postgres_string_functions(connection, _record) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.create_function("char_length", 1, len)

    OrderTable.__table__.create(engine)
    OrderUpdateTask.__table__.create(engine)
    OrderReleaseTask.__table__.create(engine)

    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add_all(
            [
                _open_order("overdue", now - timedelta(minutes=1)),
                _open_order("future", now + timedelta(minutes=1)),
            ]
        )
        session.commit()

        orders = await list_available_orders(_AsyncSessionAdapter(session), "courier-1")

    engine.dispose()
    assert [order.order_id for order in orders] == ["future"]


async def test_participant_lists_filter_identity_and_status() -> None:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def register_postgres_string_functions(connection, _record) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.create_function("char_length", 1, len)

    OrderTable.__table__.create(engine)
    now = datetime.now(UTC)

    def order(
        order_id: str,
        status: OrderStatus,
        requester_id: str = "requester-1",
        courier_id: str | None = None,
        days_ago: int = 0,
    ) -> OrderTable:
        row = _open_order(order_id, now + timedelta(days=1 - days_ago))
        row.status = status
        row.requester_id = requester_id
        row.courier_id = courier_id
        row.created_at = now - timedelta(days=days_ago)
        return row

    with Session(engine) as session:
        session.add_all(
            [
                order("open", OrderStatus.OPEN),
                order("accepted", OrderStatus.ACCEPTED, courier_id="courier-1"),
                order("picked-up", OrderStatus.PICKED_UP, courier_id="courier-1"),
                order("awaiting", OrderStatus.AWAITING_APPROVAL, courier_id="courier-1"),
                order("completed-new", OrderStatus.COMPLETED, courier_id="courier-1"),
                order("completed-old", OrderStatus.COMPLETED, courier_id="courier-1", days_ago=2),
                order("completed-other-courier", OrderStatus.COMPLETED, courier_id="courier-2"),
                order(
                    "completed-other-requester", OrderStatus.COMPLETED, "requester-2", "courier-1"
                ),
                order("cancelled", OrderStatus.CANCELLED),
                order("expired", OrderStatus.EXPIRED),
                order("open-other-requester", OrderStatus.OPEN, "requester-2"),
            ]
        )
        session.commit()
        async_session = _AsyncSessionAdapter(session)

        ongoing = await list_requested_ongoing_orders(async_session, "requester-1")
        requested_completed = await list_requested_completed_orders(async_session, "requester-1")
        assigned_completed = await list_assigned_completed_orders(async_session, "courier-1")

    engine.dispose()
    assert [row.order_id for row in ongoing] == ["accepted", "awaiting", "open", "picked-up"]
    assert [row.order_id for row in requested_completed] == [
        "completed-other-courier",
        "completed-new",
        "completed-old",
    ]
    assert [row.order_id for row in assigned_completed] == [
        "completed-other-requester",
        "completed-new",
        "completed-old",
    ]

# AI-influenced: Available-order deadline filtering test added with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models.order_release_tasks import OrderReleaseTask
from app.models.order_update_tasks import OrderUpdateTask
from app.models.orders import OrderTable
from app.repositories.orders import list_available_orders
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

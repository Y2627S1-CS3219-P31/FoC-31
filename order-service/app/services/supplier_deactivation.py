# AI-INFLUENCED: Cancel eligible orders when their supplier is deactivated.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import OrderTable
from app.models.supplier_deactivation_inbox import SupplierDeactivationInbox
from app.repositories import order_event_outbox as event_outbox
from app.schemas.supplier_events import SupplierDeactivatedEvent
from app.services.lifecycle import OrderStatus, assert_transition
from foc_shared.events import OrderEvent, OrderEventType

BATCH_SIZE = 100


async def process_supplier_deactivated(
    session: AsyncSession, event: SupplierDeactivatedEvent
) -> int:
    """Cancel matching pre-pickup orders; commits each bounded batch with its facts."""
    cancelled = 0
    while True:
        async with session.begin():
            if await session.get(SupplierDeactivationInbox, event.event_id) is not None:
                return cancelled

            rows = await session.scalars(
                select(OrderTable)
                .where(
                    OrderTable.supplier_id == event.supplier_id,
                    OrderTable.status.in_((OrderStatus.OPEN, OrderStatus.ACCEPTED)),
                )
                .order_by(OrderTable.order_id)
                .limit(BATCH_SIZE)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            orders = list(rows.all())
            if not orders:
                session.add(SupplierDeactivationInbox(event_id=event.event_id))
                return cancelled

            now = datetime.now(UTC)
            facts: list[OrderEvent] = []
            for order in orders:
                # Recheck after the lock: pickup may have won the race.
                if order.status not in (OrderStatus.OPEN, OrderStatus.ACCEPTED):
                    continue
                assert_transition(OrderStatus(order.status), OrderStatus.CANCELLED)
                order.status = OrderStatus.CANCELLED
                facts.append(
                    OrderEvent(
                        event_type=OrderEventType.ORDER_CANCELLED,
                        order_id=order.order_id,
                        requester_id=order.requester_id,
                        courier_id=order.courier_id,
                        timestamp=now,
                        reason=f"Supplier {event.supplier_id} deactivated.",
                    )
                )
            if facts:
                await event_outbox.create_events(session, facts)
            cancelled += len(facts)

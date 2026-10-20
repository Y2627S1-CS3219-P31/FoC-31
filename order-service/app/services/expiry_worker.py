# AI-INFLUENCED: Batched order expiry and overdue signaling implemented with Codex.
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.orders import OrderTable
from app.repositories import order_event_outbox as event_outbox_repository
from app.repositories import orders as order_repository
from app.services.lifecycle import OrderStatus, assert_transition
from foc_shared.events import OrderEvent, OrderEventType

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 5
BATCH_SIZE = 100
OVERDUE_TARGET_SECONDS = 20
OVERDUE_SIGNAL_COOLDOWN_SECONDS = 60

_last_overdue_signal_at = 0.0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _signal_if_overdue(order_id: str, deadline: datetime, database_now: datetime) -> None:
    global _last_overdue_signal_at

    overdue_seconds = (_as_utc(database_now) - _as_utc(deadline)).total_seconds()
    if overdue_seconds <= OVERDUE_TARGET_SECONDS:
        return

    loop = asyncio.get_running_loop()
    signal_time = loop.time()
    if signal_time - _last_overdue_signal_at < OVERDUE_SIGNAL_COOLDOWN_SECONDS:
        return

    _last_overdue_signal_at = signal_time
    logger.error(
        "Order expiry exceeded its 20-second target",
        extra={
            "signal": "order_expiry_slo_breached",
            "order_id": order_id,
            "overdue_seconds": round(overdue_seconds, 2),
            "target_seconds": OVERDUE_TARGET_SECONDS,
        },
    )


async def _signal_oldest_overdue_order() -> None:
    async with SessionLocal() as session:
        due_order = await order_repository.get_oldest_due_order(session)

    if due_order is not None:
        order_id, deadline, database_now = due_order
        _signal_if_overdue(order_id, deadline, database_now)


async def _expire_batch() -> int:
    async with SessionLocal() as session, session.begin():
        orders = await order_repository.get_due_orders_for_expiry(session, BATCH_SIZE)
        if not orders:
            return 0

        database_now = await session.scalar(select(func.current_timestamp()))
        if database_now is None:
            raise RuntimeError("Could not read the database clock for order expiry.")

        eligible_orders: list[OrderTable] = []
        for order in orders:
            # Recheck after locking so only still-open, due orders transition.
            if order.status != OrderStatus.OPEN or _as_utc(order.deadline) > _as_utc(database_now):
                continue

            assert_transition(OrderStatus(order.status), OrderStatus.EXPIRED)
            eligible_orders.append(order)
            _signal_if_overdue(order.order_id, order.deadline, database_now)

        if not eligible_orders:
            return 0

        await order_repository.set_statuses(session, eligible_orders, OrderStatus.EXPIRED)
        await event_outbox_repository.create_events(
            session,
            [
                OrderEvent(
                    event_type=OrderEventType.ORDER_EXPIRED,
                    order_id=order.order_id,
                    requester_id=order.requester_id,
                    courier_id=order.courier_id,
                    timestamp=database_now,
                )
                for order in eligible_orders
            ],
        )
        return len(eligible_orders)


async def expire_due_orders() -> int:
    """Expire every currently due order, committing one bounded batch at a time."""
    total_expired = 0
    while True:
        await _signal_oldest_overdue_order()
        expired_count = await _expire_batch()
        if expired_count == 0:
            return total_expired
        total_expired += expired_count


async def run_expiry_sweeper() -> None:
    loop = asyncio.get_running_loop()
    while True:
        next_sweep_at = loop.time() + SWEEP_INTERVAL_SECONDS
        try:
            await expire_due_orders()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Could not complete the order expiry sweep")

        await asyncio.sleep(max(0, next_sweep_at - loop.time()))

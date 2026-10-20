# AI-INFLUENCED: Start overdue approvals through the existing durable workflow.
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.db import SessionLocal
from app.repositories import order_approval_tasks as approval_tasks
from app.repositories import order_event_outbox as event_outbox_repository
from app.repositories import orders as order_repository
from app.schemas.order_approval_events import OrderApprovalRequestedEvent, OrderApprovedEvent
from app.services.lifecycle import OrderStatus, assert_transition

logger = logging.getLogger(__name__)

APPROVAL_DELAY = timedelta(hours=24)
SWEEP_INTERVAL_SECONDS = 60
BATCH_SIZE = 100


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _start_batch() -> int:
    async with SessionLocal() as session, session.begin():
        cutoff = datetime.now(UTC) - APPROVAL_DELAY
        orders = await order_repository.get_due_orders_for_auto_approval(
            session, cutoff, BATCH_SIZE
        )
        started = 0
        for order in orders:
            # The row lock makes this recheck consistent with requester approval.
            if (
                order.status != OrderStatus.AWAITING_APPROVAL
                or order.awaiting_approval_at is None
                or _as_utc(order.awaiting_approval_at) > cutoff
            ):
                continue

            task = await approval_tasks.get_pending_for_order(session, order.order_id)
            if task is None:
                task = await approval_tasks.create_task(
                    session,
                    order_id=order.order_id,
                    reservation_id=order.reservation_id,
                    requester_id=order.requester_id,
                    courier_id=order.courier_id,
                )
                await event_outbox_repository.create_event(
                    session,
                    OrderApprovalRequestedEvent(
                        task_id=task.task_id,
                        order_id=task.order_id,
                        reservation_id=task.reservation_id,
                        requester_id=task.requester_id,
                        courier_id=task.courier_id,
                        timestamp=task.created_at,
                    ),
                )

            assert_transition(OrderStatus(order.status), OrderStatus.COMPLETED)
            await order_repository.set_status(session, order, OrderStatus.COMPLETED)
            await event_outbox_repository.create_event(
                session,
                OrderApprovedEvent(
                    task_id=task.task_id,
                    order_id=task.order_id,
                    reservation_id=task.reservation_id,
                    requester_id=task.requester_id,
                    courier_id=task.courier_id,
                    timestamp=datetime.now(UTC),
                ),
            )
            started += 1
        return started


async def auto_approve_due_orders() -> int:
    """Complete due orders locally while retaining one transfer task per order."""
    total = 0
    while True:
        count = await _start_batch()
        if count == 0:
            return total
        total += count


async def run_auto_approval_sweeper() -> None:
    while True:
        try:
            await auto_approve_due_orders()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Could not complete the order auto-approval sweep")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)

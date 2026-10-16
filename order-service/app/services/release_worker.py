# AI-INFLUENCED: Order-action publication and credit-outcome handling implemented with Codex.
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import aio_pika
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionLocal
from app.models.order_release_outbox import (
    COMPLETED,
    FAILED,
    PENDING,
    OrderReleaseOutbox,
    ReleaseAction,
)
from app.models.orders import OrderTable
from app.repositories import order_event_outbox as event_outbox_repository
from app.repositories import order_release_outbox as release_tasks
from app.repositories import orders as order_repository
from app.schemas.credit_events import CreditReleaseResult
from app.schemas.order_action_events import (
    OrderActionEvent,
    OrderActionEventType,
    OrderCancellationFailedEvent,
)
from app.services.lifecycle import OrderStatus, assert_transition
from foc_shared.events import OrderEvent, OrderEventType

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 5
ORDER_ACTION_EVENT_TYPES: dict[ReleaseAction, OrderActionEventType] = {
    ReleaseAction.DELETE: "OrderDelete",
    ReleaseAction.CANCEL: "OrderCancellationRequested",
    ReleaseAction.EXPIRE: "OrderExpired",
}


def _utc_datetime(value: datetime) -> datetime:
    """Normalize timestamps loaded by drivers that omit the UTC offset."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def build_order_action_event(task: OrderReleaseOutbox) -> OrderActionEvent | None:
    try:
        action = ReleaseAction(task.action)
    except ValueError:
        return None

    return OrderActionEvent(
        event_type=ORDER_ACTION_EVENT_TYPES[action],
        order_id=task.order_id,
        reservation_id=task.reservation_id,
        requester_id=task.requester_id,
        timestamp=task.created_at,
        reason=task.reason,
    )


async def publish_order_action(event: OrderActionEvent) -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=3)
    async with connection:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        exchange = await channel.declare_exchange(
            settings.order_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        await exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json().encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=event.event_type,
            mandatory=True,
        )


async def publish_pending_order_actions() -> None:
    async with SessionLocal() as session:
        task_ids = await release_tasks.list_unpublished_task_ids(session)

    for task_id in task_ids:
        async with SessionLocal() as session, session.begin():
            task = await release_tasks.get_task_for_update(session, task_id, skip_locked=True)
            if task is None or task.status != PENDING or task.published_at is not None:
                continue

            event = build_order_action_event(task)
            if event is None:
                _fail_task(task, "Unknown order action.")
                continue

            try:
                await publish_order_action(event)
            except Exception as exc:
                logger.warning(
                    "Could not publish pending Order action",
                    extra={"task_id": task_id},
                    exc_info=True,
                )
                error = str(exc)[:500]
            else:
                error = None
            await release_tasks.record_publication(session, task, error)


def _fail_task(task: OrderReleaseOutbox, error: str) -> None:
    task.status = FAILED
    task.last_error = error[:500]


def _complete_task(task: OrderReleaseOutbox) -> None:
    task.status = COMPLETED
    task.last_error = None


async def _record_cancellation_failed(
    session: AsyncSession, task: OrderReleaseOutbox, error: str
) -> None:
    _fail_task(task, error)
    await event_outbox_repository.create_event(
        session,
        OrderCancellationFailedEvent(
            task_id=task.task_id,
            order_id=task.order_id,
            reservation_id=task.reservation_id,
            requester_id=task.requester_id,
            timestamp=datetime.now(UTC),
            reason=task.last_error,
        ),
    )


async def _get_locked_order(session: AsyncSession, task: OrderReleaseOutbox) -> OrderTable | None:
    order = await order_repository.get_order_for_update(session, task.order_id)
    if order is None:
        _fail_task(task, "The order no longer exists.")
    return order


async def handle_delete(session: AsyncSession, task: OrderReleaseOutbox) -> None:
    order = await _get_locked_order(session, task)
    if order is None:
        return

    if order.status != OrderStatus.OPEN:
        _fail_task(task, "Order can no longer be deleted.")
        return
    if order.courier_id is not None:
        _fail_task(task, "An assigned order cannot be deleted.")
        return

    await order_repository.delete_order(session, order)
    _complete_task(task)


async def handle_cancel(session: AsyncSession, task: OrderReleaseOutbox) -> None:
    order = await _get_locked_order(session, task)
    if order is None:
        await _record_cancellation_failed(session, task, task.last_error or "Order not found.")
        return

    try:
        assert_transition(OrderStatus(order.status), OrderStatus.CANCELLED)
    except ValueError as exc:
        await _record_cancellation_failed(session, task, str(exc))
        return

    completed_at = datetime.now(UTC)
    await order_repository.set_status(session, order, OrderStatus.CANCELLED)
    await event_outbox_repository.create_event(
        session,
        OrderEvent(
            event_type=OrderEventType.ORDER_CANCELLED,
            order_id=order.order_id,
            requester_id=order.requester_id,
            courier_id=order.courier_id,
            timestamp=completed_at,
            reason=task.reason,
        ),
    )
    _complete_task(task)


async def handle_expire(session: AsyncSession, task: OrderReleaseOutbox) -> None:
    order = await _get_locked_order(session, task)
    if order is None:
        return

    if _utc_datetime(order.deadline) > datetime.now(UTC):
        _fail_task(task, "The order deadline has not passed.")
        return
    try:
        assert_transition(OrderStatus(order.status), OrderStatus.EXPIRED)
    except ValueError as exc:
        _fail_task(task, str(exc))
        return

    await order_repository.set_status(session, order, OrderStatus.EXPIRED)
    _complete_task(task)


async def handle_credit_release_failed(
    session: AsyncSession, task: OrderReleaseOutbox, event: CreditReleaseResult
) -> None:
    error = event.reason or "Credit Service rejected the release."
    if task.action == ReleaseAction.CANCEL.value:
        await _record_cancellation_failed(session, task, error)
        return
    _fail_task(task, error)


ActionHandler = Callable[[AsyncSession, OrderReleaseOutbox], Awaitable[None]]
ACTION_HANDLERS: dict[ReleaseAction, ActionHandler] = {
    ReleaseAction.DELETE: handle_delete,
    ReleaseAction.CANCEL: handle_cancel,
    ReleaseAction.EXPIRE: handle_expire,
}


async def process_release_result(session: AsyncSession, event: CreditReleaseResult) -> bool:
    """Apply a credit-domain fact to the matching local workflow, if one exists."""
    async with session.begin():
        task = await release_tasks.get_pending_by_reservation_for_update(
            session, event.reservation_id
        )
        if task is None:
            return False

        if event.event_type == "CreditReleaseFailed":
            await handle_credit_release_failed(session, task, event)
            return True

        try:
            action = ReleaseAction(task.action)
        except ValueError:
            _fail_task(task, "Unknown order action.")
            return True

        handler = ACTION_HANDLERS[action]
        await handler(session, task)
        return True


async def run_order_action_worker() -> None:
    while True:
        try:
            await publish_pending_order_actions()
        except Exception:
            logger.exception("Could not scan pending Order actions")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

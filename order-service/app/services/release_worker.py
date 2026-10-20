# AI-INFLUENCED: Order-action publication and credit-outcome handling implemented with Codex.
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_release_tasks import (
    COMPLETED,
    FAILED,
    PENDING,
    OrderReleaseTask,
    ReleaseAction,
)
from app.models.orders import OrderTable
from app.repositories import order_event_outbox as event_outbox_repository
from app.repositories import order_release_tasks as release_tasks
from app.repositories import orders as order_repository
from app.schemas.credit_events import CreditReleaseResult
from app.schemas.order_action_events import (
    OrderCancellationFailedEvent,
    OrderDeletedEvent,
    OrderDeletionFailedEvent,
)
from app.services.lifecycle import OrderStatus, assert_transition
from foc_shared.events import OrderEvent, OrderEventType


def _fail_task(task: OrderReleaseTask, error: str) -> None:
    task.status = FAILED
    task.last_error = error[:500]


def _complete_task(task: OrderReleaseTask) -> None:
    task.status = COMPLETED
    task.last_error = None


async def _record_cancellation_failed(
    session: AsyncSession, task: OrderReleaseTask, error: str
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


async def _record_deletion_failed(
    session: AsyncSession, task: OrderReleaseTask, error: str
) -> None:
    _fail_task(task, error)
    await event_outbox_repository.create_event(
        session,
        OrderDeletionFailedEvent(
            task_id=task.task_id,
            order_id=task.order_id,
            reservation_id=task.reservation_id,
            requester_id=task.requester_id,
            timestamp=datetime.now(UTC),
            reason=task.last_error,
        ),
    )


async def _get_locked_order(session: AsyncSession, task: OrderReleaseTask) -> OrderTable | None:
    order = await order_repository.get_order_for_update(session, task.order_id)
    if order is None:
        _fail_task(task, "The order no longer exists.")
    elif order.reservation_id != task.reservation_id:
        _fail_task(task, "The order reservation does not match the terminal-action task.")
        return None
    return order


async def handle_delete(
    session: AsyncSession, task: OrderReleaseTask, event: CreditReleaseResult
) -> None:
    if event.event_type == "CreditReleaseFailed":
        await _record_deletion_failed(
            session, task, event.reason or "Credit Service rejected the release."
        )
        return

    order = await _get_locked_order(session, task)
    if order is None:
        await _record_deletion_failed(session, task, task.last_error or "Order not found.")
        return

    if order.status != OrderStatus.OPEN:
        await _record_deletion_failed(session, task, "Order can no longer be deleted.")
        return
    if order.courier_id is not None:
        await _record_deletion_failed(session, task, "An assigned order cannot be deleted.")
        return

    await order_repository.delete_order(session, order)
    await event_outbox_repository.create_event(
        session,
        OrderDeletedEvent(
            task_id=task.task_id,
            order_id=task.order_id,
            reservation_id=task.reservation_id,
            requester_id=task.requester_id,
            timestamp=datetime.now(UTC),
        ),
    )
    _complete_task(task)


async def handle_cancel(
    session: AsyncSession, task: OrderReleaseTask, event: CreditReleaseResult
) -> None:
    if event.event_type == "CreditReleaseFailed":
        await _record_cancellation_failed(
            session, task, event.reason or "Credit Service rejected the release."
        )
        return

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


ActionHandler = Callable[[AsyncSession, OrderReleaseTask, CreditReleaseResult], Awaitable[None]]
ACTION_HANDLERS: dict[ReleaseAction, ActionHandler] = {
    ReleaseAction.DELETE: handle_delete,
    ReleaseAction.CANCEL: handle_cancel,
}


async def process_release_result(session: AsyncSession, event: CreditReleaseResult) -> bool:
    """Apply a credit-domain fact to the matching local workflow, if one exists."""
    async with session.begin():
        task = await release_tasks.get_task_for_update(session, event.task_id)
        if task is None:
            return False
        if task.status != PENDING:
            return False
        if task.reservation_id != event.reservation_id or (
            event.order_id is not None and task.order_id != event.order_id
        ):
            raise ValueError(f"Credit release result does not match task '{event.task_id}'.")

        try:
            action = ReleaseAction(task.action)
        except ValueError:
            _fail_task(task, "Unknown order action.")
            return True

        handler = ACTION_HANDLERS.get(action)
        if handler is None:
            _fail_task(task, "Unsupported release task action.")
            return True
        await handler(session, task, event)
        return True

# AI-INFLUENCED: Credit-transfer results applied to order approvals with Codex.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_approval_tasks import COMPLETED, FAILED, PENDING, OrderApprovalTask
from app.models.orders import OrderTable
from app.repositories import order_approval_tasks as approval_tasks
from app.repositories import order_event_outbox as event_outbox_repository
from app.repositories import orders as order_repository
from app.schemas.credit_events import CreditTransferResult
from app.schemas.order_approval_events import OrderApprovalFailedEvent, OrderApprovedEvent
from app.services.lifecycle import OrderStatus, assert_transition


def _record_failure(task: OrderApprovalTask, reason: str) -> None:
    task.status = FAILED
    task.last_error = reason[:500]


async def _record_order_approval_failed(
    session: AsyncSession, task: OrderApprovalTask, reason: str
) -> None:
    _record_failure(task, reason)
    await event_outbox_repository.create_event(
        session,
        OrderApprovalFailedEvent(
            task_id=task.task_id,
            order_id=task.order_id,
            reservation_id=task.reservation_id,
            requester_id=task.requester_id,
            timestamp=datetime.now(UTC),
            reason=task.last_error or reason,
        ),
    )


async def process_transfer_result(session: AsyncSession, event: CreditTransferResult) -> bool:
    """Apply a credit-transfer fact to its matching pending approval."""
    async with session.begin():
        task = await approval_tasks.get_task_for_update(session, event.task_id)
        if task is None or task.status != PENDING:
            return False
        if task.order_id != event.order_id or task.reservation_id != event.reservation_id:
            raise ValueError(f"Credit transfer result does not match task '{event.task_id}'.")

        order: OrderTable | None = await order_repository.get_order_for_update(
            session, task.order_id
        )
        if order is None:
            await _record_order_approval_failed(session, task, "The order no longer exists.")
            return True
        if (
            order.reservation_id != task.reservation_id
            or order.requester_id != task.requester_id
            or order.courier_id != task.courier_id
            or order.status != OrderStatus.AWAITING_APPROVAL
        ):
            await _record_order_approval_failed(
                session, task, "The order no longer matches the pending approval."
            )
            return True

        if event.event_type == "CreditTransferFailed":
            await _record_order_approval_failed(
                session, task, event.reason or "Credit Service rejected the transfer."
            )
            return True

        assert_transition(OrderStatus(order.status), OrderStatus.COMPLETED)
        await order_repository.set_status(session, order, OrderStatus.COMPLETED)
        task.status = COMPLETED
        task.last_error = None
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
        return True

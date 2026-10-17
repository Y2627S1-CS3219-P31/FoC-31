# AI-INFLUENCED: Apply credit amendment results to Order Service tasks with Codex.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_update_tasks import COMPLETED, PENDING, REJECTED
from app.repositories import order_event_outbox as event_outbox_repository
from app.repositories import order_update_tasks as update_tasks
from app.repositories import orders as order_repository
from app.schemas.credit_events import CreditAmendResult
from app.schemas.order_update_events import OrderUpdatedEvent, OrderUpdateFailedEvent
from app.schemas.orders import OrderUpdate
from app.services.lifecycle import OrderStatus


async def process_amendment_result(session: AsyncSession, event: CreditAmendResult) -> bool:
    async with session.begin():
        task = await update_tasks.get_task_for_update(session, event.task_id)
        if task is None:
            return False
        if task.status != PENDING:
            return False
        if (
            (event.order_id is not None and task.order_id != event.order_id)
            or task.reservation_id != event.reservation_id
            or task.requester_id != event.requester_id
            or task.proposed_order["reward"] != event.amount
        ):
            raise ValueError(f"Credit amendment result does not match task '{event.task_id}'.")
        if event.event_type == "CreditAmendRejected":
            task.status = REJECTED
            task.rejection_code = event.reason or "credit_rejected"
            task.last_error = event.reason or "Credit Service rejected the amendment."
            await event_outbox_repository.create_event(
                session,
                OrderUpdateFailedEvent(
                    task_id=task.task_id,
                    order_id=task.order_id,
                    reservation_id=task.reservation_id,
                    requester_id=task.requester_id,
                    timestamp=datetime.now(UTC),
                    reason=task.last_error,
                ),
            )
            return True

        order = await order_repository.get_order_for_update(session, task.order_id)
        if order is None or order.status != OrderStatus.OPEN or order.courier_id is not None:
            raise RuntimeError(f"Order '{task.order_id}' changed after its credit amendment.")
        if order.reservation_id != task.reservation_id:
            task.status = REJECTED
            task.rejection_code = "reservation_mismatch"
            task.last_error = "The order reservation does not match the update task."
            await event_outbox_repository.create_event(
                session,
                OrderUpdateFailedEvent(
                    task_id=task.task_id,
                    order_id=task.order_id,
                    reservation_id=task.reservation_id,
                    requester_id=task.requester_id,
                    timestamp=datetime.now(UTC),
                    reason=task.last_error,
                ),
            )
            return True
        await order_repository.update_order(
            order,
            OrderUpdate.model_validate(task.proposed_order, context={"stored_update": True}),
            session,
        )
        task.status = COMPLETED
        task.last_error = None
        await event_outbox_repository.create_event(
            session,
            OrderUpdatedEvent(
                task_id=task.task_id,
                order_id=task.order_id,
                reservation_id=task.reservation_id,
                requester_id=task.requester_id,
                timestamp=datetime.now(UTC),
            ),
        )
        return True

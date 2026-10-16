# AI-INFLUENCED: Order update outbox persistence implemented with Codex.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_update_tasks import PENDING, OrderUpdateTask


async def get_pending_for_order(session: AsyncSession, order_id: str) -> OrderUpdateTask | None:
    return await session.scalar(
        select(OrderUpdateTask).where(
            OrderUpdateTask.order_id == order_id,
            OrderUpdateTask.status == PENDING,
        )
    )


async def get_task_for_update(
    session: AsyncSession, task_id: str, *, skip_locked: bool = False
) -> OrderUpdateTask | None:
    return await session.scalar(
        select(OrderUpdateTask)
        .where(OrderUpdateTask.task_id == task_id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )


async def get_task(session: AsyncSession, task_id: str) -> OrderUpdateTask | None:
    return await session.get(OrderUpdateTask, task_id)


async def create_task(
    session: AsyncSession,
    *,
    order_id: str,
    requester_id: str,
    reservation_id: str,
    proposed_order: dict,
) -> OrderUpdateTask:
    task = OrderUpdateTask(
        order_id=order_id,
        requester_id=requester_id,
        reservation_id=reservation_id,
        proposed_order=proposed_order,
        status=PENDING,
    )
    session.add(task)
    await session.flush()
    return task

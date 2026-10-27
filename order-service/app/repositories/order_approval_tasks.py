# AI-INFLUENCED: Order approval task persistence implemented with Codex.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_approval_tasks import PENDING, OrderApprovalTask


async def get_pending_for_order(session: AsyncSession, order_id: str) -> OrderApprovalTask | None:
    return await session.scalar(
        select(OrderApprovalTask).where(
            OrderApprovalTask.order_id == order_id,
            OrderApprovalTask.status == PENDING,
        )
    )


async def get_task_for_update(session: AsyncSession, task_id: str) -> OrderApprovalTask | None:
    return await session.scalar(
        select(OrderApprovalTask)
        .where(OrderApprovalTask.task_id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def get_task(session: AsyncSession, task_id: str) -> OrderApprovalTask | None:
    return await session.get(OrderApprovalTask, task_id)


async def create_task(
    session: AsyncSession,
    *,
    order_id: str,
    reservation_id: str,
    requester_id: str,
    courier_id: str,
) -> OrderApprovalTask:
    task = OrderApprovalTask(
        order_id=order_id,
        reservation_id=reservation_id,
        requester_id=requester_id,
        courier_id=courier_id,
        status=PENDING,
    )
    session.add(task)
    await session.flush()
    return task

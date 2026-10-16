# AI-INFLUENCED: Credit-release workflow persistence implemented with Codex.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_release_tasks import PENDING, OrderReleaseTask, ReleaseAction


async def get_for_order(session: AsyncSession, order_id: str) -> OrderReleaseTask | None:
    """Return the pending release task that currently blocks another action."""
    return await session.scalar(
        select(OrderReleaseTask).where(
            OrderReleaseTask.order_id == order_id,
            OrderReleaseTask.status == PENDING,
        )
    )


async def get_task(session: AsyncSession, task_id: str) -> OrderReleaseTask | None:
    return await session.get(OrderReleaseTask, task_id)


async def get_task_for_update(
    session: AsyncSession, task_id: str, *, skip_locked: bool = False
) -> OrderReleaseTask | None:
    return await session.scalar(
        select(OrderReleaseTask)
        .where(OrderReleaseTask.task_id == task_id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )


async def create_task(
    session: AsyncSession,
    *,
    order_id: str,
    requester_id: str,
    reservation_id: str,
    action: ReleaseAction,
    reason: str | None = None,
) -> OrderReleaseTask:
    task = OrderReleaseTask(
        order_id=order_id,
        requester_id=requester_id,
        reservation_id=reservation_id,
        action=action.value,
        reason=reason,
        status=PENDING,
    )
    session.add(task)
    await session.flush()
    return task

# AI-INFLUENCED: Credit-release workflow persistence implemented with Codex.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_release_outbox import FAILED, PENDING, OrderReleaseOutbox, ReleaseAction

ACTIVE_STATUSES = (PENDING, FAILED)


async def get_for_order(session: AsyncSession, order_id: str) -> OrderReleaseOutbox | None:
    return await session.scalar(
        select(OrderReleaseOutbox).where(
            OrderReleaseOutbox.order_id == order_id,
            OrderReleaseOutbox.status.in_(ACTIVE_STATUSES),
        )
    )


async def get_task(session: AsyncSession, task_id: str) -> OrderReleaseOutbox | None:
    return await session.get(OrderReleaseOutbox, task_id)


async def get_pending_by_reservation_for_update(
    session: AsyncSession, reservation_id: str
) -> OrderReleaseOutbox | None:
    return await session.scalar(
        select(OrderReleaseOutbox)
        .where(
            OrderReleaseOutbox.reservation_id == reservation_id,
            OrderReleaseOutbox.status == PENDING,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def get_task_for_update(
    session: AsyncSession, task_id: str, *, skip_locked: bool = False
) -> OrderReleaseOutbox | None:
    return await session.scalar(
        select(OrderReleaseOutbox)
        .where(OrderReleaseOutbox.task_id == task_id)
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
) -> OrderReleaseOutbox:
    task = OrderReleaseOutbox(
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


async def list_unpublished_task_ids(session: AsyncSession, limit: int = 20) -> list[str]:
    result = await session.scalars(
        select(OrderReleaseOutbox.task_id)
        .where(
            OrderReleaseOutbox.status == PENDING,
            OrderReleaseOutbox.published_at.is_(None),
        )
        .order_by(
            OrderReleaseOutbox.attempts,
            OrderReleaseOutbox.created_at,
            OrderReleaseOutbox.task_id,
        )
        .limit(limit)
    )
    return list(result.all())


async def record_publication(
    session: AsyncSession, task: OrderReleaseOutbox, error: str | None
) -> None:
    task.attempts += 1
    task.last_error = error
    if error is None:
        task.published_at = datetime.now(UTC)
    await session.flush()

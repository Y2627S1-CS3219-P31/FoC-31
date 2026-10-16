# AI-INFLUENCED: Order event outbox persistence implemented with Codex.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_event_outbox import OrderEventOutbox
from app.schemas.order_action_events import OrderCancellationFailedEvent
from foc_shared.events import OrderEvent

OrderOutboxEvent = OrderEvent | OrderCancellationFailedEvent


async def create_event(session: AsyncSession, event: OrderOutboxEvent) -> OrderEventOutbox:
    task = OrderEventOutbox(payload=event.model_dump(mode="json"))
    session.add(task)
    await session.flush()
    return task


async def list_pending_event_ids(session: AsyncSession, limit: int = 20) -> list[str]:
    result = await session.scalars(
        select(OrderEventOutbox.event_id)
        .where(OrderEventOutbox.published_at.is_(None))
        .order_by(OrderEventOutbox.attempts, OrderEventOutbox.created_at, OrderEventOutbox.event_id)
        .limit(limit)
    )
    return list(result.all())


async def get_pending_for_update(session: AsyncSession, event_id: str) -> OrderEventOutbox | None:
    return await session.scalar(
        select(OrderEventOutbox)
        .where(OrderEventOutbox.event_id == event_id, OrderEventOutbox.published_at.is_(None))
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )


async def record_publication(
    session: AsyncSession, task: OrderEventOutbox, error: str | None
) -> None:
    task.attempts += 1
    task.last_error = error
    if error is None:
        task.published_at = datetime.now(UTC)
    await session.flush()

# AI-INFLUENCED: Retriable Supplier Service outbox persistence added with Codex.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_event_outbox import SupplierEventOutbox


async def list_pending_ids(session: AsyncSession, limit: int = 20) -> list[str]:
    rows = await session.scalars(
        select(SupplierEventOutbox.event_id)
        .where(SupplierEventOutbox.published_at.is_(None))
        .order_by(SupplierEventOutbox.created_at, SupplierEventOutbox.event_id)
        .limit(limit)
    )
    return list(rows.all())


async def get_pending_for_update(
    session: AsyncSession, event_id: str
) -> SupplierEventOutbox | None:
    return await session.scalar(
        select(SupplierEventOutbox)
        .where(
            SupplierEventOutbox.event_id == event_id,
            SupplierEventOutbox.published_at.is_(None),
        )
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )


async def record_publication(
    session: AsyncSession, event: SupplierEventOutbox, error: str | None
) -> None:
    event.attempts += 1
    event.last_error = error
    if error is None:
        event.published_at = datetime.now(UTC)
    await session.flush()

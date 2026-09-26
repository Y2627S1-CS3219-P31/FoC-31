from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import aio_pika
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionLocal
from app.models.outbox import OutboxEvent
from foc_shared.events import UserRegisteredEvent

logger = logging.getLogger(__name__)

async def enqueue_user_registered(
    session: AsyncSession, *, user_id: str, email: str
) -> None:
    event = UserRegisteredEvent(user_id=user_id, email=email)
    session.add(
        OutboxEvent(
            event_type=event.event_type,
            aggregate_id=user_id,
            payload=event.model_dump_json(),
        )
    )


async def publish_user_registered(*, payload: str) -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=3)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            settings.user_events_exchange,
            aio_pika.ExchangeType.FANOUT,
            durable=True,
        )
        await exchange.publish(
            aio_pika.Message(body=payload.encode()),
            routing_key="",
        )


async def dispatch_outbox_once(session: AsyncSession) -> None:
    rows = list(
        (
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(50)
            )
        ).all()
    )
    for row in rows:
        row.attempts += 1
        try:
            await publish_user_registered(payload=row.payload)
            row.published_at = datetime.now(UTC).replace(tzinfo=None)
            row.last_error = None
        except Exception as exc:
            row.last_error = str(exc)[:500]
            logger.exception("Event delivery failed for outbox id=%s", row.id)
    await session.commit()


async def outbox_worker() -> None:
    while True:
        try:
            async with SessionLocal() as session:
                await dispatch_outbox_once(session)
        except Exception:
            logger.exception("Outbox worker iteration failed")
        await asyncio.sleep(5)

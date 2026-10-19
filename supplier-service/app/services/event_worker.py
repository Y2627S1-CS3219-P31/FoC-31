# AI-INFLUENCED: Publish durable Supplier Service facts with broker confirmation.
from __future__ import annotations

import asyncio
import logging

import aio_pika

from app.config import settings
from app.db import SessionLocal
from app.repositories import supplier_event_outbox as outbox
from app.schemas.supplier_events import SUPPLIER_EVENTS_EXCHANGE, SupplierDeactivatedEvent

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 5


async def publish_supplier_event(event: SupplierDeactivatedEvent) -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=3)
    async with connection:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        exchange = await channel.declare_exchange(
            SUPPLIER_EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        await exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json().encode(),
                content_type="application/json",
                message_id=event.event_id,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=event.event_type,
            mandatory=True,
            timeout=5,
        )


async def publish_pending_events() -> None:
    async with SessionLocal() as session:
        event_ids = await outbox.list_pending_ids(session)

    for event_id in event_ids:
        async with SessionLocal() as session, session.begin():
            row = await outbox.get_pending_for_update(session, event_id)
            if row is None:
                continue
            try:
                event = SupplierDeactivatedEvent.model_validate(row.payload)
                async with asyncio.timeout(10):
                    await publish_supplier_event(event)
            except Exception as exc:
                logger.warning(
                    "Could not publish supplier event",
                    extra={"event_id": event_id},
                    exc_info=True,
                )
                error = str(exc)[:500]
            else:
                error = None
            await outbox.record_publication(session, row, error)


async def run_event_worker() -> None:
    while True:
        try:
            await publish_pending_events()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Could not scan pending supplier events")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

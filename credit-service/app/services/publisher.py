# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Publishes credit events to RabbitMQ (Credit F2.1.4 / F2.1.5).

Publication is best-effort: the reservation outcome is already committed, and
a messaging failure must not roll back or fail the credit operation (matches
the user-service pattern for UserRegistered).
"""

from __future__ import annotations

import logging

import aio_pika

from app.config import settings
from foc_shared.events import ReservationEvent

logger = logging.getLogger(__name__)


async def publish_reservation_event(event: ReservationEvent) -> None:
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=3)
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                settings.credit_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
            )
            await exchange.publish(
                aio_pika.Message(body=event.model_dump_json().encode()),
                routing_key=event.event_type.value,
            )
    except Exception:
        logger.exception(
            "Failed to publish %s for user_id=%s order_id=%s",
            event.event_type.value,
            event.user_id,
            event.order_id,
        )

# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Publishes credit events to RabbitMQ (Credit F2.1.4 / F2.1.5).

Two callers with different failure semantics:

- ``publish_reservation_event`` reports the outcome of a reservation that is
  already committed, so publication is best-effort: a messaging failure must
  not roll back or fail the credit operation (matches the user-service pattern
  for UserRegistered).
- ``publish_credit_event`` answers an Order Service task. The reply *is* the
  contract, so a failure is raised and the consumer retries the message.
"""

from __future__ import annotations

import logging
import time

import aio_pika

from app.config import settings
from app.observability import metrics
from app.schemas.interop import CreditResultEvent
from foc_shared.events import ReservationEvent

logger = logging.getLogger(__name__)


async def _publish(event_type: str, payload: str) -> None:
    """Publish one event and count the outcome either way.

    The counter is what makes a lost reservation event visible at all:
    ``publish_reservation_event`` swallows failures, so without
    ``credit_event_publish_total{result="failed"}`` a broker outage would only
    be discoverable by grepping logs.
    """
    started = time.perf_counter()
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=3)
        async with connection:
            channel = await connection.channel(publisher_confirms=True)
            exchange = await channel.declare_exchange(
                settings.credit_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
            )
            await exchange.publish(
                aio_pika.Message(
                    body=payload.encode(),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=event_type,
            )
    except Exception:
        metrics.record_event_publish(event_type, ok=False, duration=time.perf_counter() - started)
        raise
    else:
        metrics.record_event_publish(event_type, ok=True, duration=time.perf_counter() - started)


async def publish_reservation_event(event: ReservationEvent) -> None:
    try:
        await _publish(event.event_type.value, event.model_dump_json())
    except Exception:
        logger.exception(
            "Failed to publish %s for user_id=%s order_id=%s",
            event.event_type.value,
            event.user_id,
            event.order_id,
        )


async def publish_credit_event(event: CreditResultEvent) -> None:
    """Publish a task reply; exceptions propagate so the consumer can retry."""
    await _publish(event.event_type, event.model_dump_json())

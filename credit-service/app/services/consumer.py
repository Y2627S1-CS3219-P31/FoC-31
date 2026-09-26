# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""RabbitMQ consumption for credit-service.

Subscribes to:
- `foc.order.events` (topic): OrderCompleted, OrderCancelled, OrderExpired,
  CourierWithdrawn — handled per the D1 credit backlog. CourierWithdrawn is
  bound explicitly so the no-op behaviour (credits stay reserved, F4.1.2) is
  exercised rather than silently missing.
- `foc.events` (fanout): UserRegistered → initial account provisioning (F1.1).

Redelivered events are handled idempotently by CreditService.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import aio_pika

from app.config import settings
from app.db import SessionLocal
from app.errors import ServiceError
from app.services.credit_service import CreditService
from foc_shared.events import OrderEvent, OrderEventType, UserRegisteredEvent

logger = logging.getLogger(__name__)

_ORDER_EVENT_BINDINGS: tuple[str, ...] = (
    OrderEventType.ORDER_COMPLETED.value,
    OrderEventType.ORDER_CANCELLED.value,
    OrderEventType.COURIER_WITHDRAWN.value,
    OrderEventType.ORDER_EXPIRED.value,
)


async def handle_order_event(event: OrderEvent) -> None:
    """Entry point for tests and the queue callback."""
    async with SessionLocal() as session:
        await CreditService(session).handle_order_event(event)


async def handle_user_registered_event(event: UserRegisteredEvent) -> None:
    async with SessionLocal() as session:
        await CreditService(session).handle_user_registered_event(event)


class CreditEventConsumer:
    """Long-running consumer started from the app lifespan."""

    def __init__(self) -> None:
        self._stop = asyncio.Event()

    async def run(self) -> None:
        """Reconnect loop: survives broker outages and connection loss."""
        while True:
            try:
                connection = await aio_pika.connect_robust(settings.rabbitmq_url)
                async with connection:
                    await self._consume(connection)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Credit event consumer crashed; reconnecting in 5s.")
                await asyncio.sleep(5)

    async def _consume(self, connection: aio_pika.abc.AbstractRobustConnection) -> None:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        order_exchange = await channel.declare_exchange(
            settings.order_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        order_queue = await channel.declare_queue(settings.order_events_queue, durable=True)
        for routing_key in _ORDER_EVENT_BINDINGS:
            await order_queue.bind(order_exchange, routing_key=routing_key)
        await order_queue.consume(
            partial(self._dispatch, model=OrderEvent, handler=handle_order_event)
        )

        user_exchange = await channel.declare_exchange(
            settings.user_events_exchange, aio_pika.ExchangeType.FANOUT, durable=True
        )
        user_queue = await channel.declare_queue(settings.user_events_queue, durable=True)
        await user_queue.bind(user_exchange)
        await user_queue.consume(
            partial(self._dispatch, model=UserRegisteredEvent, handler=handle_user_registered_event)
        )

        logger.info(
            "Credit event consumer started (queue %s on %s; queue %s on %s).",
            settings.order_events_queue,
            settings.order_events_exchange,
            settings.user_events_queue,
            settings.user_events_exchange,
        )
        await self._stop.wait()

    async def _dispatch(
        self, message: aio_pika.abc.AbstractIncomingMessage, *, model, handler
    ) -> None:
        try:
            event = model.model_validate_json(message.body)
            await handler(event)
        except ServiceError:
            # Data/business mismatch (e.g. completion with no reservation):
            # log and acknowledge so a poison message does not loop forever.
            logger.error(
                "Business error handling event; acknowledging (body=%s)",
                message.body,
                exc_info=True,
            )
            await message.ack()
        except Exception:
            logger.exception("Failed to handle event; requeueing (body=%s)", message.body)
            await message.nack(requeue=True)
        else:
            await message.ack()

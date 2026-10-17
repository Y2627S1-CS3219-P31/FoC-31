# AI-INFLUENCED: Confirmed RabbitMQ order event publication implemented with Codex.
from __future__ import annotations

import aio_pika

from app.config import settings
from app.schemas.order_action_events import OrderActionEvent, OrderLocalOutcomeEvent
from app.schemas.order_update_events import (
    OrderUpdateOutcomeEvent,
    OrderUpdateRequestedEvent,
)
from foc_shared.events import OrderEvent, OrderEventType

OrderPublishableEvent = (
    OrderEvent
    | OrderActionEvent
    | OrderLocalOutcomeEvent
    | OrderUpdateRequestedEvent
    | OrderUpdateOutcomeEvent
)


def _routing_key(event: OrderPublishableEvent) -> str:
    if isinstance(event.event_type, OrderEventType):
        return event.event_type.value
    return event.event_type


async def publish_order_event(event: OrderPublishableEvent, *, event_id: str) -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=3)
    async with connection:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        exchange = await channel.declare_exchange(
            settings.order_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        await exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json().encode(),
                content_type="application/json",
                message_id=event_id,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=_routing_key(event),
            mandatory=True,
            timeout=5,
        )

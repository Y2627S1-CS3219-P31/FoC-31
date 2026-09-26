from __future__ import annotations

import logging

import aio_pika

from app.config import settings
from foc_shared.events import UserRegisteredEvent

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "foc.events"


async def publish_user_registered(*, user_id: str, email: str) -> None:
    """So credit-service can provision the account"""
    event = UserRegisteredEvent(user_id=user_id, email=email)
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=3)
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                EXCHANGE_NAME, aio_pika.ExchangeType.FANOUT, durable=True
            )
            await exchange.publish(
                aio_pika.Message(body=event.model_dump_json().encode()),
                routing_key="",
            )
    except Exception:
        logger.exception("Failed to publish UserRegistered for user_id=%s", user_id)
# AI-INFLUENCED: Consume SupplierDeactivated facts with durable acknowledgements.
from __future__ import annotations

import asyncio
import logging

import aio_pika
from pydantic import ValidationError

from app.config import settings
from app.db import SessionLocal
from app.schemas.supplier_events import SUPPLIER_EVENTS_EXCHANGE, SupplierDeactivatedEvent
from app.services.supplier_deactivation import process_supplier_deactivated

logger = logging.getLogger(__name__)
QUEUE_NAME = "order-service.supplier-deactivated"


async def _handle_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    try:
        event = SupplierDeactivatedEvent.model_validate_json(message.body)
        if event.event_type != message.routing_key:
            raise ValueError("Supplier event routing key does not match its payload.")
        async with SessionLocal() as session:
            await process_supplier_deactivated(session, event)
    except (ValidationError, ValueError):
        logger.exception("Invalid supplier deactivation event")
        await message.nack(requeue=False)
    except Exception:
        logger.exception("Could not apply supplier deactivation")
        await message.nack(requeue=True)
    else:
        await message.ack()


async def run_supplier_consumer() -> None:
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=10)
                exchange = await channel.declare_exchange(
                    SUPPLIER_EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
                )
                queue = await channel.declare_queue(QUEUE_NAME, durable=True)
                await queue.bind(exchange, routing_key="SupplierDeactivated")
                await queue.consume(_handle_message)
                await asyncio.Future()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Supplier deactivation consumer disconnected")
            await asyncio.sleep(5)

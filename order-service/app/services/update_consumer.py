# AI-INFLUENCED: Consume durable credit amendment replies with Codex.
from __future__ import annotations

import asyncio
import logging

import aio_pika
from pydantic import ValidationError

from app.config import settings
from app.db import SessionLocal
from app.schemas.credit_events import CreditAmendResult
from app.services.update_worker import process_amendment_result

logger = logging.getLogger(__name__)


async def _handle_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    try:
        result = CreditAmendResult.model_validate_json(message.body)
        if result.event_type != message.routing_key:
            raise ValueError("Amendment reply routing key does not match its payload.")
        async with SessionLocal() as session:
            matched = await process_amendment_result(session, result)
        if not matched:
            logger.info(
                "Ignoring credit amendment result with no pending update",
                extra={"task_id": result.task_id, "reservation_id": result.reservation_id},
            )
    except (ValidationError, ValueError):
        logger.exception("Invalid credit amendment result")
        await message.nack(requeue=False)
    except Exception:
        logger.exception("Could not apply credit amendment result")
        await message.nack(requeue=True)
    else:
        await message.ack()


async def run_update_consumer() -> None:
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=10)
                exchange = await channel.declare_exchange(
                    settings.credit_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
                )
                queue = await channel.declare_queue(settings.amendment_results_queue, durable=True)
                for routing_key in ("CreditAmended", "CreditAmendRejected"):
                    await queue.bind(exchange, routing_key=routing_key)
                await queue.consume(_handle_message)
                await asyncio.Future()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Credit amendment result consumer disconnected")
            await asyncio.sleep(5)

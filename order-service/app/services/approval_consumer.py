# AI-INFLUENCED: Credit-transfer result consumer implemented with Codex.
from __future__ import annotations

import asyncio
import logging

import aio_pika
from pydantic import ValidationError

from app.config import settings
from app.db import SessionLocal
from app.schemas.credit_events import CreditTransferResult
from app.services.approval_worker import process_transfer_result

logger = logging.getLogger(__name__)


async def _handle_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    try:
        event = CreditTransferResult.model_validate_json(message.body)
        if event.event_type != message.routing_key:
            raise ValueError("Credit transfer result routing key does not match its payload.")
        async with SessionLocal() as session:
            matched = await process_transfer_result(session, event)
        if not matched:
            logger.info(
                "Ignoring credit transfer with no pending order approval",
                extra={"task_id": event.task_id, "reservation_id": event.reservation_id},
            )
    except (ValidationError, ValueError):
        logger.exception("Invalid credit transfer result event")
        await message.nack(requeue=False)
    except Exception:
        # Retry until the order state and its outcome event commit together.
        logger.exception("Could not apply credit transfer result")
        await message.nack(requeue=True)
    else:
        await message.ack()


async def run_approval_consumer() -> None:
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=10)
                exchange = await channel.declare_exchange(
                    settings.credit_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
                )
                queue = await channel.declare_queue(settings.approval_results_queue, durable=True)
                for routing_key in ("CreditTransferSucceeded", "CreditTransferFailed"):
                    await queue.bind(exchange, routing_key=routing_key)
                await queue.consume(_handle_message)
                await asyncio.Future()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Credit approval-result consumer disconnected")
            await asyncio.sleep(5)

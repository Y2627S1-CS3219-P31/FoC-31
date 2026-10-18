# AI-INFLUENCED: Order update publication and credit-outcome tests implemented with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.order_event_outbox import OrderEventOutbox
from app.models.order_update_tasks import COMPLETED, PENDING, REJECTED, OrderUpdateTask
from app.models.orders import OrderTable
from app.schemas.credit_events import CreditAmendResult
from app.services import update_consumer, update_worker
from app.services.lifecycle import OrderStatus


@pytest.fixture
async def maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def add_postgres_string_functions(connection, _record):
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.create_function("char_length", 1, len)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session, session.begin():
        session.add(
            OrderTable(
                order_id="order-1",
                name="Lunch",
                details="Bring lunch",
                reward=5,
                deadline=datetime.now(UTC) + timedelta(hours=2),
                supplier_id="supplier-1",
                requester_id="user-1",
                reservation_id="reservation-1",
                pickup_location="Library",
                delivery_location="Dorm",
                status=OrderStatus.OPEN,
            )
        )
    yield sessions
    await engine.dispose()


async def _task(maker, *, reward: int = 20):
    async with maker() as session, session.begin():
        task = OrderUpdateTask(
            order_id="order-1",
            requester_id="user-1",
            reservation_id="reservation-1",
            proposed_order={
                "name": "New lunch",
                "details": "Bring lunch",
                "reward": reward,
                "deadline": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
                "supplier_id": "supplier-1",
                "pickup_location": "Library",
                "delivery_location": "Dorm",
            },
        )
        session.add(task)
        await session.flush()
        return task.task_id


def _result(task_id, *, rejected=False, amount: int = 20):
    return CreditAmendResult(
        event_type="CreditAmendRejected" if rejected else "CreditAmended",
        task_id=task_id,
        order_id="order-1",
        reservation_id="reservation-1",
        requester_id="user-1",
        amount=amount,
        reason="insufficient_credits" if rejected else None,
    )


async def test_success_reply_commits_order_and_task_together(maker):
    task_id = await _task(maker)
    async with maker() as session:
        await update_worker.process_amendment_result(session, _result(task_id))
    async with maker() as session:
        assert (await session.get(OrderTable, "order-1")).reward == 20
        assert (await session.get(OrderUpdateTask, task_id)).status == COMPLETED
        outcome = (await session.scalars(select(OrderEventOutbox))).one()
        assert outcome.payload == {
            "event_type": "OrderUpdated",
            "task_id": task_id,
            "order_id": "order-1",
            "reservation_id": "reservation-1",
            "requester_id": "user-1",
            "timestamp": outcome.payload["timestamp"],
        }
        await session.rollback()
        await update_worker.process_amendment_result(session, _result(task_id))
        assert len(list(await session.scalars(select(OrderEventOutbox)))) == 1


async def test_failed_order_commit_keeps_success_reply_retryable(maker):
    task_id = await _task(maker)
    async with maker() as session:

        def fail_commit(_session):
            raise SQLAlchemyError("commit failed")

        event.listen(session.sync_session, "before_commit", fail_commit)
        with pytest.raises(SQLAlchemyError, match="commit failed"):
            await update_worker.process_amendment_result(session, _result(task_id))
        event.remove(session.sync_session, "before_commit", fail_commit)

    async with maker() as session:
        assert (await session.get(OrderTable, "order-1")).reward == 5
        assert (await session.get(OrderUpdateTask, task_id)).status == PENDING
        assert list(await session.scalars(select(OrderEventOutbox))) == []
        await session.rollback()
        await update_worker.process_amendment_result(session, _result(task_id))
    async with maker() as session:
        assert (await session.get(OrderTable, "order-1")).reward == 20
        assert (await session.scalars(select(OrderEventOutbox))).one().payload[
            "event_type"
        ] == "OrderUpdated"


async def test_rejection_keeps_order_and_clears_pending_task(maker):
    task_id = await _task(maker)
    async with maker() as session:
        await update_worker.process_amendment_result(session, _result(task_id, rejected=True))
    async with maker() as session:
        assert (await session.get(OrderTable, "order-1")).reward == 5
        task = await session.get(OrderUpdateTask, task_id)
        assert task.status == REJECTED
        assert task.last_error == "insufficient_credits"
        outcome = (await session.scalars(select(OrderEventOutbox))).one()
        assert outcome.payload == {
            "event_type": "OrderUpdateFailed",
            "task_id": task_id,
            "order_id": "order-1",
            "reservation_id": "reservation-1",
            "requester_id": "user-1",
            "timestamp": outcome.payload["timestamp"],
            "reason": "insufficient_credits",
        }


async def test_failed_rejection_commit_keeps_reply_retryable(maker):
    task_id = await _task(maker)
    async with maker() as session:

        def fail_commit(_session):
            raise SQLAlchemyError("commit failed")

        event.listen(session.sync_session, "before_commit", fail_commit)
        with pytest.raises(SQLAlchemyError, match="commit failed"):
            await update_worker.process_amendment_result(session, _result(task_id, rejected=True))
        event.remove(session.sync_session, "before_commit", fail_commit)

    async with maker() as session:
        task = await session.get(OrderUpdateTask, task_id)
        assert task.status == PENDING
        assert task.last_error is None
        assert list(await session.scalars(select(OrderEventOutbox))) == []


async def test_unchanged_reward_can_be_applied_after_credit_approval(maker):
    task_id = await _task(maker, reward=5)
    async with maker() as session:
        assert (await session.get(OrderUpdateTask, task_id)).status == PENDING
        assert (await session.get(OrderTable, "order-1")).name == "Lunch"

    async with maker() as session:
        await update_worker.process_amendment_result(session, _result(task_id, amount=5))
    async with maker() as session:
        assert (await session.get(OrderUpdateTask, task_id)).status == COMPLETED
        assert (await session.get(OrderTable, "order-1")).name == "New lunch"


@pytest.mark.parametrize(
    ("field", "value"),
    [("reservation_id", "another-reservation"), ("order_id", "another-order")],
)
async def test_amendment_result_must_match_task_correlation_fields(maker, field, value):
    task_id = await _task(maker)
    result = _result(task_id).model_copy(update={field: value})

    async with maker() as session:
        with pytest.raises(ValueError, match="does not match task"):
            await update_worker.process_amendment_result(session, result)

    async with maker() as session:
        assert (await session.get(OrderUpdateTask, task_id)).status == PENDING
        assert (await session.get(OrderTable, "order-1")).reward == 5


async def test_unknown_or_completed_update_result_is_ignored(maker):
    task_id = await _task(maker)
    unknown = _result("unknown-task")
    async with maker() as session:
        assert await update_worker.process_amendment_result(session, unknown) is False
        assert await update_worker.process_amendment_result(session, _result(task_id)) is True
        assert await update_worker.process_amendment_result(session, _result(task_id)) is False


async def test_order_reservation_must_match_update_task(maker):
    task_id = await _task(maker)
    async with maker() as session, session.begin():
        order = await session.get(OrderTable, "order-1")
        order.reservation_id = "another-reservation"

    async with maker() as session:
        assert await update_worker.process_amendment_result(session, _result(task_id)) is True

    async with maker() as session:
        task = await session.get(OrderUpdateTask, task_id)
        assert task.status == REJECTED
        assert task.last_error == "The order reservation does not match the update task."
        assert (await session.get(OrderTable, "order-1")).reward == 5
        outcome = (await session.scalars(select(OrderEventOutbox))).one()
        assert outcome.payload["event_type"] == "OrderUpdateFailed"


async def test_accepted_update_can_finish_after_its_deadline_passes(maker):
    task_id = await _task(maker)
    async with maker() as session, session.begin():
        task = await session.get(OrderUpdateTask, task_id)
        proposed = dict(task.proposed_order)
        proposed["deadline"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        task.proposed_order = proposed

    async with maker() as session:
        await update_worker.process_amendment_result(session, _result(task_id))

    async with maker() as session:
        assert (await session.get(OrderUpdateTask, task_id)).status == COMPLETED


async def test_reply_is_acknowledged_only_after_order_commit(maker, monkeypatch):
    task_id = await _task(maker)
    monkeypatch.setattr(update_consumer, "SessionLocal", maker)

    class Message:
        routing_key = "CreditAmended"
        body = _result(task_id).model_dump_json().encode()

        def __init__(self):
            self.acked = False
            self.requeued = None

        async def ack(self):
            self.acked = True

        async def nack(self, *, requeue):
            self.requeued = requeue

    failure = AsyncMock(side_effect=SQLAlchemyError("commit failed"))
    monkeypatch.setattr(update_consumer, "process_amendment_result", failure)
    first = Message()
    await update_consumer._handle_message(first)
    assert first.acked is False
    assert first.requeued is True

    monkeypatch.setattr(
        update_consumer, "process_amendment_result", update_worker.process_amendment_result
    )
    second = Message()
    await update_consumer._handle_message(second)
    assert second.acked is True
    assert second.requeued is None


async def test_consumer_rejects_routing_key_payload_mismatch(monkeypatch):
    message = type(
        "Message",
        (),
        {
            "routing_key": "CreditAmendRejected",
            "body": _result("task-1").model_dump_json().encode(),
            "ack": AsyncMock(),
            "nack": AsyncMock(),
        },
    )()
    await update_consumer._handle_message(message)
    message.ack.assert_not_awaited()
    message.nack.assert_awaited_once_with(requeue=False)

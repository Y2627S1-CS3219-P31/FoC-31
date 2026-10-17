# AI-INFLUENCED: Generic credit-release workflow tests implemented with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.order_event_outbox import OrderEventOutbox
from app.models.order_release_tasks import (
    COMPLETED,
    FAILED,
    PENDING,
    OrderReleaseTask,
    ReleaseAction,
)
from app.models.orders import OrderTable
from app.repositories import order_release_tasks as release_repository
from app.schemas.credit_events import CreditReleaseResult
from app.services import release_consumer, release_worker
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
    yield sessions
    await engine.dispose()


async def _seed_task(
    maker,
    action: ReleaseAction,
    *,
    status: OrderStatus = OrderStatus.OPEN,
    deadline: datetime | None = None,
) -> str:
    async with maker() as session, session.begin():
        order = OrderTable(
            order_id="order-1",
            name="Lunch",
            details="Bring lunch",
            reward=5,
            deadline=deadline or datetime.now(UTC) + timedelta(hours=1),
            supplier_id="supplier-1",
            requester_id="requester-1",
            courier_id="courier-1" if status == OrderStatus.ACCEPTED else None,
            reservation_id="reservation-1",
            pickup_location="Library",
            delivery_location="Dorm",
            status=status,
        )
        session.add(order)
        task = await release_repository.create_task(
            session,
            order_id=order.order_id,
            requester_id=order.requester_id,
            reservation_id=order.reservation_id,
            action=action,
            reason="requester_cancelled" if action == ReleaseAction.CANCEL else None,
        )
        return task.task_id


def _result(
    event_type: str = "CreditReleased",
    *,
    task_id: str = "missing-task",
    order_id: str | None = "order-1",
    reservation_id: str = "reservation-1",
) -> CreditReleaseResult:
    return CreditReleaseResult(
        event_type=event_type,
        task_id=task_id,
        order_id=order_id,
        reservation_id=reservation_id,
        timestamp=datetime.now(UTC),
        reason="release_rejected" if event_type == "CreditReleaseFailed" else None,
    )


async def test_credit_released_deletes_order_and_completes_task(maker) -> None:
    task_id = await _seed_task(maker, ReleaseAction.DELETE)
    async with maker() as session:
        assert await release_worker.process_release_result(session, _result(task_id=task_id))

    async with maker() as session:
        assert await session.get(OrderTable, "order-1") is None
        assert (await session.get(OrderReleaseTask, task_id)).status == COMPLETED
        event_task = (await session.scalars(select(OrderEventOutbox))).one()
        assert event_task.payload == {
            "event_type": "OrderDeleted",
            "task_id": task_id,
            "order_id": "order-1",
            "reservation_id": "reservation-1",
            "requester_id": "requester-1",
            "timestamp": event_task.payload["timestamp"],
        }


async def test_credit_released_cancels_order_and_records_final_event(maker) -> None:
    task_id = await _seed_task(maker, ReleaseAction.CANCEL, status=OrderStatus.ACCEPTED)
    async with maker() as session:
        assert await release_worker.process_release_result(session, _result(task_id=task_id))

    async with maker() as session:
        order = await session.get(OrderTable, "order-1")
        assert order.status == OrderStatus.CANCELLED
        assert (await session.get(OrderReleaseTask, task_id)).status == COMPLETED
        event_task = (await session.scalars(select(OrderEventOutbox))).one()
        assert event_task.payload["event_type"] == "OrderCancelled"
        assert event_task.payload["reason"] == "requester_cancelled"


@pytest.mark.parametrize("deadline_offset_seconds", [-60, 60])
async def test_credit_result_does_not_drive_order_expiry(
    maker, deadline_offset_seconds: int
) -> None:
    task_id = await _seed_task(
        maker,
        ReleaseAction.EXPIRE,
        deadline=datetime.now(UTC) + timedelta(seconds=deadline_offset_seconds),
    )
    async with maker() as session:
        await release_worker.process_release_result(session, _result(task_id=task_id))

    async with maker() as session:
        assert (await session.get(OrderTable, "order-1")).status == OrderStatus.OPEN
        task = await session.get(OrderReleaseTask, task_id)
        assert task.status == FAILED
        assert task.last_error == "Unsupported release task action."
        assert (await session.scalars(select(OrderEventOutbox))).all() == []


async def test_unknown_and_duplicate_release_events_are_no_ops(maker) -> None:
    async with maker() as session:
        assert await release_worker.process_release_result(session, _result()) is False

    task_id = await _seed_task(maker, ReleaseAction.CANCEL, status=OrderStatus.ACCEPTED)
    async with maker() as session:
        assert await release_worker.process_release_result(session, _result(task_id=task_id))
    async with maker() as session:
        assert (
            await release_worker.process_release_result(session, _result(task_id=task_id)) is False
        )


async def test_failed_delete_records_failure_without_deleting_order(maker) -> None:
    task_id = await _seed_task(maker, ReleaseAction.DELETE)
    async with maker() as session:
        assert (
            await release_worker.process_release_result(
                session, _result("CreditReleaseFailed", task_id=task_id)
            )
            is True
        )
    async with maker() as session:
        assert await session.get(OrderTable, "order-1") is not None
        task = await session.get(OrderReleaseTask, task_id)
        assert task.status == FAILED
        assert task.last_error == "release_rejected"
        event_task = (await session.scalars(select(OrderEventOutbox))).one()
        assert event_task.payload == {
            "event_type": "OrderDeletionFailed",
            "task_id": task_id,
            "order_id": "order-1",
            "reservation_id": "reservation-1",
            "requester_id": "requester-1",
            "timestamp": event_task.payload["timestamp"],
            "reason": "release_rejected",
        }


async def test_failed_cancel_records_failure_without_changing_order(maker) -> None:
    task_id = await _seed_task(maker, ReleaseAction.CANCEL, status=OrderStatus.ACCEPTED)

    async with maker() as session:
        assert (
            await release_worker.process_release_result(
                session, _result("CreditReleaseFailed", task_id=task_id)
            )
            is True
        )

    async with maker() as session:
        order = await session.get(OrderTable, "order-1")
        assert order.status == OrderStatus.ACCEPTED
        task = await session.get(OrderReleaseTask, task_id)
        assert task.status == FAILED
        assert task.last_error == "release_rejected"
        event_task = (await session.scalars(select(OrderEventOutbox))).one()
        assert event_task.payload == {
            "event_type": "OrderCancellationFailed",
            "task_id": task_id,
            "order_id": "order-1",
            "reservation_id": "reservation-1",
            "requester_id": "requester-1",
            "timestamp": event_task.payload["timestamp"],
            "reason": "release_rejected",
        }


@pytest.mark.parametrize("event_type", ["CreditReleased", "CreditReleaseFailed"])
async def test_delete_result_commit_failure_rolls_back_and_remains_retryable(
    maker, event_type: str
) -> None:
    task_id = await _seed_task(maker, ReleaseAction.DELETE)
    async with maker() as session:

        def fail_commit(_session):
            raise SQLAlchemyError("commit failed")

        event.listen(session.sync_session, "before_commit", fail_commit)
        with pytest.raises(SQLAlchemyError, match="commit failed"):
            await release_worker.process_release_result(
                session, _result(event_type, task_id=task_id)
            )
        event.remove(session.sync_session, "before_commit", fail_commit)

    async with maker() as session:
        assert await session.get(OrderTable, "order-1") is not None
        assert (await session.get(OrderReleaseTask, task_id)).status == PENDING
        assert list(await session.scalars(select(OrderEventOutbox))) == []
        await session.rollback()
        await release_worker.process_release_result(session, _result(event_type, task_id=task_id))

    async with maker() as session:
        task = await session.get(OrderReleaseTask, task_id)
        event_task = (await session.scalars(select(OrderEventOutbox))).one()
        if event_type == "CreditReleased":
            assert await session.get(OrderTable, "order-1") is None
            assert task.status == COMPLETED
            assert event_task.payload["event_type"] == "OrderDeleted"
        else:
            assert await session.get(OrderTable, "order-1") is not None
            assert task.status == FAILED
            assert event_task.payload["event_type"] == "OrderDeletionFailed"


@pytest.mark.parametrize("event_type", ["CreditReleased", "CreditReleaseFailed"])
async def test_cancel_result_commit_failure_rolls_back_task_order_and_event(
    maker, event_type: str
) -> None:
    task_id = await _seed_task(maker, ReleaseAction.CANCEL, status=OrderStatus.ACCEPTED)
    async with maker() as session:

        def fail_commit(_session):
            raise SQLAlchemyError("commit failed")

        event.listen(session.sync_session, "before_commit", fail_commit)
        with pytest.raises(SQLAlchemyError, match="commit failed"):
            await release_worker.process_release_result(
                session, _result(event_type, task_id=task_id)
            )
        event.remove(session.sync_session, "before_commit", fail_commit)

    async with maker() as session:
        assert (await session.get(OrderTable, "order-1")).status == OrderStatus.ACCEPTED
        assert (await session.get(OrderReleaseTask, task_id)).status == PENDING
        assert list(await session.scalars(select(OrderEventOutbox))) == []


async def test_dispatcher_calls_handler_mapped_to_local_action(maker, monkeypatch) -> None:
    task_id = await _seed_task(maker, ReleaseAction.CANCEL, status=OrderStatus.ACCEPTED)
    handler = AsyncMock()
    monkeypatch.setitem(release_worker.ACTION_HANDLERS, ReleaseAction.CANCEL, handler)

    async with maker() as session:
        assert await release_worker.process_release_result(session, _result(task_id=task_id))

    handler.assert_awaited_once()
    assert handler.await_args.args[1].action == ReleaseAction.CANCEL.value


@pytest.mark.parametrize(
    ("field", "value"),
    [("reservation_id", "another-reservation"), ("order_id", "another-order")],
)
async def test_credit_result_must_match_task_correlation_fields(maker, field, value):
    task_id = await _seed_task(maker, ReleaseAction.DELETE)
    result = _result(task_id=task_id).model_copy(update={field: value})

    async with maker() as session:
        with pytest.raises(ValueError, match="does not match task"):
            await release_worker.process_release_result(session, result)

    async with maker() as session:
        assert (await session.get(OrderReleaseTask, task_id)).status == PENDING
        assert await session.get(OrderTable, "order-1") is not None


async def test_order_reservation_must_match_local_release_task(maker):
    task_id = await _seed_task(maker, ReleaseAction.DELETE)
    async with maker() as session, session.begin():
        task = await session.get(OrderReleaseTask, task_id)
        task.reservation_id = "different-reservation"

    async with maker() as session:
        assert await release_worker.process_release_result(
            session,
            _result(task_id=task_id, reservation_id="different-reservation"),
        )

    async with maker() as session:
        assert (await session.get(OrderTable, "order-1")).status == OrderStatus.OPEN
        assert (await session.get(OrderReleaseTask, task_id)).status == FAILED
        outcome = (await session.scalars(select(OrderEventOutbox))).one()
        assert outcome.payload["event_type"] == "OrderDeletionFailed"


async def test_consumer_acknowledges_unmatched_release(monkeypatch) -> None:
    message = AsyncMock()
    message.body = _result().model_dump_json().encode()
    message.routing_key = "CreditReleased"
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr(release_consumer, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        release_consumer,
        "process_release_result",
        AsyncMock(return_value=False),
    )

    await release_consumer._handle_message(message)

    message.ack.assert_awaited_once()
    message.nack.assert_not_awaited()


async def test_consumer_requeues_database_failure(monkeypatch) -> None:
    message = AsyncMock()
    message.body = _result().model_dump_json().encode()
    message.routing_key = "CreditReleased"
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr(release_consumer, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        release_consumer,
        "process_release_result",
        AsyncMock(side_effect=SQLAlchemyError("database unavailable")),
    )

    await release_consumer._handle_message(message)

    message.ack.assert_not_awaited()
    message.nack.assert_awaited_once_with(requeue=True)

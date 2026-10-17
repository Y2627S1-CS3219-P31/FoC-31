# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Order Service task protocol: release/amend requests and their replies."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.reservation import ReservationStatus
from app.schemas.interop import OrderActionEvent, OrderUpdateRequestedEvent
from app.services import publisher
from app.services.credit_service import CreditService
from foc_shared.events import OrderEvent, OrderEventType


@pytest.fixture
def published(monkeypatch):
    """Capture task replies instead of talking to RabbitMQ."""
    events = []

    async def _capture(event) -> None:
        events.append(event)

    async def _noop(event) -> None:
        return None

    monkeypatch.setattr(publisher, "publish_credit_event", _capture)
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop)
    return events


def _release_event(
    event_type: str = "OrderDeletionRequested",
    *,
    task_id: str = "task-1",
    order_id: str = "order-1",
    reservation_id: str,
    requester_id: str = "requester",
) -> OrderActionEvent:
    return OrderActionEvent(
        event_type=event_type,
        task_id=task_id,
        order_id=order_id,
        reservation_id=reservation_id,
        requester_id=requester_id,
        timestamp=datetime.now(UTC),
    )


def _update_event(
    *,
    task_id: str = "task-u1",
    order_id: str = "order-1",
    reservation_id: str,
    requester_id: str = "requester",
    reward: int,
) -> OrderUpdateRequestedEvent:
    return OrderUpdateRequestedEvent(
        task_id=task_id,
        order_id=order_id,
        reservation_id=reservation_id,
        requester_id=requester_id,
        reward=reward,
        timestamp=datetime.now(UTC),
    )


async def _setup(session) -> tuple[CreditService, str]:
    service = CreditService(session)
    await service.ensure_account("requester")
    await service.ensure_account("courier")
    reservation = await service.reserve(user_id="requester", order_id="order-1", amount=40)
    return service, reservation.id


# ── release requests ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("event_type", ["OrderDeletionRequested", "OrderCancellationRequested"])
async def test_release_request_releases_and_replies(session, published, event_type):
    service, reservation_id = await _setup(session)

    await service.handle_release_requested(
        _release_event(event_type, reservation_id=reservation_id)
    )

    requester = await service.get_balances("requester")
    assert requester.available_balance == 100
    assert requester.reserved_balance == 0
    reservation = await service._reservations.get_by_order_id("order-1")
    assert reservation.status == ReservationStatus.RELEASED.value

    assert len(published) == 1
    reply = published[0]
    assert reply.event_type == "CreditReleased"
    assert reply.task_id == "task-1"
    assert reply.order_id == "order-1"
    assert reply.reservation_id == reservation_id
    assert reply.reason is None


async def test_duplicate_release_task_republishes_the_same_reply(session, published):
    service, reservation_id = await _setup(session)
    event = _release_event(reservation_id=reservation_id)

    await service.handle_release_requested(event)
    await service.handle_release_requested(event)  # repeated delivery

    # Released once, answered twice with the identical outcome.
    requester = await service.get_balances("requester")
    assert requester.available_balance == 100
    assert requester.reserved_balance == 0
    assert [reply.event_type for reply in published] == [
        "CreditReleased",
        "CreditReleased",
    ]
    assert len(await service.list_transactions("requester")) == 3  # alloc, reserve, release


async def test_release_of_unknown_reservation_reports_failure(session, published):
    service, _ = await _setup(session)

    await service.handle_release_requested(_release_event(reservation_id="does-not-exist"))

    assert len(published) == 1
    reply = published[0]
    assert reply.event_type == "CreditReleaseFailed"
    assert reply.reason == "Reservation was not found."
    requester = await service.get_balances("requester")
    assert requester.reserved_balance == 40


async def test_release_for_another_order_reports_failure(session, published):
    service, reservation_id = await _setup(session)

    await service.handle_release_requested(
        _release_event(order_id="other-order", reservation_id=reservation_id)
    )

    assert published[0].event_type == "CreditReleaseFailed"
    assert published[0].reason == "Reservation does not belong to this order."
    requester = await service.get_balances("requester")
    assert requester.reserved_balance == 40


async def test_release_for_another_requester_reports_failure(session, published):
    service, reservation_id = await _setup(session)

    await service.handle_release_requested(
        _release_event(reservation_id=reservation_id, requester_id="intruder")
    )

    assert published[0].event_type == "CreditReleaseFailed"
    assert published[0].reason == "Reservation does not belong to this requester."


async def test_release_after_transfer_reports_failure(session, published):
    service, reservation_id = await _setup(session)
    await service.transfer(
        reservation_id, "courier", caller_user_id="requester", caller_role="client"
    )

    await service.handle_release_requested(_release_event(reservation_id=reservation_id))

    assert published[0].event_type == "CreditReleaseFailed"
    assert "transferred" in published[0].reason
    courier = await service.get_balances("courier")
    assert courier.available_balance == 140


# ── amendment requests ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("reward", "expected_available", "expected_reserved"),
    [(70, 30, 70), (10, 90, 10), (40, 60, 40)],
)
async def test_update_request_amends_and_replies(
    session, published, reward, expected_available, expected_reserved
):
    service, reservation_id = await _setup(session)

    await service.handle_update_requested(
        _update_event(reservation_id=reservation_id, reward=reward)
    )

    requester = await service.get_balances("requester")
    assert requester.available_balance == expected_available
    assert requester.reserved_balance == expected_reserved
    reservation = await service._reservations.get_by_order_id("order-1")
    assert reservation.amount == reward

    assert len(published) == 1
    reply = published[0]
    assert reply.event_type == "CreditAmended"
    assert reply.task_id == "task-u1"
    assert reply.amount == reward
    assert reply.requester_id == "requester"


async def test_duplicate_update_task_is_applied_once(session, published):
    service, reservation_id = await _setup(session)
    event = _update_event(reservation_id=reservation_id, reward=70)

    await service.handle_update_requested(event)
    await service.handle_update_requested(event)  # repeated delivery

    requester = await service.get_balances("requester")
    assert requester.available_balance == 30
    assert requester.reserved_balance == 70
    assert [reply.event_type for reply in published] == [
        "CreditAmended",
        "CreditAmended",
    ]
    # alloc, reserve, amendment — the duplicate task added nothing.
    assert len(await service.list_transactions("requester")) == 3


async def test_update_beyond_available_credits_is_rejected(session, published):
    service, reservation_id = await _setup(session)

    await service.handle_update_requested(_update_event(reservation_id=reservation_id, reward=500))

    assert published[0].event_type == "CreditAmendRejected"
    assert "available" in published[0].reason
    assert published[0].amount == 500
    requester = await service.get_balances("requester")
    assert requester.available_balance == 60
    assert requester.reserved_balance == 40


async def test_update_of_released_reservation_is_rejected(session, published):
    service, reservation_id = await _setup(session)
    await service.handle_order_event(
        OrderEvent(
            event_type=OrderEventType.ORDER_EXPIRED,
            order_id="order-1",
            requester_id="requester",
            timestamp=datetime.now(UTC),
        )
    )
    published.clear()  # expiry publishes no reply

    await service.handle_update_requested(_update_event(reservation_id=reservation_id, reward=70))

    assert published[0].event_type == "CreditAmendRejected"
    assert "released" in published[0].reason


async def test_expired_order_publishes_no_reply(session, published):
    service, _ = await _setup(session)

    await service.handle_order_event(
        OrderEvent(
            event_type=OrderEventType.ORDER_EXPIRED,
            order_id="order-1",
            requester_id="requester",
            timestamp=datetime.now(UTC),
        )
    )

    assert published == []
    requester = await service.get_balances("requester")
    assert requester.available_balance == 100

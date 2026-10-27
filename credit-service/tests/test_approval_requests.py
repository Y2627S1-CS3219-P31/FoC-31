# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Order approval transfer protocol: ``OrderApprovalRequested`` and its reply.

The Order Service records an approval, asks credit-service to settle the
reservation to the courier, and waits for exactly one ``CreditTransferSucceeded``
or ``CreditTransferFailed`` keyed by ``task_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.reservation import ReservationStatus
from app.schemas.interop import (
    CreditTransferResult,
    OrderApprovalRequestedEvent,
)
from app.services import publisher
from app.services.credit_service import CreditService


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


def _approval_event(
    *,
    task_id: str = "task-t1",
    order_id: str = "order-1",
    reservation_id: str,
    requester_id: str = "requester",
    courier_id: str = "courier",
) -> OrderApprovalRequestedEvent:
    return OrderApprovalRequestedEvent(
        task_id=task_id,
        order_id=order_id,
        reservation_id=reservation_id,
        requester_id=requester_id,
        courier_id=courier_id,
        timestamp=datetime.now(UTC),
    )


async def _setup(session) -> tuple[CreditService, str]:
    service = CreditService(session)
    await service.ensure_account("requester")
    await service.ensure_account("courier")
    reservation = await service.reserve(user_id="requester", order_id="order-1", amount=40)
    return service, reservation.id


# ── happy path ───────────────────────────────────────────────────────────────


async def test_approval_request_transfers_and_replies(session, published):
    service, reservation_id = await _setup(session)

    await service.handle_approval_requested(_approval_event(reservation_id=reservation_id))

    requester = await service.get_balances("requester")
    courier = await service.get_balances("courier")
    assert requester.available_balance == 60
    assert requester.reserved_balance == 0
    assert courier.available_balance == 140
    settlement = await service._reservations.get(reservation_id)
    assert settlement.status == ReservationStatus.TRANSFERRED.value

    assert len(published) == 1
    reply = published[0]
    assert reply.event_type == "CreditTransferSucceeded"
    assert reply.task_id == "task-t1"
    assert reply.order_id == "order-1"
    assert reply.reservation_id == reservation_id
    assert reply.reason is None
    # The Order consumer validates the reply against this strict model.
    CreditTransferResult.model_validate_json(reply.model_dump_json())


async def test_reply_carries_exactly_the_contract_fields(session, published):
    service, reservation_id = await _setup(session)

    await service.handle_approval_requested(
        _approval_requested := _approval_event(reservation_id=reservation_id)
    )

    assert _approval_requested.event_type == "OrderApprovalRequested"
    # Order's CreditTransferResult forbids extra fields; adding requester_id or
    # amount here would make the reply undeliverable to the Order saga.
    assert set(published[0].model_dump()) == {
        "event_type",
        "task_id",
        "order_id",
        "reservation_id",
        "timestamp",
        "reason",
    }


# ── idempotency ──────────────────────────────────────────────────────────────


async def test_duplicate_approval_task_republishes_the_same_reply(session, published):
    service, reservation_id = await _setup(session)
    event = _approval_event(reservation_id=reservation_id)

    await service.handle_approval_requested(event)
    await service.handle_approval_requested(event)

    courier = await service.get_balances("courier")
    assert courier.available_balance == 140  # settled once, not twice
    assert len(published) == 2
    assert {reply.event_type for reply in published} == {"CreditTransferSucceeded"}


async def test_second_task_for_the_same_reservation_is_answered_as_success(session, published):
    service, reservation_id = await _setup(session)
    await service.handle_approval_requested(_approval_event(reservation_id=reservation_id))

    await service.handle_approval_requested(
        _approval_event(task_id="task-t2", reservation_id=reservation_id)
    )

    # A second task for an already-settled reservation is answered as success
    # (the courier already has the credits) but must not move money again.
    courier = await service.get_balances("courier")
    assert courier.available_balance == 140
    assert published[-1].event_type == "CreditTransferSucceeded"
    assert published[-1].task_id == "task-t2"


# ── definitive failures ──────────────────────────────────────────────────────


async def test_approval_of_unknown_reservation_reports_failure(session, published):
    service, _ = await _setup(session)

    await service.handle_approval_requested(_approval_event(reservation_id="ghost"))

    assert published[0].event_type == "CreditTransferFailed"
    assert published[0].reason == "Reservation was not found."


async def test_approval_for_another_order_reports_failure(session, published):
    service, reservation_id = await _setup(session)

    await service.handle_approval_requested(
        _approval_event(order_id="order-2", reservation_id=reservation_id)
    )

    assert published[0].event_type == "CreditTransferFailed"
    assert "does not belong to this order" in published[0].reason
    requester = await service.get_balances("requester")
    assert requester.reserved_balance == 40  # untouched


async def test_approval_for_another_requester_reports_failure(session, published):
    service, reservation_id = await _setup(session)

    await service.handle_approval_requested(
        _approval_event(requester_id="someone-else", reservation_id=reservation_id)
    )

    assert published[0].event_type == "CreditTransferFailed"
    assert "does not belong to this requester" in published[0].reason


async def test_approval_of_released_reservation_reports_failure(session, published):
    service, reservation_id = await _setup(session)
    await service.release(reservation_id, caller_user_id="requester", caller_role="client")

    await service.handle_approval_requested(_approval_event(reservation_id=reservation_id))

    assert published[0].event_type == "CreditTransferFailed"
    assert "released" in published[0].reason
    requester = await service.get_balances("requester")
    assert requester.available_balance == 100


async def test_approval_creates_courier_account_when_missing_and_succeeds(session, published):
    """Courier with no pre-existing account: account is auto-created and transfer succeeds."""
    service, reservation_id = await _setup(session)

    await service.handle_approval_requested(
        _approval_event(reservation_id=reservation_id, courier_id="brand-new-courier")
    )

    assert published[0].event_type == "CreditTransferSucceeded"
    courier = await service.get_balances("brand-new-courier")
    # initial allocation (100) + reward (40)
    assert courier.available_balance == 140
    CreditTransferResult.model_validate_json(published[0].model_dump_json())


async def test_approval_creates_courier_account_and_transfers_when_account_missing(
    session, published
):
    """Courier delivers before UserRegistered reaches credit-service.

    handle_approval_requested must create the account and complete the transfer
    rather than recording a definitive CreditTransferFailed.
    """
    service = CreditService(session)
    await service.ensure_account("requester")
    # Courier account intentionally absent — simulates the race window.
    reservation = await service.reserve(user_id="requester", order_id="order-race", amount=40)

    await service.handle_approval_requested(
        _approval_event(
            reservation_id=reservation.id,
            order_id="order-race",
            courier_id="late-courier",
        )
    )

    assert published[0].event_type == "CreditTransferSucceeded"
    courier = await service.get_balances("late-courier")
    # initial allocation (100) + reward (40)
    assert courier.available_balance == 140


async def test_user_registered_after_approval_leaves_balance_unchanged(session, published):
    """A UserRegistered event arriving after ensure_account was called during
    approval must not grant a second initial allocation.
    """
    service = CreditService(session)
    await service.ensure_account("requester")
    reservation = await service.reserve(user_id="requester", order_id="order-race2", amount=40)
    await service.handle_approval_requested(
        _approval_event(
            reservation_id=reservation.id,
            order_id="order-race2",
            courier_id="late-courier2",
        )
    )
    balance_after_approval = (await service.get_balances("late-courier2")).available_balance

    # Simulate the delayed UserRegistered event arriving now.
    from foc_shared.events import UserRegisteredEvent

    await service.handle_user_registered_event(
        UserRegisteredEvent(user_id="late-courier2", email="late@example.com")
    )

    balance_after_registered = (await service.get_balances("late-courier2")).available_balance
    assert balance_after_registered == balance_after_approval

    from app.models.transaction import TransactionKind

    txns = await service._transactions.list("late-courier2")
    allocation_count = sum(1 for t in txns if t.kind == TransactionKind.ALLOCATION.value)
    assert allocation_count == 1


# ── transactionality and retry behaviour ─────────────────────────────────────


async def test_transfer_and_task_result_commit_once(session, published, monkeypatch):
    service, reservation_id = await _setup(session)
    calls = []
    original = session.commit

    async def counting_commit() -> None:
        calls.append(1)
        await original()

    monkeypatch.setattr(session, "commit", counting_commit)

    await service.handle_approval_requested(_approval_event(reservation_id=reservation_id))

    # Settlement and its recorded outcome are one transaction, not two.
    assert len(calls) == 1
    courier = await service.get_balances("courier")
    assert courier.available_balance == 140
    assert published[0].event_type == "CreditTransferSucceeded"


async def test_publish_failure_keeps_the_transfer_and_replays_it(session, monkeypatch):
    service, reservation_id = await _setup(session)
    event = _approval_event(reservation_id=reservation_id)
    calls = []

    async def _flaky(reply) -> None:
        calls.append(reply)
        if len(calls) == 1:
            raise RuntimeError("broker unavailable")

    monkeypatch.setattr(publisher, "publish_credit_event", _flaky)

    with pytest.raises(RuntimeError):
        await service.handle_approval_requested(event)

    # The transfer committed; only the reply failed.
    courier = await service.get_balances("courier")
    assert courier.available_balance == 140
    assert await service._task_results.get(event.task_id) is not None

    # The redelivery replays the recorded success instead of settling again.
    await service.handle_approval_requested(event)
    assert calls[-1].event_type == "CreditTransferSucceeded"
    assert (await service.get_balances("courier")).available_balance == 140


async def test_transfer_exhaustion_replays_the_recorded_success(session, published):
    service, reservation_id = await _setup(session)
    event = _approval_event(reservation_id=reservation_id)
    await service.handle_approval_requested(event)
    published.clear()

    await service.report_transfer_retries_exhausted(event, RuntimeError("broker down"))

    assert [reply.event_type for reply in published] == ["CreditTransferSucceeded"]


async def test_transfer_exhaustion_reports_failure_when_nothing_was_recorded(session, published):
    service, reservation_id = await _setup(session)
    event = _approval_event(reservation_id=reservation_id)

    await service.report_transfer_retries_exhausted(event, RuntimeError("database down"))

    reply = published[0]
    assert reply.event_type == "CreditTransferFailed"
    assert reply.reason.startswith("Retry limit exceeded")
    CreditTransferResult.model_validate_json(reply.model_dump_json())
    requester = await service.get_balances("requester")
    assert requester.reserved_balance == 40  # the transfer never happened


async def test_settled_reservation_is_not_offered_for_release(session, published):
    service, reservation_id = await _setup(session)
    await service.handle_approval_requested(_approval_event(reservation_id=reservation_id))

    with pytest.raises(Exception) as caught:
        await service.release(reservation_id, caller_user_id="requester", caller_role="client")

    # Already settled: releasing would mint credits back to the requester.
    assert "cannot be released" in str(caught.value)
    assert (await service.get_balances("requester")).available_balance == 60
    status = getattr(caught.value, "status_code", None)
    assert status == 409

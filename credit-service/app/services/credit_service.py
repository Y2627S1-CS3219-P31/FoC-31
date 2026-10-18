# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Core credit-economy business logic (Credit Service D1 backlog).

Implements:
- F1  account provisioning + balance tracking/queries
- F2  reservation (+ validation, events, state) and amendment
- F3  transfer on order completion, idempotent
- F4  release on cancellation/expiry; never on courier withdrawal
- F5  transaction-history recording + retrieval

Order Service tasks (``OrderDeletionRequested``/``OrderCancellationRequested``
→ release, ``OrderUpdateRequested`` → amend) are answered with a definitive
result event, so the Order Service saga can complete its delete/cancel/update
workflows. Task handling is idempotent by ``task_id``: the recorded outcome is
republished instead of re-applying a duplicate task.

Concurrency (N1.2.2): account/reservation rows are locked with SELECT ...
FOR UPDATE for the duration of each operation, and every operation commits
atomically (N1.2.1).
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import (
    ConflictError,
    ForbiddenError,
    InsufficientCreditsError,
    NotFoundError,
    ServiceError,
)
from app.models._util import _utcnow
from app.models.account import CreditAccount
from app.models.reservation import CreditReservation, ReservationStatus
from app.models.task_result import CreditTaskResult, TaskResultKind, TaskResultOutcome
from app.models.transaction import CreditTransaction, TransactionKind
from app.observability import metrics
from app.repositories.account_repo import AccountRepository
from app.repositories.reservation_repo import ReservationRepository
from app.repositories.task_result_repo import TaskResultRepository
from app.repositories.transaction_repo import TransactionRepository
from app.schemas.interop import (
    CreditAmendResult,
    CreditReleaseResult,
    OrderActionEvent,
    OrderUpdateRequestedEvent,
)
from app.services import publisher
from foc_shared.auth import Role
from foc_shared.events import (
    CreditEventType,
    OrderEvent,
    OrderEventType,
    ReservationEvent,
    UserRegisteredEvent,
)

logger = logging.getLogger(__name__)


class CreditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._accounts = AccountRepository(session)
        self._reservations = ReservationRepository(session)
        self._task_results = TaskResultRepository(session)
        self._transactions = TransactionRepository(session)

    # ── F1: accounts ──────────────────────────────────────────────────────────

    async def ensure_account(self, user_id: str) -> CreditAccount:
        """Create the account on registration with the initial allocation
        (F1.1, F1.1.1). Idempotent: a redelivered UserRegistered event or an
        existing account leaves balances untouched."""
        existing = await self._accounts.get(user_id)
        if existing is not None:
            return existing
        account = CreditAccount(
            user_id=user_id,
            available_balance=settings.initial_credit_allocation,
            reserved_balance=0,
        )
        try:
            await self._accounts.add(account)
            await self._transactions.add(
                CreditTransaction(
                    user_id=user_id,
                    kind=TransactionKind.ALLOCATION.value,
                    amount=settings.initial_credit_allocation,
                )
            )
            await self._session.commit()
        except IntegrityError:
            # Concurrent UserRegistered delivery: another worker created the
            # account first. Roll back our insert and return the winner.
            await self._session.rollback()
            existing = await self._accounts.get(user_id)
            if existing is not None:
                return existing
            raise
        logger.info(
            "Provisioned credit account for user_id=%s with %d credits",
            user_id,
            settings.initial_credit_allocation,
        )
        return account

    async def get_balances(self, user_id: str) -> CreditAccount:
        account = await self._accounts.get(user_id)
        if account is None:
            raise NotFoundError(f"No credit account exists for user '{user_id}'.")
        return account

    async def balance_totals(self) -> dict[str, int]:
        """Aggregate balances across all accounts (observability summary)."""
        return await self._accounts.totals()

    # ── F2: reservations ─────────────────────────────────────────────────────

    async def reserve(self, *, user_id: str, order_id: str, amount: int) -> CreditReservation:
        """Reserve credits for an order (F2.1). Moves the amount from
        available to reserved only after sufficiency is verified (F2.1.6);
        publishes accepted/rejected reservation events (F2.1.4/F2.1.5)."""
        account = await self._accounts.get_for_update(user_id)
        if account is None:
            raise NotFoundError(f"No credit account exists for user '{user_id}'.")

        existing = await self._reservations.get_by_order_id(order_id)
        if existing is not None:
            # Idempotent retry: order-service may re-attempt a reserve call
            # after a timeout. An identical reservation succeeds as-is.
            if existing.user_id == user_id and existing.amount == amount:
                metrics.record_duplicate_suppressed("reservation")
                return existing
            metrics.record_reservation("conflict")
            raise ConflictError(f"Credits for order '{order_id}' are already reserved.")

        if amount > account.available_balance:
            available = account.available_balance
            metrics.record_reservation("rejected_insufficient_credits")
            # Release the row lock before doing network I/O.
            await self._session.rollback()
            await publisher.publish_reservation_event(
                ReservationEvent(
                    event_type=CreditEventType.CREDIT_RESERVATION_REJECTED,
                    reservation_id=None,
                    user_id=user_id,
                    order_id=order_id,
                    amount=amount,
                    timestamp=_utcnow(),
                    reason="insufficient available credits",
                )
            )
            raise InsufficientCreditsError(
                f"User '{user_id}' has only {available} available "
                f"credit(s); cannot reserve {amount}."
            )

        account.available_balance -= amount
        account.reserved_balance += amount
        reservation = CreditReservation(
            user_id=user_id,
            order_id=order_id,
            amount=amount,
            status=ReservationStatus.RESERVED.value,
        )
        try:
            await self._reservations.add(reservation)
            await self._transactions.add(
                CreditTransaction(
                    user_id=user_id,
                    kind=TransactionKind.RESERVATION.value,
                    amount=-amount,
                    reservation_id=reservation.id,
                    order_id=order_id,
                )
            )
            await self._session.commit()
        except IntegrityError:
            # N1.2.2: the unique order_id constraint caught a concurrent
            # duplicate reservation. An identical retry is a success.
            await self._session.rollback()
            existing = await self._reservations.get_by_order_id(order_id)
            if existing is not None and existing.user_id == user_id and existing.amount == amount:
                metrics.record_duplicate_suppressed("reservation")
                metrics.record_reservation("accepted")
                return existing
            metrics.record_reservation("conflict")
            raise ConflictError(f"Credits for order '{order_id}' are already reserved.") from None
        await self._session.refresh(reservation)
        metrics.record_reservation("accepted")
        await publisher.publish_reservation_event(
            ReservationEvent(
                event_type=CreditEventType.CREDIT_RESERVATION_ACCEPTED,
                reservation_id=reservation.id,
                user_id=user_id,
                order_id=order_id,
                amount=amount,
                timestamp=_utcnow(),
            )
        )
        return reservation

    async def amend(
        self,
        reservation_id: str,
        new_amount: int,
        *,
        caller_user_id: str,
        caller_role: str,
    ) -> CreditReservation:
        """Amend an existing reservation when the order's reward changes (F2.3).

        Increase re-validates available credits (F2.3.1); decrease returns the
        difference to available (F2.3.2)."""
        reservation = await self._reservation_for_caller(
            reservation_id, caller_user_id, caller_role
        )
        return await self._amend_reservation(reservation, new_amount)

    async def _amend_reservation(
        self, reservation: CreditReservation, new_amount: int, *, commit: bool = True
    ) -> CreditReservation:
        """Amend the reservation; ``commit=False`` leaves the transaction open so
        the caller can record the task outcome in the same transaction."""
        if reservation.status != ReservationStatus.RESERVED.value:
            metrics.record_amendment("conflict")
            raise ConflictError(
                f"Reservation '{reservation.id}' is {reservation.status} and cannot be amended."
            )

        account = await self._accounts.get_for_update(reservation.user_id)
        delta = new_amount - reservation.amount
        if delta > account.available_balance:
            metrics.record_amendment("rejected_insufficient_credits")
            raise InsufficientCreditsError(
                f"User '{reservation.user_id}' has only {account.available_balance} available "
                f"credit(s); cannot increase the reservation by {delta}."
            )

        reservation.amount = new_amount
        account.available_balance -= delta
        account.reserved_balance += delta
        if delta != 0:
            await self._transactions.add(
                CreditTransaction(
                    user_id=reservation.user_id,
                    kind=TransactionKind.AMENDMENT.value,
                    amount=-delta,
                    reservation_id=reservation.id,
                    order_id=reservation.order_id,
                )
            )
        if commit:
            await self._session.commit()
            await self._session.refresh(reservation)
        metrics.record_amendment("unchanged" if delta == 0 else "amended")
        return reservation

    # ── F3: transfers ────────────────────────────────────────────────────────

    async def transfer(
        self,
        reservation_id: str,
        courier_id: str,
        *,
        caller_user_id: str,
        caller_role: str,
    ) -> CreditReservation:
        reservation = await self._reservation_for_caller(
            reservation_id, caller_user_id, caller_role
        )
        return await self._transfer_reservation(reservation, courier_id)

    async def transfer_for_order(self, order_id: str, courier_id: str) -> CreditReservation:
        """Event-driven transfer on OrderCompleted (F3.2)."""
        reservation = await self._reservations.get_by_order_id_for_update(order_id)
        if reservation is None:
            raise NotFoundError(f"No reservation exists for order '{order_id}'.")
        return await self._transfer_reservation(reservation, courier_id)

    async def _transfer_reservation(
        self, reservation: CreditReservation, courier_id: str
    ) -> CreditReservation:
        # Idempotent (F3.2.1): a repeated order-completion leaves the already
        # transferred reservation and all balances untouched.
        if reservation.status == ReservationStatus.TRANSFERRED.value:
            metrics.record_duplicate_suppressed("transfer")
            metrics.record_transfer("already_transferred")
            return reservation
        if reservation.status != ReservationStatus.RESERVED.value:
            metrics.record_transfer("conflict")
            raise ConflictError(
                f"Reservation '{reservation.id}' is {reservation.status} and cannot be transferred."
            )

        # Lock both accounts in a deterministic (sorted) order so concurrent
        # transfers between the same pair cannot deadlock each other. The
        # requester row always exists (FK to credit_accounts).
        locked: dict[str, CreditAccount | None] = {}
        for user_id in sorted({reservation.user_id, courier_id}):
            locked[user_id] = await self._accounts.get_for_update(user_id)

        courier = locked.get(courier_id)
        if courier is None:
            metrics.record_transfer("rejected_no_courier_account")
            raise NotFoundError(f"No credit account exists for courier '{courier_id}'.")
        requester = locked[reservation.user_id]

        requester.reserved_balance -= reservation.amount
        courier.available_balance += reservation.amount
        reservation.status = ReservationStatus.TRANSFERRED.value
        await self._transactions.add(
            CreditTransaction(
                user_id=reservation.user_id,
                counterparty_user_id=courier_id,
                kind=TransactionKind.TRANSFER.value,
                # The outflow was already recorded at reservation time; keeping
                # this entry at 0 makes history sum to the balance (F5.2).
                amount=0,
                reservation_id=reservation.id,
                order_id=reservation.order_id,
            )
        )
        await self._transactions.add(
            CreditTransaction(
                user_id=courier_id,
                counterparty_user_id=reservation.user_id,
                kind=TransactionKind.TRANSFER.value,
                amount=reservation.amount,
                reservation_id=reservation.id,
                order_id=reservation.order_id,
            )
        )
        await self._session.commit()
        await self._session.refresh(reservation)
        metrics.record_transfer("ok")
        return reservation

    # ── F4: releases ─────────────────────────────────────────────────────────

    async def release(
        self,
        reservation_id: str,
        *,
        caller_user_id: str,
        caller_role: str,
    ) -> CreditReservation:
        reservation = await self._reservation_for_caller(
            reservation_id, caller_user_id, caller_role
        )
        return await self._release_reservation(reservation)

    async def release_for_order(self, order_id: str) -> CreditReservation | None:
        """Event-driven release on OrderCancelled/OrderExpired (F4.1.1, F4.2.1).

        Idempotent: a missing or already-released reservation is a no-op, so a
        redelivered event never errors."""
        reservation = await self._reservations.get_by_order_id_for_update(order_id)
        if reservation is None:
            logger.info("No reservation exists for order '%s'; nothing to release.", order_id)
            return None
        return await self._release_reservation(reservation)

    async def _release_reservation(
        self, reservation: CreditReservation, *, commit: bool = True
    ) -> CreditReservation:
        """Release the reservation; ``commit=False`` leaves the transaction open
        so the caller can record the task outcome in the same transaction."""
        if reservation.status == ReservationStatus.RELEASED.value:
            metrics.record_duplicate_suppressed("release")
            metrics.record_release("already_released")
            return reservation  # idempotent
        if reservation.status == ReservationStatus.TRANSFERRED.value:
            metrics.record_release("conflict")
            raise ConflictError(
                f"Reservation '{reservation.id}' is already transferred and cannot be released."
            )

        # reservation.user_id is a FK to credit_accounts, so the account row
        # always exists (no account deletion exists in the system).
        account = await self._accounts.get_for_update(reservation.user_id)
        account.reserved_balance -= reservation.amount
        account.available_balance += reservation.amount
        reservation.status = ReservationStatus.RELEASED.value
        await self._transactions.add(
            CreditTransaction(
                user_id=reservation.user_id,
                kind=TransactionKind.RELEASE.value,
                amount=reservation.amount,
                reservation_id=reservation.id,
                order_id=reservation.order_id,
            )
        )
        if commit:
            await self._session.commit()
            await self._session.refresh(reservation)
        metrics.record_release("ok")
        return reservation

    # ── Event handling ───────────────────────────────────────────────────────

    async def handle_order_event(self, event: OrderEvent) -> None:
        """Handle the legacy order lifecycle events (no reply expected)."""
        if event.event_type == OrderEventType.ORDER_COMPLETED:
            if event.courier_id is None:
                logger.error(
                    "OrderCompleted for order '%s' carries no courier_id; credits stay reserved.",
                    event.order_id,
                )
                return
            await self.transfer_for_order(event.order_id, event.courier_id)
        elif event.event_type == OrderEventType.ORDER_EXPIRED:
            await self.release_for_order(event.order_id)
        elif event.event_type == OrderEventType.COURIER_WITHDRAWN:
            # Credit F4.1.2: withdrawal keeps the credits reserved.
            logger.info(
                "CourierWithdrawn for order '%s': reservation stays reserved (F4.1.2).",
                event.order_id,
            )

    async def handle_release_requested(self, event: OrderActionEvent) -> None:
        """Release the reservation for a delete/cancel request and answer the
        Order Service task (Credit F4.1.1).

        Idempotent by ``task_id``: a repeated delivery republishes the stored
        outcome instead of releasing a second time. Every definitive outcome
        (released or failed) is recorded and published, so the Order Service
        saga always receives exactly one answer per ``task_id``."""
        recorded = await self._task_results.get(event.task_id)
        if recorded is not None:
            metrics.record_duplicate_suppressed("release_task")
            await self._publish_release_outcome(recorded)
            return

        reservation = await self._reservations.get_for_update(event.reservation_id)
        reason = self._request_mismatch(
            reservation, order_id=event.order_id, requester_id=event.requester_id
        )
        if reason is None and reservation.status == ReservationStatus.TRANSFERRED.value:
            reason = "Reservation has already been transferred and cannot be released."
        if reason is not None:
            await self._record_release_outcome(event, TaskResultOutcome.RELEASE_FAILED, reason)
            return

        try:
            await self._release_reservation(reservation, commit=False)
        except ServiceError as exc:
            await self._record_release_outcome(event, TaskResultOutcome.RELEASE_FAILED, str(exc))
            return
        await self._record_release_outcome(event, TaskResultOutcome.RELEASED)

    async def handle_update_requested(self, event: OrderUpdateRequestedEvent) -> None:
        """Amend the reservation to the reward carried by the order update
        (Credit F2.3) and answer the Order Service task.

        Idempotent by ``task_id``; definitive outcomes become
        ``CreditAmended`` or ``CreditAmendRejected``."""
        recorded = await self._task_results.get(event.task_id)
        if recorded is not None:
            metrics.record_duplicate_suppressed("amend_task")
            await self._publish_amend_outcome(recorded)
            return

        reservation = await self._reservations.get_for_update(event.reservation_id)
        reason = self._request_mismatch(
            reservation, order_id=event.order_id, requester_id=event.requester_id
        )
        if reason is None and reservation.status != ReservationStatus.RESERVED.value:
            reason = f"Reservation is {reservation.status} and cannot be amended."
        if reason is None and event.reward < 0:
            reason = "Reward cannot be negative."
        if reason is not None:
            await self._record_amend_outcome(event, TaskResultOutcome.AMEND_REJECTED, reason)
            return

        try:
            await self._amend_reservation(reservation, event.reward, commit=False)
        except ServiceError as exc:
            await self._record_amend_outcome(event, TaskResultOutcome.AMEND_REJECTED, str(exc))
            return
        await self._record_amend_outcome(event, TaskResultOutcome.AMENDED)

    async def handle_user_registered_event(self, event: UserRegisteredEvent) -> None:
        await self.ensure_account(event.user_id)

    async def report_release_retries_exhausted(
        self, event: OrderActionEvent, error: Exception
    ) -> None:
        """Answer a release task we could not finish within the retry budget.

        If the release already committed and only the reply kept failing, the
        recorded outcome is republished: Order must never be told "failed" for
        work that succeeded."""
        recorded = await self._task_results.get(event.task_id)
        if recorded is not None:
            await self._publish_release_outcome(recorded)
            return
        metrics.record_saga_retries_exhausted("release")
        await publisher.publish_credit_event(
            CreditReleaseResult(
                event_type="CreditReleaseFailed",
                task_id=event.task_id,
                order_id=event.order_id,
                reservation_id=event.reservation_id,
                timestamp=_utcnow(),
                reason=self._retry_limit_reason(error),
            )
        )

    async def report_amend_retries_exhausted(
        self, event: OrderUpdateRequestedEvent, error: Exception
    ) -> None:
        """Amend counterpart of :meth:`report_release_retries_exhausted`."""
        recorded = await self._task_results.get(event.task_id)
        if recorded is not None:
            metrics.record_duplicate_suppressed("amend_task")
            await self._publish_amend_outcome(recorded)
            return
        metrics.record_saga_retries_exhausted("amend")
        await publisher.publish_credit_event(
            CreditAmendResult(
                event_type="CreditAmendRejected",
                task_id=event.task_id,
                order_id=event.order_id,
                reservation_id=event.reservation_id,
                requester_id=event.requester_id,
                amount=event.reward,
                reason=self._retry_limit_reason(error),
            )
        )

    @staticmethod
    def _retry_limit_reason(error: Exception) -> str:
        return f"Retry limit exceeded: {error}"[:500]

    @staticmethod
    def _request_mismatch(
        reservation: CreditReservation | None, *, order_id: str, requester_id: str
    ) -> str | None:
        """Return a rejection reason when a task targets the wrong reservation."""
        if reservation is None:
            return "Reservation was not found."
        if reservation.order_id != order_id:
            return "Reservation does not belong to this order."
        if reservation.user_id != requester_id:
            return "Reservation does not belong to this requester."
        return None

    async def _record_release_outcome(
        self,
        event: OrderActionEvent,
        outcome: TaskResultOutcome,
        reason: str | None = None,
    ) -> None:
        result = await self._save_task_result(
            CreditTaskResult(
                task_id=event.task_id,
                kind=TaskResultKind.RELEASE.value,
                reservation_id=event.reservation_id,
                order_id=event.order_id,
                requester_id=event.requester_id,
                outcome=outcome.value,
                reason=reason,
            )
        )
        metrics.record_saga_task("release", outcome.value)
        await self._publish_release_outcome(result)

    async def _record_amend_outcome(
        self,
        event: OrderUpdateRequestedEvent,
        outcome: TaskResultOutcome,
        reason: str | None = None,
    ) -> None:
        result = await self._save_task_result(
            CreditTaskResult(
                task_id=event.task_id,
                kind=TaskResultKind.AMEND.value,
                reservation_id=event.reservation_id,
                order_id=event.order_id,
                requester_id=event.requester_id,
                outcome=outcome.value,
                amount=event.reward,
                reason=reason,
            )
        )
        metrics.record_saga_task("amend", outcome.value)
        await self._publish_amend_outcome(result)

    async def _save_task_result(self, result: CreditTaskResult) -> CreditTaskResult:
        """Persist the outcome and commit it together with whatever state change
        the caller already staged (release or amendment), so the operation can
        never be committed without its outcome. A concurrent duplicate keeps the
        first recorded outcome."""
        try:
            await self._task_results.add(result)
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self._task_results.get(result.task_id)
            if existing is None:
                raise
            metrics.record_duplicate_suppressed("task_result")
            return existing
        return result

    @staticmethod
    async def _publish_release_outcome(result: CreditTaskResult) -> None:
        released = result.outcome == TaskResultOutcome.RELEASED.value
        await publisher.publish_credit_event(
            CreditReleaseResult(
                event_type="CreditReleased" if released else "CreditReleaseFailed",
                task_id=result.task_id,
                order_id=result.order_id,
                reservation_id=result.reservation_id,
                timestamp=_utcnow(),
                reason=None if released else result.reason,
            )
        )

    @staticmethod
    async def _publish_amend_outcome(result: CreditTaskResult) -> None:
        amended = result.outcome == TaskResultOutcome.AMENDED.value
        await publisher.publish_credit_event(
            CreditAmendResult(
                event_type="CreditAmended" if amended else "CreditAmendRejected",
                task_id=result.task_id,
                order_id=result.order_id,
                reservation_id=result.reservation_id,
                requester_id=result.requester_id,
                amount=result.amount if result.amount is not None else 0,
                reason=None if amended else result.reason,
            )
        )

    # ── F5: transaction history ──────────────────────────────────────────────

    async def list_transactions(
        self, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[CreditTransaction]:
        return await self._transactions.list(user_id, limit=limit, offset=offset)

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _reservation_for_caller(
        self, reservation_id: str, caller_user_id: str, caller_role: str
    ) -> CreditReservation:
        """Fetch with a row lock and verify the caller owns it (or is admin)."""
        reservation = await self._reservations.get_for_update(reservation_id)
        if reservation is None:
            raise NotFoundError(f"Reservation '{reservation_id}' was not found.")
        self._require_owner_or_admin(caller_user_id, caller_role, reservation.user_id)
        return reservation

    @staticmethod
    def _require_owner_or_admin(caller_user_id: str, caller_role: str, owner_id: str) -> None:
        if caller_user_id == owner_id or caller_role == Role.ADMIN.value:
            return
        raise ForbiddenError("You may only manage your own credit reservations.")

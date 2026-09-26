# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Core credit-economy business logic (Credit Service D1 backlog).

Implements:
- F1  account provisioning + balance tracking/queries
- F2  reservation (+ validation, events, state) and amendment
- F3  transfer on order completion, idempotent
- F4  release on cancellation/expiry; never on courier withdrawal
- F5  transaction-history recording + retrieval

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
)
from app.models._util import _utcnow
from app.models.account import CreditAccount
from app.models.reservation import CreditReservation, ReservationStatus
from app.models.transaction import CreditTransaction, TransactionKind
from app.repositories.account_repo import AccountRepository
from app.repositories.reservation_repo import ReservationRepository
from app.repositories.transaction_repo import TransactionRepository
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
                return existing
            raise ConflictError(f"Credits for order '{order_id}' are already reserved.")

        if amount > account.available_balance:
            available = account.available_balance
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
                return existing
            raise ConflictError(f"Credits for order '{order_id}' are already reserved.") from None
        await self._session.refresh(reservation)
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
        if reservation.status != ReservationStatus.RESERVED.value:
            raise ConflictError(
                f"Reservation '{reservation_id}' is {reservation.status} and cannot be amended."
            )

        account = await self._accounts.get_for_update(reservation.user_id)
        delta = new_amount - reservation.amount
        if delta > account.available_balance:
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
        await self._session.commit()
        await self._session.refresh(reservation)
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
            return reservation
        if reservation.status != ReservationStatus.RESERVED.value:
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

    async def _release_reservation(self, reservation: CreditReservation) -> CreditReservation:
        if reservation.status == ReservationStatus.RELEASED.value:
            return reservation  # idempotent
        if reservation.status == ReservationStatus.TRANSFERRED.value:
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
        await self._session.commit()
        await self._session.refresh(reservation)
        return reservation

    # ── Event handling ───────────────────────────────────────────────────────

    async def handle_order_event(self, event: OrderEvent) -> None:
        """Dispatch only the event types this service subscribes to (the
        consumer binds exactly these four routing keys)."""
        if event.event_type == OrderEventType.ORDER_COMPLETED:
            if event.courier_id is None:
                logger.error(
                    "OrderCompleted for order '%s' carries no courier_id; credits stay reserved.",
                    event.order_id,
                )
                return
            await self.transfer_for_order(event.order_id, event.courier_id)
        elif event.event_type in (OrderEventType.ORDER_CANCELLED, OrderEventType.ORDER_EXPIRED):
            await self.release_for_order(event.order_id)
        elif event.event_type == OrderEventType.COURIER_WITHDRAWN:
            # Credit F4.1.2: withdrawal keeps the credits reserved.
            logger.info(
                "CourierWithdrawn for order '%s': reservation stays reserved (F4.1.2).",
                event.order_id,
            )

    async def handle_user_registered_event(self, event: UserRegisteredEvent) -> None:
        await self.ensure_account(event.user_id)

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

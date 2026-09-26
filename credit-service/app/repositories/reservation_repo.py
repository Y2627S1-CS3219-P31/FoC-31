# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reservation import CreditReservation


class ReservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, reservation: CreditReservation) -> CreditReservation:
        self._session.add(reservation)
        await self._session.flush()
        return reservation

    async def get(self, reservation_id: str) -> CreditReservation | None:
        return await self._session.get(CreditReservation, reservation_id)

    async def get_for_update(self, reservation_id: str) -> CreditReservation | None:
        result = await self._session.execute(
            select(CreditReservation)
            .where(CreditReservation.id == reservation_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: str) -> CreditReservation | None:
        result = await self._session.execute(
            select(CreditReservation).where(CreditReservation.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_order_id_for_update(self, order_id: str) -> CreditReservation | None:
        result = await self._session.execute(
            select(CreditReservation)
            .where(CreditReservation.order_id == order_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

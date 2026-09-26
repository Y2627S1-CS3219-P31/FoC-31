from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.otp import OtpCode, OtpPurpose


class OtpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, otp: OtpCode) -> OtpCode:
        self._session.add(otp)
        await self._session.flush()
        return otp

    async def get_latest_unconsumed(self, user_id: str, purpose: OtpPurpose) -> OtpCode | None:
        result = await self._session.execute(
            select(OtpCode)
            .where(
                OtpCode.user_id == user_id,
                OtpCode.purpose == purpose.value,
                OtpCode.consumed_at.is_(None),
            )
            .order_by(OtpCode.created_at.desc())
        )
        return result.scalars().first()

    async def mark_consumed(self, otp_id: str) -> bool:
        result = await self._session.execute(
            update(OtpCode)
            .where(OtpCode.id == otp_id, OtpCode.consumed_at.is_(None))
            .values(consumed_at=datetime.now(UTC).replace(tzinfo=None))
        )
        return result.rowcount > 0
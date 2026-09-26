from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.otp import OtpCode, OtpPurpose
from app.models.user import User
from app.repositories.otp import OtpRepository
from app.repositories.user import UserRepository
from app.services import events, notification, otp, security
from app.services.exceptions import (
    AccountEmailAlreadyVerifiedError,
    AccountNotFoundError,
    AccountNotVerifiedError,
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidOtpError,
)
from foc_shared.auth import Role


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._otps = OtpRepository(session)

    async def register(
        self, *, email: str, password: str, display_name: str, contact_number: str | None = None
    ) -> User:
        existing = await self._users.get_by_email(email)
        if existing is not None:
            if existing.email_verified:
                raise EmailAlreadyRegisteredError(email)
            # Registered but never verified
            existing.password_hash = security.hash_password(password)
            existing.display_name = display_name
            existing.contact_number = contact_number
            user = existing
        else:
            user = User(
                email=email,
                password_hash=security.hash_password(password),
                display_name=display_name,
                contact_number=contact_number,
                role=Role.CLIENT.value,
                email_verified=False,
                is_suspended=False,
            )
            await self._users.add(user)

        await self._issue_and_send_otp(user, purpose=OtpPurpose.EMAIL_VERIFICATION)
        return user

    async def resend_otp(self, *, email: str) -> User:
        user = await self._users.get_by_email(email)
        if user is None:
            raise AccountNotFoundError(email)
        if user.email_verified:
            raise AccountEmailAlreadyVerifiedError(email)

        await self._issue_and_send_otp(user, purpose=OtpPurpose.EMAIL_VERIFICATION)
        return user

    async def _issue_and_send_otp(self, user: User, *, purpose: OtpPurpose) -> None:
        code = otp.generate_code()
        await self._otps.add(
            OtpCode(
                user_id=user.id,
                purpose=purpose.value,
                code_hash=otp.hash_code(code),
                expires_at=otp.expiry_from_now(),
            )
        )
        await self._session.commit()
        notification.send_otp_email(user.email, code)

    async def verify_email(self, *, email: str, code: str) -> User:
        user = await self._users.get_by_email(email)
        if user is None:
            raise InvalidOtpError("no account with that email")
        if user.email_verified:
            return user

        otp_row = await self._otps.get_latest_unconsumed(user.id, OtpPurpose.EMAIL_VERIFICATION)
        if otp_row is None:
            raise InvalidOtpError("no active code — request a new one")
        if otp_row.expires_at < datetime.now(UTC).replace(tzinfo=None):
            raise InvalidOtpError("code expired — request a new one")
        if otp_row.code_hash != otp.hash_code(code):
            raise InvalidOtpError("incorrect code")

        # Atomic claim — closes the race where two concurrent requests both
        # read consumed_at=NULL before either one writes. See OtpRepository.
        consumed = await self._otps.mark_consumed(otp_row.id)
        if not consumed:
            raise InvalidOtpError("code already used")

        user.email_verified = True
        await self._session.commit()

        await events.publish_user_registered(user_id=user.id, email=user.email)
        return user

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self._users.get_by_email(email)
        if user is None or not security.verify_password(password, user.password_hash):
            raise InvalidCredentialsError()
        if user.is_suspended:
            raise AccountSuspendedError()
        if not user.email_verified:
            raise AccountNotVerifiedError()
        return user

    async def get_profile(self, user_id: str) -> User | None:
        return await self._users.get_by_id(user_id)

    async def update_profile(
        self, user_id: str, *, display_name: str | None, contact_number: str | None
    ) -> User | None:
        user = await self._users.get_by_id(user_id)
        if user is None:
            return None
        if display_name is not None:
            user.display_name = display_name
        if contact_number is not None:
            user.contact_number = contact_number
        await self._session.commit()
        return user
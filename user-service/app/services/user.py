from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.otp import OtpCode, OtpPurpose
from app.models.user import User
from app.repositories.otp import OtpRepository
from app.repositories.user import UserRepository
from app.services import events, notification, otp, security
from app.services.exceptions import (
    AccountNotVerifiedError,
    AccountSuspendedError,
    CannotModifyAdminError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidOtpError,
    NotificationDeliveryError,
    OtpRateLimitError,
    UserNotFoundError,
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
            latest = await self._otps.get_latest_unconsumed(
                existing.id, OtpPurpose.EMAIL_VERIFICATION
            )
            if latest is not None:
                age = datetime.now(UTC).replace(tzinfo=None) - latest.created_at
                if age.total_seconds() < settings.otp_resend_cooldown_seconds:
                    raise OtpRateLimitError()
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
            try:
                await self._users.add(user)
            except IntegrityError as exc:
                await self._session.rollback()
                raise EmailAlreadyRegisteredError(email) from exc

        await self._issue_and_send_otp(user, purpose=OtpPurpose.EMAIL_VERIFICATION)
        return user

    async def resend_otp(self, *, email: str) -> User | None:
        user = await self._users.get_by_email(email)
        # Always return the same public response for unknown and already
        # verified accounts so this endpoint cannot enumerate user emails.
        if user is None or user.email_verified:
            return None

        latest = await self._otps.get_latest_unconsumed(user.id, OtpPurpose.EMAIL_VERIFICATION)
        if latest is not None:
            age = datetime.now(UTC).replace(tzinfo=None) - latest.created_at
            if age.total_seconds() < settings.otp_resend_cooldown_seconds:
                raise OtpRateLimitError()

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
        try:
            await asyncio.to_thread(notification.send_otp_email, user.email, code)
        except NotificationDeliveryError:
            raise
        except Exception as exc:
            raise NotificationDeliveryError("OTP email delivery failed") from exc

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
        if otp_row.attempts >= settings.otp_max_attempts:
            raise InvalidOtpError("too many attempts — request a new code")
        if otp_row.code_hash != otp.hash_code(code):
            attempts = await self._otps.increment_attempts(
                otp_row.id, max_attempts=settings.otp_max_attempts
            )
            await self._session.commit()
            if attempts >= settings.otp_max_attempts:
                raise InvalidOtpError("too many attempts — request a new code")
            raise InvalidOtpError("incorrect code")

        consumed = await self._otps.mark_consumed(otp_row.id)
        if not consumed:
            raise InvalidOtpError("code already used")

        user.email_verified = True
        await events.enqueue_user_registered(
            self._session, user_id=user.id, email=user.email
        )
        await self._session.commit()
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

    async def create_admin(
        self, *, email: str, password: str, display_name: str, contact_number: str | None = None
    ) -> User:
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)

        admin = User(
            email=email,
            password_hash=security.hash_password(password),
            display_name=display_name,
            contact_number=contact_number,
            role=Role.ADMIN.value,
            email_verified=True,
            is_suspended=False,
        )
        try:
            await self._users.add(admin)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyRegisteredError(email) from exc
        return admin

    async def ensure_bootstrap_admin(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        contact_number: str | None = None,
    ) -> User:
        """Create the configured first admin exactly once.

        PostgreSQL advisory locking serializes multiple app instances during
        first-run setup. The unique email constraint remains the fallback for
        other databases and concurrent callers.
        """
        connection = await self._session.connection()
        if connection.dialect.name == "postgresql":
            await connection.execute(text("SELECT pg_advisory_xact_lock(73918421)"))

        existing = await self._users.get_by_email(email)
        if existing is not None:
            if existing.role != Role.ADMIN.value:
                raise RuntimeError("bootstrap email belongs to a non-admin account")
            return existing

        admin = User(
            email=email,
            password_hash=security.hash_password(password),
            display_name=display_name,
            contact_number=contact_number,
            role=Role.ADMIN.value,
            email_verified=True,
            is_suspended=False,
        )
        try:
            await self._users.add(admin)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            existing = await self._users.get_by_email(email)
            if existing is not None and existing.role == Role.ADMIN.value:
                return existing
            raise RuntimeError("concurrent bootstrap admin creation failed") from exc
        return admin

    async def list_users(self, *, limit: int = 50, offset: int = 0) -> tuple[list[User], int]:
        return await self._users.list_all(limit=limit, offset=offset), await self._users.count_all()

    async def set_suspended(self, *, user_id: str, suspended: bool, actor_id: str) -> User:
        if user_id == actor_id:
            raise CannotModifyAdminError("an administrator cannot suspend themselves")

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        if user.role == Role.ADMIN.value:
            raise CannotModifyAdminError("administrator accounts cannot be suspended here")

        user.is_suspended = suspended
        await self._session.commit()
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

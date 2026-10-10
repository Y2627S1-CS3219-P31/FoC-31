import logging

from app.config import settings
from app.db import SessionLocal
from app.schemas.user import CreateAdminRequest
from app.services.user import UserService

logger = logging.getLogger(__name__)


async def seed_bootstrap_admin() -> None:
    configured = [
        settings.bootstrap_admin_email,
        settings.bootstrap_admin_password,
    ]

    if not any(configured):
        return

    if not all(configured):
        raise RuntimeError(
            "BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD "
            "must be configured together"
        )

    payload = CreateAdminRequest(
        email=settings.bootstrap_admin_email,
        password=settings.bootstrap_admin_password,
        display_name=settings.bootstrap_admin_display_name,
        contact_number=settings.bootstrap_admin_contact_number,
    )

    async with SessionLocal() as session:
        admin = await UserService(session).ensure_bootstrap_admin(
            email=str(payload.email),
            password=payload.password,
            display_name=payload.display_name,
            contact_number=payload.contact_number,
        )

    logger.info("Bootstrap admin is ready: user_id=%s", admin.id)
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings
from app.services.exceptions import NotificationDeliveryError

logger = logging.getLogger(__name__)


def send_otp_email(email: str, code: str) -> None:
    """Deliver an OTP through the configured SMTP provider.

    OTP values are deliberately never written to logs in real deployments.
    Missing mail configuration fails explicitly so the API cannot report a
    code as sent when no delivery mechanism exists.

    Dev-only escape hatch: when ``OTP_DEV_MODE`` is enabled and no SMTP host
    is configured, the code is logged instead of emailed so the
    register -> verify flow can be exercised without a mail provider. This
    branch MUST NOT be enabled in any real deployment.
    """
    if not settings.smtp_host:
        if settings.otp_dev_mode:
            logger.warning(
                "OTP_DEV_MODE active: verification code for %s is %s "
                "(dev-only; never enable in production)",
                email,
                code,
            )
            return
        raise NotificationDeliveryError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = "FoC email verification code"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        f"Your FoC verification code is {code}. It expires in 5 minutes."
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise NotificationDeliveryError("OTP email delivery failed") from exc

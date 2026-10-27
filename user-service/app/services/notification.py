from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings
from app.services.exceptions import NotificationDeliveryError

logger = logging.getLogger(__name__)


def send_otp_email(email: str, code: str) -> None:
    """Deliver an email-verification OTP through the configured SMTP provider."""
    _deliver(
        email=email,
        code=code,
        kind="verification",
        subject="FoC email verification code",
        body=f"Your FoC verification code is {code}. It expires in 5 minutes.",
    )


def send_password_reset_email(email: str, code: str) -> None:
    """Deliver a password-reset OTP through the configured SMTP provider."""
    _deliver(
        email=email,
        code=code,
        kind="password reset",
        subject="FoC password reset code",
        body=(
            f"Your FoC password reset code is {code}. It expires in 5 minutes.\n\n"
            "If you did not ask to reset your password, you can ignore this email; "
            "your password has not been changed."
        ),
    )


def _deliver(*, email: str, code: str, kind: str, subject: str, body: str) -> None:
    """Send one OTP email.

    OTP values are deliberately never written to logs in real deployments.
    Missing mail configuration fails explicitly so the API cannot report a
    code as sent when no delivery mechanism exists.

    Dev-only escape hatch: when ``OTP_DEV_MODE`` is enabled and no SMTP host
    is configured, the code is logged instead of emailed so OTP flows can be
    exercised without a mail provider. This branch MUST NOT be enabled in any
    real deployment.
    """
    if not settings.smtp_host:
        if settings.otp_dev_mode:
            logger.warning(
                "OTP_DEV_MODE active: %s code for %s is %s "
                "(dev-only; never enable in production)",
                kind,
                email,
                code,
            )
            return
        raise NotificationDeliveryError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise NotificationDeliveryError("OTP email delivery failed") from exc

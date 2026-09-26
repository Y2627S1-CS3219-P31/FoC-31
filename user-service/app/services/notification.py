from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import settings
from app.services.exceptions import NotificationDeliveryError


def send_otp_email(email: str, code: str) -> None:
    """Deliver an OTP through the configured SMTP provider.

    OTP values are deliberately never written to logs. Missing mail
    configuration fails explicitly so the API cannot report a code as sent
    when no delivery mechanism exists.
    """
    if not settings.smtp_host:
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

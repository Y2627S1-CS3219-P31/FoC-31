from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def send_otp_email(email: str, code: str) -> None:
    """Deliver the OTP code to the user.

    TODO(team): wire this to a real mailer, or to notification-service once
    it exposes an inbound API/queue for it. For now this just logs the code
    so the register -> verify -> login flow can be built and tested locally
    without an email provider. Do not ship this to anything real users touch.
    """
    logger.info("OTP for %s: %s (dev-only log, not a real email send)", email, code)
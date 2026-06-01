from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def send_email(*, to_email: str | None, subject: str, body: str) -> tuple[bool, str | None]:
        recipient = str(to_email or "").strip()
        if not recipient:
            return False, "Employee email address is not available."
        if not settings.smtp_host or not settings.smtp_from_email:
            return False, "Email server is not configured."

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
        message["To"] = recipient
        message.set_content(body)

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password or "")
                smtp.send_message(message)
        except Exception as exc:  # pragma: no cover - depends on external SMTP availability
            logger.exception("Failed to send email to %s", recipient)
            return False, str(exc)

        return True, None

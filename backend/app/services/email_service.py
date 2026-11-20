"""Outbound email (password reset). Uses SMTP when configured.

Without SMTP in non-production environments the reset link is written to the server log so the flow
can be exercised locally. In production without SMTP nothing is sent and an error is logged.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("medicore.email")


def send_password_reset(to_email: str, link: str) -> bool:
    s = get_settings()
    if not s.smtp_host:
        if s.is_production:
            log.error("Password reset requested but SMTP is not configured")
            return False
        log.warning("SMTP not configured (dev mode). Password reset link for %s: %s", to_email, link)
        return True
    msg = EmailMessage()
    msg["Subject"] = "MediCore AI password reset"
    msg["From"] = s.smtp_from or s.smtp_user
    msg["To"] = to_email
    msg.set_content(f"Use this link within 15 minutes to reset your password:\n\n{link}\n\n"
                    "If you did not request this, you can ignore this email.")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        log.exception("Failed to send password reset email")
        return False

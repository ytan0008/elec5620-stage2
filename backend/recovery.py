"""One-use password recovery tokens and optional SMTP delivery."""
from email.message import EmailMessage
import hashlib
import secrets
import smtplib
from urllib.parse import quote

from backend.config import settings


def new_reset_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def reset_path(token: str) -> str:
    return f"/reset-password?token={quote(token, safe='')}"


def mail_ready() -> bool:
    config = settings()
    return bool(config.smtp_host and config.smtp_from_email and config.public_base_url)


def send_reset_email(recipient: str, token: str) -> None:
    config = settings()
    message = EmailMessage()
    message["Subject"] = "Reset your CertifyAI password"
    message["From"] = config.smtp_from_email
    message["To"] = recipient
    link = config.public_base_url.rstrip("/") + reset_path(token)
    message.set_content(
        "A password reset was requested for your CertifyAI account.\n\n"
        f"Open this link within 30 minutes: {link}\n\n"
        "If you did not request this, you can ignore this email."
    )
    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as smtp:
        if config.smtp_use_tls:
            smtp.starttls()
        if config.smtp_username:
            smtp.login(config.smtp_username, config.smtp_password)
        smtp.send_message(message)

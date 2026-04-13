"""Send password reset instructions via SMTP email."""

from __future__ import annotations

import os
from email.message import EmailMessage
from urllib.parse import quote


def reset_frontend_base() -> str:
    """Origin for links in emails (no trailing slash)."""
    b = (os.getenv("PASSWORD_RESET_FRONTEND_BASE") or "").strip()
    if b:
        return b.rstrip("/")
    b = (os.getenv("OAUTH_FRONTEND_REDIRECT_BASE") or os.getenv("OAUTH_REDIRECT_BASE") or "").strip()
    if b:
        return b.rstrip("/")
    return "http://127.0.0.1:8000"


def smtp_configured() -> bool:
    return bool(
        (os.getenv("SMTP_HOST") or "").strip()
        and (os.getenv("SMTP_USER") or "").strip()
        and (os.getenv("SMTP_PASSWORD") or "").strip()
        and (os.getenv("SMTP_FROM") or "").strip()
    )


def send_reset_email(to_email: str, raw_token: str) -> None:
    """Blocking SMTP send (TLS). Raises on failure."""
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int((os.getenv("SMTP_PORT") or "587").strip() or "587")
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    from_addr = (os.getenv("SMTP_FROM") or "").strip()
    base = reset_frontend_base()
    link = f"{base}/?recovery={quote(raw_token, safe='')}"

    msg = EmailMessage()
    msg["Subject"] = "Reset your IntelliDigest password"
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.set_content(
        f"Use this link to choose a new password (expires in about an hour):\n\n{link}\n\n"
        "If you did not request this, you can ignore this email.\n"
    )

    import smtplib

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)

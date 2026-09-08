"""Email notification helper — extracted from tushare-email-fetch.

Sends a plain-text summary with optional CSV attachments via SMTP.
Uses SMTP_STARTTLS by default.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def send_email(
    summary: str,
    attachments: list[Path] | None = None,
    *,
    to_addr: str | None = None,
    from_addr: str | None = None,
    smtp_server: str | None = None,
    smtp_port: int | None = None,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    use_starttls: bool = True,
    subject_prefix: str = "[tushare]",
) -> None:
    """Send an email with optional CSV attachments.

    All parameters can be passed explicitly or read from environment variables:
    - EMAIL_TO, EMAIL_FROM
    - SMTP_SERVER, SMTP_PORT (default: 587)
    - SMTP_USERNAME, SMTP_PASSWORD
    - SMTP_STARTTLS (default: true)
    - EMAIL_SUBJECT_PREFIX (default: [tushare])
    """
    to = to_addr or os.getenv("EMAIL_TO")
    server = smtp_server or os.getenv("SMTP_SERVER")

    if not to or not server:
        print("EMAIL_TO or SMTP_SERVER not provided; skipping email.")
        return

    from_ = (
        from_addr
        or os.getenv("EMAIL_FROM")
        or os.getenv("SMTP_USERNAME")
        or "tushare-bot@example.com"
    )
    port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
    user = smtp_user or os.getenv("SMTP_USERNAME")
    password = smtp_password or os.getenv("SMTP_PASSWORD")
    if os.getenv("SMTP_STARTTLS") is not None:
        use_starttls = os.getenv("SMTP_STARTTLS", "").lower() != "false"
    prefix = os.getenv("EMAIL_SUBJECT_PREFIX", subject_prefix)

    msg = EmailMessage()
    msg["Subject"] = f"{prefix} Daily Tushare fetch"
    msg["From"] = from_
    msg["To"] = to
    msg.set_content(summary)

    for path in attachments or []:
        data = path.read_bytes()
        msg.add_attachment(data, maintype="text", subtype="csv", filename=path.name)

    print(f"Sending email to {to} via {server}:{port}")
    with smtplib.SMTP(server, port, timeout=30) as smtp:
        if use_starttls:
            smtp.starttls()
        if user:
            if not password:
                raise SystemExit("SMTP_USERNAME provided but SMTP_PASSWORD missing.")
            smtp.login(user, password)
        smtp.send_message(msg)
    print("Email sent successfully.")

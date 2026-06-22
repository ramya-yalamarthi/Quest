"""
Engineer assignment notifications.

Best-effort, like every other side-channel in the orchestrator: a missing
mail config or a delivery failure must never break the case pipeline, so
failures are logged and swallowed, not raised.

Sends via Gmail SMTP (GMAIL_USER + GMAIL_APP_PASSWORD -- a free Gmail App
Password, no third-party signup) if configured, else falls back to SendGrid
(SENDGRID_API_KEY + SENDGRID_FROM) if that's configured instead.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


def _build_message(advisory: dict, case: dict) -> tuple[dict, str, str]:
    """Returns (engineer, subject, body); engineer is {} if nothing to send."""
    engineer = ((advisory or {}).get("routing") or {}).get("assigned_engineer")
    if not engineer or not engineer.get("email"):
        return {}, "", ""

    team = ((advisory or {}).get("routing") or {}).get("recommended_team", "")
    title = case.get("title", "(no title)")
    number = case.get("ticket_number") or case.get("id") or ""
    root_cause = ((advisory or {}).get("diagnosis") or {}).get("root_cause", "")

    subject = f"[Support-AI] Case assigned to you: {title}"
    body = (
        f"Hi {engineer.get('name')},\n\n"
        f"This ticket is assigned to you.\n\n"
        f"Case: {number}\n"
        f"Title: {title}\n"
        f"Team: {team}\n"
        f"Why you: {engineer.get('reason', '')}\n"
    )
    if root_cause:
        body += f"\nLikely root cause: {root_cause}\n"
    return engineer, subject, body


def _send_via_gmail(to_email: str, subject: str, body: str) -> bool:
    user = os.getenv("GMAIL_USER")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if not user or not app_password:
        return False
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_email
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(user, app_password)
            smtp.send_message(msg)
        return True
    except Exception:
        log.exception("Gmail SMTP send failed for %s", to_email)
        return False


def _send_via_sendgrid(to_email: str, subject: str, body: str) -> bool:
    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    sendgrid_from = os.getenv("SENDGRID_FROM")
    if not sendgrid_key or not sendgrid_from:
        return False
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        message = Mail(from_email=sendgrid_from, to_emails=to_email,
                       subject=subject, plain_text_content=body)
        SendGridAPIClient(sendgrid_key).send(message)
        return True
    except Exception:
        log.exception("SendGrid send failed for %s", to_email)
        return False


def notify_assigned_engineer(advisory: dict, case: dict) -> bool:
    """Email the engineer the routing agent assigned this case to. Tries
    Gmail SMTP first, then SendGrid. Returns True if a send succeeded."""
    engineer, subject, body = _build_message(advisory, case)
    if not engineer:
        return False

    if _send_via_gmail(engineer["email"], subject, body):
        return True
    if _send_via_sendgrid(engineer["email"], subject, body):
        return True

    log.warning("No mail config (GMAIL_USER/GMAIL_APP_PASSWORD or "
                "SENDGRID_API_KEY/SENDGRID_FROM); skipping assignment email to %s",
                engineer.get("email"))
    return False

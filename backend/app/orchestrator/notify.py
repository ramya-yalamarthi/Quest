"""
Engineer assignment notifications (SendGrid).

Best-effort, like every other side-channel in the orchestrator: a missing
SendGrid config or a delivery failure must never break the case pipeline, so
failures are logged and swallowed, not raised.
"""

from __future__ import annotations

import logging
import os

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

log = logging.getLogger(__name__)


def notify_assigned_engineer(advisory: dict, case: dict) -> bool:
    """Email the engineer the routing agent assigned this case to. Returns
    True if a send was attempted and accepted by SendGrid, else False."""
    engineer = ((advisory or {}).get("routing") or {}).get("assigned_engineer")
    if not engineer or not engineer.get("email"):
        return False

    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    sendgrid_from = os.getenv("SENDGRID_FROM")
    if not sendgrid_key or not sendgrid_from:
        log.warning("SendGrid not configured; skipping assignment email to %s", engineer.get("email"))
        return False

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

    try:
        message = Mail(
            from_email=sendgrid_from,
            to_emails=engineer["email"],
            subject=subject,
            plain_text_content=body,
        )
        sg = SendGridAPIClient(sendgrid_key)
        sg.send(message)
        return True
    except Exception:
        log.exception("Failed to send assignment email to %s", engineer.get("email"))
        return False

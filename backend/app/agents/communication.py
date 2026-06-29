from datetime import datetime, timezone
from uuid import UUID
from typing import Optional
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from sqlalchemy.orm import Session

from app.db.models.email import Email
from app.db.models.resolution import Resolution
from app.db.models.ticket import Ticket
from app.db.models.user import User

# A ticket still open with no customer-facing email sent within this many
# hours of its last activity is a communication gap worth flagging.
DEFAULT_COMMUNICATION_SLA_HOURS = 24.0


def flag_missing_updates(db: Session, sla_hours: float = DEFAULT_COMMUNICATION_SLA_HOURS) -> list[dict]:
    """Open (NEW/ASSIGNED) tickets with no APPROVED customer email sent
    within `sla_hours` of their last activity -- a communication gap the
    engineer/manager should close before the customer escalates."""
    now = datetime.now(timezone.utc)
    flagged = []
    for t in db.query(Ticket).filter(Ticket.status.in_(["NEW", "ASSIGNED"])).all():
        last_email = (
            db.query(Email)
            .filter(Email.ticket_id == t.ticket_id, Email.type == "APPROVED")
            .order_by(Email.created_at.desc())
            .first()
        )
        last_update_at = last_email.created_at if last_email else t.created_at
        gap_hours = (now - last_update_at).total_seconds() / 3600
        if gap_hours >= sla_hours:
            flagged.append({
                "ticket_id": str(t.ticket_id), "title": t.title, "status": t.status,
                "hours_since_last_update": round(gap_hours, 1),
                "last_update_at": last_update_at.isoformat(),
            })
    return flagged


def build_progress_template(ticket: Ticket, resolution: Optional[Resolution] = None,
                             engineer_name: Optional[str] = None) -> str:
    """Customer update body, tailored to where the ticket actually IS --
    not one generic template for every status."""
    title = ticket.title.strip()
    if ticket.status == "RESOLVED":
        body = f"Good news -- your ticket \"{title}\" has been resolved.\n\n"
        if resolution and resolution.resolution_text:
            body += f"What we did: {resolution.resolution_text}\n\n"
        body += "Please let us know if the issue returns."
        return body
    if ticket.status == "ASSIGNED":
        body = f"Update on your ticket \"{title}\": "
        body += f"it's now assigned to {engineer_name}." if engineer_name else "it's now assigned to an engineer."
        if resolution and resolution.root_cause:
            body += f"\n\nCurrent assessment: {resolution.root_cause}"
        body += "\n\nWe'll follow up with next steps shortly."
        return body
    return (f"We've received your ticket \"{title}\" and are triaging it now. "
            "We'll update you again once it's assigned to an engineer.")


def draft_progress_update(db: Session, ticket_id: UUID, engineer_id: Optional[UUID] = None) -> Email:
    """Draft a customer update grounded in the ticket's actual current
    progress (status + latest resolution), instead of a hand-written body."""
    ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise ValueError("ticket not found")
    resolution = (
        db.query(Resolution).filter(Resolution.ticket_id == ticket_id)
        .order_by(Resolution.created_at.desc()).first()
    )
    engineer_name = None
    if ticket.assigned_to:
        engineer = db.query(User).filter(User.user_id == ticket.assigned_to).first()
        engineer_name = engineer.display_name if engineer else None
    body = build_progress_template(ticket, resolution, engineer_name)
    return CommCoach(db).draft_email(ticket_id, body, engineer_id=engineer_id)


class CommCoach:
    """Agent that handles drafting, approving and sending emails and logging
    final resolutions into the database."""

    def __init__(self, db: Session):
        self.db = db

    def _make_subject(self, ticket: Ticket) -> str:
        title = ticket.title.strip()
        short_title = title if len(title) <= 60 else title[:57].rstrip() + "..."
        return f"[Support‑AI] Update on your issue: {short_title}"

    def draft_email(
        self,
        ticket_id: UUID,
        body: str,
        engineer_id: Optional[UUID] = None,
        subject: Optional[str] = None,
    ) -> Email:
        ticket = self.db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if not ticket:
            raise ValueError("ticket not found")

        email = Email(
            ticket_id=ticket_id,
            type="DRAFT",
            subject=subject or self._make_subject(ticket),
            body=body,
            created_by=engineer_id,
        )
        self.db.add(email)
        self.db.commit()
        self.db.refresh(email)
        return email

    def approve_email(self, email_id: UUID) -> Email:
        email = self.db.query(Email).filter(Email.email_id == email_id).first()
        if not email:
            raise ValueError("email not found")
        email.type = "APPROVED"
        self.db.commit()
        self.db.refresh(email)
        return email

    def update_draft_email(
        self,
        email_id: UUID,
        subject: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Email:
        email = self.db.query(Email).filter(Email.email_id == email_id).first()
        if not email:
            raise ValueError("email not found")
        if email.type != "DRAFT":
            return email
        if subject is not None:
            email.subject = subject
        if body is not None:
            email.body = body
        self.db.commit()
        self.db.refresh(email)
        return email

    def send_email(self, email: Email) -> None:
        """Send the email using SendGrid."""
        # Note: Email sending is currently disabled for testing
        # The email will be marked as approved but not actually sent
        
        ticket = self.db.query(Ticket).filter(Ticket.ticket_id == email.ticket_id).first()
        if not ticket:
            raise ValueError("ticket not found for email")

        recipient = None
        if ticket.created_by:
            user = self.db.query(User).filter(User.user_id == ticket.created_by).first()
            if user:
                recipient = user.email

        if not recipient:
            raise ValueError("recipient email not found")

        # Email sending disabled - uncomment below to enable SendGrid integration
        # sendgrid_key = os.environ.get("SENDGRID_API_KEY")
        # sendgrid_from = os.environ.get("SENDGRID_FROM")
        # if not sendgrid_key or not sendgrid_from:
        #     raise ValueError("SendGrid configuration is incomplete")
        #
        # message = Mail(
        #     from_email=sendgrid_from,
        #     to_emails=recipient,
        #     subject=email.subject,
        #     plain_text_content=email.body,
        # )
        # sg = SendGridAPIClient(sendgrid_key)
        # sg.send(message)
        
        # For now, just log that the email would be sent
        print(f"[Email Service] Email approved for ticket {ticket.ticket_id}")
        print(f"[Email Service] Recipient: {recipient}")
        print(f"[Email Service] Subject: {email.subject}")

    def log_resolution(
        self,
        ticket_id: UUID,
        resolution_text: str,
        root_cause: Optional[str] = None,
        outcome: Optional[str] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
        engineer_id: Optional[UUID] = None,
        recommendedsteps: Optional[list] = None,
    ) -> Resolution:
        res = Resolution(
            ticket_id=ticket_id,
            resolution_text=resolution_text,
            root_cause=root_cause,
            outcome=outcome,
            confidence_score=confidence,
            reasoning=reasoning,
            created_by=engineer_id,
            recommendedsteps=recommendedsteps,
        )
        self.db.add(res)
        self.db.commit()
        self.db.refresh(res)

        # optionally update ticket embedding now that we have a final resolution
        ticket = self.db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if ticket:
            ticket.embedding = self._combined_embedding_text(ticket, resolution_text)
            self.db.add(ticket)
            self.db.commit()
            self.db.refresh(ticket)
        return res

    def _combined_embedding_text(self, ticket: Ticket, resolution_text: str) -> str:
        # placeholder; actual embedding computed by InsightsBuddy
        return ticket.title + "\n" + ticket.description + "\n" + resolution_text

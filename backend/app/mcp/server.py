from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

from app.agents.insights import InsightsBuddy
from app.agents.communication import CommCoach
from app.utils.llm import draft_email_from_summary
from app.db.models.email import Email


class MCPServer:
    """Model‑Context‑Protocol server that orchestrates agents for ticket
    analysis and communication.  The UI or any other caller can instantiate this
    class with a database session and invoke the high‑level methods.

    In a production setup you might run the server as a separate process, expose
    an HTTP endpoint, or wire the methods into FastAPI routers.  For now the
    class is just a convenient wrapper around the two agents you asked for.
    """

    def __init__(self, db: Session):
        self.db = db
        self.insights = InsightsBuddy(db)
        self.comm = CommCoach(db)

    def handle_new_ticket(
        self,
        ticket_id: UUID,
        engineer_id: Optional[UUID] = None,
        engineer_name: Optional[str] = None,
        progress=None,
    ) -> dict:
        """Called when an engineer opens/assigns a ticket or when an external
        trigger detects a NEW ticket.  Returns a draft email record along with
        analysis results so the UI can display everything.
        """
        result = self.insights.analyse_ticket(ticket_id, progress=progress)
        # the insights result contains ticket object, similar_resolutions, etc.
        summary = result["recommendation"]
        if progress:
            progress("Drafting customer email")
        draft_body = draft_email_from_summary(
            summary,
            sender_name=engineer_name or "Support Team",
        )

        draft_email = self.comm.draft_email(
            ticket_id=ticket_id, body=draft_body, engineer_id=engineer_id
        )

        return {"insights": result, "draft_email": draft_email}

    def approve_and_send(self, email_id: UUID) -> Email:
        """Called by the UI when the engineer approves the draft.  Approves the
        email, sends it, and returns the updated email object."""
        email = self.comm.approve_email(email_id)
        self.comm.send_email(email)
        return email

    def update_draft_email(
        self,
        email_id: UUID,
        subject: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Email:
        """Update a draft email before approval."""
        return self.comm.update_draft_email(
            email_id=email_id,
            subject=subject,
            body=body,
        )

    def log_final_resolution(
        self,
        ticket_id: UUID,
        resolution_text: str,
        root_cause: Optional[str] = None,
        outcome: Optional[str] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
        engineer_id: Optional[UUID] = None,
        is_kb: bool = False,
    ):
        """Record a resolution (called after email send or in a separate step)."""
        return self.comm.log_resolution(
            ticket_id=ticket_id,
            resolution_text=resolution_text,
            root_cause=root_cause,
            outcome=outcome,
            confidence=confidence,
            reasoning=reasoning,
            engineer_id=engineer_id,
            is_final=True,
            is_kb=is_kb,
        )

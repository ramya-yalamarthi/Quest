from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
import json

from app.agents.insights import InsightsBuddy
from app.agents.communication import CommCoach
from app.utils.llm import draft_email_from_summary
from app.db.models.email import Email
from app.db.models.resolution import Resolution


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
        trigger detects a NEW ticket. Returns only analysis results; draft email is not created until Send is clicked."""
        result = self.insights.analyse_ticket(ticket_id, progress=progress)

        # Summarize ticket info using SummarizationAgent
        from app.db.models.ticket import Ticket
        from app.agents.summarization_agent import SummarizationAgent
        from app.utils.llm import LLMClient
        ticket = self.db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if ticket:
            # If ticket_summary exists, use it; else generate and save
            if ticket.ticket_summary:
                result["ticket_summary"] = ticket.ticket_summary
                result["error_codes"] = []
            else:
                llm = LLMClient()
                summarizer = SummarizationAgent(ticket.title, ticket.description)
                summary_result = summarizer.run(llm)
                summary = summary_result.get("summary", "No summary available.")
                result["ticket_summary"] = summary
                result["error_codes"] = summary_result.get("error_codes", [])
                # Save summary to ticket
                ticket.ticket_summary = summary
                self.db.commit()
            # Ensure ticket is included as a dict
            result["ticket"] = dict(ticket.__dict__)
        else:
            result["ticket_summary"] = "No summary available."
            result["error_codes"] = []
            result["ticket"] = {}

        # Save analysis results to resolutions table for caching
        if progress:
            progress("Saving analysis results")
        self._save_analysis_cache(
            ticket_id=ticket_id,
            root_cause=result["root_cause"],
            recommendation=result["recommendation"],
            # web_solutions=result.get("web_solutions", []),
            engineer_id=engineer_id,
        )
        return {"insights": result, "draft_email": None}
    
    def _save_analysis_cache(
        self,
        ticket_id: UUID,
        root_cause: str,
        recommendation: str,
        # web_solutions: list,
        engineer_id: Optional[UUID] = None,
    ):
        """Save analysis results as a cached resolution for quick retrieval."""
        # Check if analysis cache already exists
        existing = (
            self.db.query(Resolution)
            .filter(Resolution.ticket_id == ticket_id)
            .first()
        )
        
        # Store web_solutions as JSON in reasoning field
        # web_solutions_json = json.dumps(web_solutions) if web_solutions else None
        
        if existing:
            # Update existing cache
            existing.root_cause = root_cause
            existing.resolution_text = recommendation
            # existing.reasoning = web_solutions_json
            existing.outcome = []  # Always store as empty list for analysis cache
        else:
            # Create new cache entry
            cache = Resolution(
                ticket_id=ticket_id,
                resolution_text=recommendation,
                root_cause=root_cause,
                outcome=[],  # Use empty list to mark as analysis cache
                # reasoning=web_solutions_json,
                created_by=engineer_id,
            )
            self.db.add(cache)

            self.db.commit()

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
        outcome: Optional[list[dict]] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
        engineer_id: Optional[UUID] = None,
        is_kb: bool = False,
        recommendedsteps: Optional[list] = None,
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
            recommendedsteps=recommendedsteps,
        )

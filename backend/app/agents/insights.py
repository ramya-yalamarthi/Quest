from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.db.models.ticket import Ticket
from app.db.models.resolution import Resolution
from app.utils.embeddings import get_embedding
from app.utils.llm import summarize_root_cause_with_llm


class InsightsBuddy:
    """Agent responsible for semantic search over historical tickets and
    summarising root causes / recommended steps for a new ticket.

    The implementation uses a pgvector column on both the `tickets` and
    `resolutions` tables; in the database the vector stores an embedding
    derived from the combination of ticket title, description and any
    final resolution text.  """

    def __init__(self, db: Session):
        self.db = db

    def build_ticket_embedding(self, ticket: Ticket) -> List[float]:
        # combine all text that should be searchable
        pieces: List[str] = [ticket.title, ticket.description]
        # if the ticket already has a final resolution, include it too
        if ticket.embedding is not None:  # note: this is only a heuristic
            pieces.append("<existing-resolution>")
        text = "\n".join(pieces)
        return get_embedding(text)

    def index_ticket(self, ticket: Ticket) -> None:
        """(Re)compute embedding for a ticket and store it in the DB."""
        emb = self.build_ticket_embedding(ticket)
        ticket.embedding = emb
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)

    def find_similar_resolutions(
        self, query_embedding: List[float], limit: int = 5
    ) -> List[Resolution]:
        """Return a list of historical final/KB resolutions ordered by similarity."""
        # Example using pgvector op '<->' for cosine distance.  adjust to your
        # flavour of SQLAlchemy if necessary.
        return (
            self.db
            .query(Resolution)
            .filter(Resolution.embedding != None)
            .filter(Resolution.is_final == True)
            .order_by(Resolution.embedding.op("<->")(query_embedding))
            .limit(limit)
            .all()
        )

    def find_similar_tickets(
        self,
        query_embedding: List[float],
        exclude_ticket_id: UUID,
        limit: int = 5,
    ) -> List[Ticket]:
        """Find similar tickets based on ticket embeddings."""
        return (
            self.db
            .query(Ticket)
            .filter(Ticket.embedding != None)
            .filter(Ticket.ticket_id != exclude_ticket_id)
            .order_by(Ticket.embedding.op("<->")(query_embedding))
            .limit(limit)
            .all()
        )

    def analyse_ticket(self, ticket_id: UUID, progress=None) -> dict:
        """Top‑level entrypoint called by the MCP server/UI.

        * loads the ticket
        * ensures an embedding exists
        * finds the most similar past resolutions
        * asks an LLM to produce a root cause / recommendation summary
        """
        ticket = self.db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if not ticket:
            raise ValueError(f"ticket {ticket_id} not found")

        if progress:
            progress("Computing ticket embedding")

        # compute or update the ticket embedding
        if ticket.embedding is None:
            self.index_ticket(ticket)

        ticket_text = f"Title: {ticket.title}\nDescription: {ticket.description}"

        if progress:
            progress("Finding similar tickets")

        # 1) find similar tickets based on ticket embeddings
        similar_tickets = self.find_similar_tickets(ticket.embedding, ticket.ticket_id)
        similar_ticket_ids = [t.ticket_id for t in similar_tickets]

        if progress:
            progress("Fetching historical resolutions")

        # 2) fetch resolutions for those similar tickets
        resolutions_q = (
            self.db
            .query(Resolution)
            .filter(Resolution.ticket_id.in_(similar_ticket_ids))
            .filter(Resolution.is_final == True)
            .filter(Resolution.confidence_score != None)
            .filter(Resolution.confidence_score >= 0.70)
        )

        if progress:
            progress("Ranking resolutions by similarity")

        # 3) if resolution embeddings exist, rank by similarity to current ticket
        if ticket.embedding is not None:
            resolutions_q = resolutions_q.filter(Resolution.embedding != None)
            resolutions_q = resolutions_q.order_by(Resolution.embedding.op("<->")(ticket.embedding))

        similar_resolutions: List[Resolution] = resolutions_q.limit(10).all()

        historical_snippets: List[str] = []
        if similar_resolutions:
            tickets_by_id = {t.ticket_id: t for t in similar_tickets}
            for r in similar_resolutions:
                t = tickets_by_id.get(r.ticket_id)
                if t:
                    snippet = (
                        f"Ticket: {t.title}\n"
                        f"Description: {t.description}\n"
                        f"Resolution: {r.resolution_text}"
                    )
                else:
                    snippet = f"Resolution: {r.resolution_text}"
                historical_snippets.append(snippet)

        # record audit event (optional)
        # ... code here to log to ai_audit_log table if desired ...

        if progress:
            progress("Summarizing what worked and what did not")

        root_cause, recommendation = summarize_root_cause_with_llm(
            ticket_text, historical_snippets
        )
        return {
            "ticket": ticket,
            "similar_resolutions": similar_resolutions,
            "similar_tickets": similar_tickets,
            "root_cause": root_cause,
            "recommendation": recommendation,
        }

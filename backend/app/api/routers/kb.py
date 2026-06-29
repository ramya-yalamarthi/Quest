from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.deps import get_db
from app.auth.deps import get_current_user
from app.schemas.kb import KBFeedbackCreate, KBFeedbackResponse
from app.db.models.ticket_kb_mapping import TicketKBMapping
from app.db.models.kb_article import KBArticle
from app.db.models.kb_feedback import KBFeedback
from app.db.models.ticket import Ticket
from app.agents.kb import submit_kb_feedback, match_kb_articles, record_kb_mapping

router = APIRouter(prefix="/kb", tags=["kb"])


@router.get("/{ticket_id}/recommendations")
def get_recommendations(ticket_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_user)):
    """KB articles already matched to this ticket (from the InsightsBuddy
    analysis run), ranked by success rate + avg resolution time."""
    rows = (
        db.query(TicketKBMapping, KBArticle)
        .join(KBArticle, KBArticle.kb_id == TicketKBMapping.kb_id)
        .filter(TicketKBMapping.ticket_id == ticket_id)
        .order_by(TicketKBMapping.recommended_at.desc())
        .all()
    )
    return [{
        "kb_id": str(a.kb_id), "title": a.title, "url": a.url, "summary": a.summary,
        "category": a.category, "similarity": float(m.similarity) if m.similarity is not None else None,
        "success_rate": round(a.success_rate, 4), "avg_resolution_hours": a.avg_resolution_hours,
    } for m, a in rows]


@router.post("/feedback", response_model=KBFeedbackResponse)
def record_feedback(payload: KBFeedbackCreate, db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Thumbs up/down on ONE cited KB article (distinct from the overall
    recommendation's /orchestrator/feedback). On 👎, immediately surfaces the
    next-best alternative -- the highest-ranked article NOT yet shown (and not
    previously disliked) for this ticket, so the engineer isn't stuck."""
    article = db.query(KBArticle).filter(KBArticle.kb_id == payload.kb_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="KB article not found")
    submit_kb_feedback(
        db, ticket_id=payload.ticket_id, kb_id=payload.kb_id, verdict=payload.verdict,
        comment=payload.comment or "", created_by=UUID(current["user_id"]),
    )
    feedback_row = (
        db.query(KBFeedback)
        .filter(KBFeedback.ticket_id == payload.ticket_id, KBFeedback.kb_id == payload.kb_id)
        .order_by(KBFeedback.created_at.desc())
        .first()
    )

    next_best = None
    if payload.verdict == "dislike":
        ticket = db.query(Ticket).filter(Ticket.ticket_id == payload.ticket_id).first()
        if ticket:
            shown = {str(kb_id) for (kb_id,) in
                     db.query(TicketKBMapping.kb_id).filter(TicketKBMapping.ticket_id == payload.ticket_id).all()}
            disliked = {str(kb_id) for (kb_id,) in
                        db.query(KBFeedback.kb_id).filter(KBFeedback.ticket_id == payload.ticket_id,
                                                            KBFeedback.verdict == "dislike").all()}
            candidates = match_kb_articles(db, ticket.title, ticket.description, top_k=1,
                                            exclude_kb_ids=shown | disliked)
            if candidates:
                next_best = candidates[0]
                record_kb_mapping(db, payload.ticket_id, next_best["kb_id"], next_best["similarity"])

    return {"feedback": feedback_row, "next_best": next_best}

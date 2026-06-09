from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
import json
from typing import Optional

from app.deps import get_db
from app.auth.deps import get_current_user
from app.schemas.ticket import TicketCreate, TicketOut, TicketAssignRequest, TicketStatusRequest
from app.mcp import tools
from app.db.models.resolution import Resolution
from app.db.models.email import Email
from pydantic import BaseModel

router = APIRouter(prefix="/tickets", tags=["tickets"])

@router.get("", response_model=list[TicketOut])
def list_tickets(
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    return tools.list_tickets(
        db,
        role=current["role"],
        user_id=UUID(current["user_id"]),
        status=status,
        query=q,
    )

@router.post("", response_model=TicketOut)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db), current=Depends(get_current_user)):
    return tools.create_ticket(
        db,
        title=payload.title,
        description=payload.description,
        created_by_user_id=UUID(current["user_id"]),
    )

@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_user)):
    t = tools.get_ticket(db, ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if current["role"] == "REQUESTER" and t.created_by != UUID(current["user_id"]):
        raise HTTPException(status_code=403, detail="Not allowed")

    return t

@router.post("/{ticket_id}/assign", response_model=TicketOut)
def assign_ticket(ticket_id: UUID, payload: TicketAssignRequest, db: Session = Depends(get_db), current=Depends(get_current_user)):
    if current["role"] != "SUPPORT":
        raise HTTPException(status_code=403, detail="Only SUPPORT can assign tickets")

    assignee = tools.get_user_by_email(db, payload.assigned_to_email)
    if not assignee:
        raise HTTPException(status_code=404, detail="Assignee user not found")

    t = tools.assign_ticket(db, ticket_id=ticket_id, assigned_to_user_id=assignee.user_id)
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return t

@router.post("/{ticket_id}/status", response_model=TicketOut)
def update_status(ticket_id: UUID, payload: TicketStatusRequest, db: Session = Depends(get_db), current=Depends(get_current_user)):
    if current["role"] != "SUPPORT":
        raise HTTPException(status_code=403, detail="Only SUPPORT can update status")

    try:
        t = tools.set_ticket_status(db, ticket_id=ticket_id, status=payload.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return t


class IncidentBriefAction(BaseModel):
    title: str
    detail: str


class IncidentBriefOut(BaseModel):
    what_we_know: list[str]
    what_has_been_done: list[str]
    recommended_actions: list[IncidentBriefAction]
    generated_at: str


@router.get("/{ticket_id}/incident-brief", response_model=IncidentBriefOut)
def get_incident_brief(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    from app.utils.llm import generate_incident_brief

    t = tools.get_ticket(db, ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if current["role"] == "REQUESTER" and t.created_by != UUID(current["user_id"]):
        raise HTTPException(status_code=403, detail="Not allowed")

    resolution = db.query(Resolution).filter(Resolution.ticket_id == ticket_id).first()

    similar_count = 0
    recommended_steps = []
    root_cause = None

    if resolution:
        root_cause = resolution.root_cause
        if isinstance(resolution.outcome, list):
            similar_count = len(resolution.outcome)
        if isinstance(resolution.recommendedsteps, list):
            recommended_steps = resolution.recommendedsteps

    brief = generate_incident_brief(
        title=t.title,
        description=t.description,
        summary=t.ticket_summary or "",
        priority=t.priority or "Normal",
        service=t.service or "General",
        env=t.env or "Production",
        region=t.region or "Unknown",
        status=t.status,
        created_at=t.created_at.isoformat() if t.created_at else "",
        assigned_at=t.assigned_at.isoformat() if t.assigned_at else None,
        root_cause=root_cause,
        similar_count=similar_count,
        recommended_steps=recommended_steps,
    )

    # Normalise recommended_actions to IncidentBriefAction shape
    actions = []
    for item in brief.get("recommended_actions", []):
        if isinstance(item, dict):
            actions.append(IncidentBriefAction(
                title=item.get("title", ""),
                detail=item.get("detail", ""),
            ))

    return IncidentBriefOut(
        what_we_know=brief.get("what_we_know", []),
        what_has_been_done=brief.get("what_has_been_done", []),
        recommended_actions=actions,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


class WebSolution(BaseModel):
    title: str
    url: str
    summary: Optional[str] = None
    steps: list[str]


class CachedAnalysis(BaseModel):
    root_cause: str
    recommendation: str
    web_solutions: list[WebSolution]
    draft_email_id: Optional[UUID] = None
    draft_email_subject: Optional[str] = None
    draft_email_body: Optional[str] = None


@router.get("/{ticket_id}/analysis", response_model=CachedAnalysis | None)
def get_cached_analysis(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_user)
):
    """Get cached analysis results if they exist for this ticket."""
    # Get cached analysis resolution
    cached = (
        db.query(Resolution)
        .filter(Resolution.ticket_id == ticket_id)
        .first()
    )
    
    if not cached:
        return None
    
    # Parse web_solutions from JSON
    web_solutions = []
    if cached.reasoning:
        try:
            web_solutions_data = json.loads(cached.reasoning)
            web_solutions = [
                WebSolution(**item) if isinstance(item, dict) else WebSolution(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    summary=item.get("summary"),
                    steps=item.get("steps", [])
                )
                for item in web_solutions_data
            ]
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Get the most recent draft email for this ticket
    draft_email = (
        db.query(Email)
        .filter(Email.ticket_id == ticket_id)
        .filter(Email.type == "DRAFT")
        .order_by(Email.created_at.desc())
        .first()
    )
    
    return CachedAnalysis(
        root_cause=cached.root_cause or "",
        recommendation=cached.resolution_text or "",
        web_solutions=web_solutions,
        draft_email_id=draft_email.email_id if draft_email else None,
        draft_email_subject=draft_email.subject if draft_email else None,
        draft_email_body=draft_email.body if draft_email else None,
    )
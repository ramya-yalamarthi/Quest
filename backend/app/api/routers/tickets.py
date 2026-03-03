from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.deps import get_db
from app.auth.deps import get_current_user
from app.schemas.ticket import TicketCreate, TicketOut, TicketAssignRequest, TicketStatusRequest
from app.mcp import tools

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
    if current["role"] != "REQUESTER":
        raise HTTPException(status_code=403, detail="Only REQUESTER can create tickets")
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
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.deps import get_db
from app.auth.deps import get_current_user
from app.schemas.resolution import ResolutionCreate, ResolutionOut
from app.mcp import tools

router = APIRouter(prefix="/resolutions", tags=["resolutions"])


def support_only(current):
    if current["role"] not in {"SUPPORT", "SUPPORT_MANAGER"}:
        raise HTTPException(status_code=403, detail="Only SUPPORT or MANAGER role allowed")


@router.get("", response_model=list[ResolutionOut])
def list_all(ticket_id: UUID | None = None, db: Session = Depends(get_db), current=Depends(get_current_user)):
    support_only(current)
    return tools.list_resolutions(db, ticket_id=ticket_id)


@router.get("/{res_id}", response_model=ResolutionOut)
def get_one(res_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_user)):
    support_only(current)
    r = tools.get_resolution(db, res_id)
    if not r:
        raise HTTPException(status_code=404, detail="Resolution not found")
    return r


@router.post("", response_model=ResolutionOut)
def create_resolution(payload: ResolutionCreate, db: Session = Depends(get_db), current=Depends(get_current_user)):
    support_only(current)
    return tools.add_resolution(
        db,
        ticket_id=payload.ticket_id,
        resolution_text=payload.resolution_text,
        root_cause=payload.root_cause,
        outcome=payload.outcome,
        confidence_score=payload.confidence_score,
        reasoning=payload.reasoning,
        is_final=payload.is_final,
        is_kb=payload.is_kb,
        created_by=UUID(current["user_id"]),
    )

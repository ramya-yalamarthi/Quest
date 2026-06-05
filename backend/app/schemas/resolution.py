from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class ResolutionCreate(BaseModel):
    ticket_id: UUID
    resolution_text: str
    root_cause: Optional[str]
    recommendedsteps: Optional[list[dict]]
    outcome: Optional[list[dict]]
    confidence_score: Optional[float]
    reasoning: Optional[str]

class ResolutionOut(BaseModel):
    resolution_id: UUID
    ticket_id: UUID
    resolution_text: Optional[str] = None
    recommendedsteps: Optional[list[dict]] = None
    root_cause: Optional[str]
    outcome: Optional[list[dict]]
    confidence_score: Optional[float]
    reasoning: Optional[str]
    created_by: Optional[UUID]
    created_at: datetime
    total_similar_tickets_above70: Optional[int] = None

    class Config:
        from_attributes = True
        fields = {
            'embedding': {'exclude': True}
        }

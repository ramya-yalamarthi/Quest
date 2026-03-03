from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class ResolutionCreate(BaseModel):
    ticket_id: UUID
    resolution_text: str
    root_cause: Optional[str]
    outcome: Optional[str]
    confidence_score: Optional[float]
    reasoning: Optional[str]
    is_final: Optional[bool] = True
    is_kb: Optional[bool] = False


class ResolutionOut(BaseModel):
    resolution_id: UUID
    ticket_id: UUID
    resolution_text: str
    root_cause: Optional[str]
    outcome: Optional[str]
    confidence_score: Optional[float]
    reasoning: Optional[str]
    is_final: bool
    is_kb: bool
    created_by: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True

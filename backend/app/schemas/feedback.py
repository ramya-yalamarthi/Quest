from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Literal


class FeedbackCreate(BaseModel):
    ticket_id: UUID
    verdict: Literal["like", "dislike"]   # invalid value -> 422 automatically
    comment: Optional[str] = None
    ai_event_id: Optional[UUID] = None


class FeedbackOut(BaseModel):
    feedback_id: UUID
    ticket_id: UUID
    ai_event_id: Optional[UUID] = None
    agent_name: str
    verdict: str
    comment: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True

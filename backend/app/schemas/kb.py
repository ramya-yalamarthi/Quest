from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Literal


class KBFeedbackCreate(BaseModel):
    ticket_id: UUID
    kb_id: UUID
    verdict: Literal["like", "dislike"]   # invalid value -> 422 automatically
    comment: Optional[str] = None


class KBFeedbackOut(BaseModel):
    kb_feedback_id: UUID
    ticket_id: UUID
    kb_id: UUID
    verdict: str
    comment: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class KBFeedbackResponse(BaseModel):
    feedback: KBFeedbackOut
    next_best: Optional[dict] = None  # set when verdict == "dislike" and an alternative exists

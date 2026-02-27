from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class TicketCreate(BaseModel):
    title: str
    description: str

class TicketOut(BaseModel):
    ticket_id: UUID
    title: str
    description: str
    status: str
    created_by: Optional[UUID]
    assigned_to: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TicketAssignRequest(BaseModel):
    assigned_to_email: str

class TicketStatusRequest(BaseModel):
    status: str  # NEW|ASSIGNED|RESOLVED
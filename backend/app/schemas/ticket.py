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
    assigned_at: Optional[datetime] = None
    escalated_manager_id1: Optional[UUID] = None
    escalated_manager_id2: Optional[UUID] = None
    escalated_manager1_at: Optional[datetime] = None
    escalated_manager2_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    last_email_at: Optional[datetime] = None
    next_update_due_at: Optional[datetime] = None
    sla_status: Optional[str] = None

    class Config:
        from_attributes = True

class TicketAssignRequest(BaseModel):
    assigned_to_email: str

class TicketStatusRequest(BaseModel):
    status: str  # NEW|ASSIGNED|RESOLVED
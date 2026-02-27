from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class UserOut(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True
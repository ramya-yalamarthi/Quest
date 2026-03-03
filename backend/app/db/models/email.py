import uuid
from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.base import Base


class Email(Base):
    __tablename__ = "emails"

    email_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.ticket_id"), nullable=True)
    type = Column(Text, nullable=False)  # DRAFT | APPROVED
    subject = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # convenience helpers
    def is_draft(self) -> bool:
        return self.type == "DRAFT"

    def is_approved(self) -> bool:
        return self.type == "APPROVED"

import uuid
from sqlalchemy import Column, Text, DateTime, ForeignKey, Boolean, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

# vector type for pgvector embeddings; install pgvector in requirements
from pgvector.sqlalchemy import Vector

from app.db.base import Base

class Ticket(Base):
    ticket_summary = Column(Text, nullable=True)  # AI-generated summary
    __tablename__ = "tickets"

    ticket_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)

    status = Column(Text, nullable=False, default="NEW")  # NEW | ASSIGNED | RESOLVED

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    escalated_manager_id1 = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    escalated_manager_id2 = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    escalated_manager1_at = Column(DateTime(timezone=True), nullable=True)
    escalated_manager2_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now())

    # combined embedding of ticket title/description and any final resolution text
    embedding = Column(Vector(1536))

    # New fields for UI display
    priority = Column(Text, nullable=True, default="Normal")  # e.g. '🔴 P1 — Critical'
    service_status = Column(Text, nullable=True, default="OK")  # e.g. '⚠ Service Degraded'
    service = Column(Text, nullable=True, default="General")  # e.g. 'Analytics Pipeline'
    env = Column(Text, nullable=True, default="Production")  # e.g. 'Production'
    region = Column(Text, nullable=True, default="Unknown")  # e.g. 'US-West-2'
    has_resolution = Column(Boolean, nullable=False, default=False)
import uuid
from sqlalchemy import Column, Text, Boolean, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.db.base import Base
from sqlalchemy import JSON


class Resolution(Base):
    __tablename__ = "resolutions"

    resolution_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.ticket_id"), nullable=False)
    resolution_text = Column(Text, nullable=True)
    recommendedsteps = Column(JSON, nullable=True)
    root_cause = Column(Text, nullable=True)
    # JSON import moved above
    outcome = Column(JSON, nullable=True)  # stores list of similar tickets as JSON
    confidence_score = Column(Numeric(5, 4), nullable=True)
    reasoning = Column(Text, nullable=True)

    # embedding vector of resolution text + any associated ticket metadata
    embedding = Column(Vector(1536))

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    total_similar_tickets_above70 = Column(Numeric, nullable=True)

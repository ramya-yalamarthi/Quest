import uuid
from sqlalchemy import Column, Text, Boolean, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.db.base import Base


class Resolution(Base):
    __tablename__ = "resolutions"

    resolution_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.ticket_id"), nullable=False)
    resolution_text = Column(Text, nullable=False)
    root_cause = Column(Text, nullable=True)
    outcome = Column(Text, nullable=True)  # success|fail|partial|pending
    confidence_score = Column(Numeric(5, 4), nullable=True)
    reasoning = Column(Text, nullable=True)
    is_final = Column(Boolean, nullable=False, default=False)
    is_kb = Column(Boolean, nullable=False, default=False)

    # embedding vector of resolution text + any associated ticket metadata
    embedding = Column(Vector(1536))

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

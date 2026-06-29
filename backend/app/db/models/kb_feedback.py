import uuid
from sqlalchemy import Column, Text, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base


class KBFeedback(Base):
    """Engineer like/dislike on ONE cited KB article (separate from
    recommendation_feedback, which rates the overall recommendation)."""

    __tablename__ = "kb_feedback"

    kb_feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.ticket_id"), nullable=False, index=True)
    kb_id = Column(UUID(as_uuid=True), ForeignKey("kb_articles.kb_id"), nullable=False, index=True)
    verdict = Column(String, nullable=False)  # "like" | "dislike"
    comment = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

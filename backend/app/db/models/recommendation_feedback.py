import uuid
from sqlalchemy import Column, Text, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base


class RecommendationFeedback(Base):
    """Engineer like/dislike on a recommendation advisory.

    Feeds the Recommendation Agent's feedback-aware confidence and gives a simple
    quality signal per advisory. ai_event_id links back to the ai_audit_log row
    for the recommendation that was rated (nullable).
    """

    __tablename__ = "recommendation_feedback"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    ai_event_id = Column(UUID(as_uuid=True), nullable=True)
    agent_name = Column(Text, nullable=False, default="recommendation")
    verdict = Column(String, nullable=False)  # "like" | "dislike"
    comment = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

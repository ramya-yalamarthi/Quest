import uuid
from sqlalchemy import Column, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func

from app.db.base import Base


class AiAuditLog(Base):
    """Audit trail of every agent / supervisor decision.

    Written by the Orchestration Agent (O-06) and by the analysis agents.
    Mirrors the ai_audit_log table defined in backend/README.md.

    NOTE: the README schema constrains agent_name to ('InsightsBuddy','CommCoach').
    The supervisor uses names like 'supervisor' / 'routing' / 'diagnosis' /
    'recommendation', so that CHECK constraint must be widened -- see the ALTER
    in app/orchestrator/README.md.
    """

    __tablename__ = "ai_audit_log"

    ai_event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tickets.ticket_id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_name = Column(Text, nullable=False)
    model_name = Column(Text, nullable=False, default="orchestrator")
    input_json = Column(JSONB, nullable=False, default=dict)
    output_json = Column(JSONB, nullable=False, default=dict)
    confidence_json = Column(JSONB, nullable=True)
    supporting_incident_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    was_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

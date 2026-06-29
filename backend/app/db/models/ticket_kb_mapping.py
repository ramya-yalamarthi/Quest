import uuid
from sqlalchemy import Column, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base


class TicketKBMapping(Base):
    """Which KB article(s) were surfaced for which ticket, and how well they
    matched -- the basis for "similar tickets -> KB articles used".

    ticket_id has NO foreign key (same precedent as recommendation_feedback):
    the D365 pipeline's "ticket" is a Dataverse Case GUID, not a row in the
    Postgres tickets table, so this column has to hold either kind of id."""

    __tablename__ = "ticket_kb_mapping"

    mapping_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    kb_id = Column(UUID(as_uuid=True), ForeignKey("kb_articles.kb_id"), nullable=False, index=True)
    similarity = Column(Numeric, nullable=True)
    recommended_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

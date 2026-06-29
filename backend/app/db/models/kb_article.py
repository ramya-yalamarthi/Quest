import uuid
from sqlalchemy import Column, Text, Integer, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class KBArticle(Base):
    """Catalog of internal KB articles / troubleshooting guides. Content
    (title/url/summary/category) is ops-maintained; the stats columns are
    updated by the app as tickets get resolved using a given article, and
    drive the success-rate ranking (KB Recommendations)."""

    __tablename__ = "kb_articles"

    kb_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    category = Column(Text, nullable=True)
    embedding = Column(Vector(1536))

    times_recommended = Column(Integer, nullable=False, default=0)
    times_resolved = Column(Integer, nullable=False, default=0)
    total_resolution_hours = Column(Numeric, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def success_rate(self) -> float:
        return (self.times_resolved / self.times_recommended) if self.times_recommended else 0.0

    @property
    def avg_resolution_hours(self):
        if not self.times_resolved:
            return None
        return float(self.total_resolution_hours) / self.times_resolved

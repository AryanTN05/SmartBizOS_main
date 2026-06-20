from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from db.connection import Base
import uuid

class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)

    score = Column(Integer, nullable=False)
    reason = Column(Text)
    factors = Column(JSONB, default=dict)
    scored_by = Column(String, default='ai')
    scored_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

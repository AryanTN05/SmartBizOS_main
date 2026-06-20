from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from db.connection import Base
import uuid

class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)

    action_type = Column(String, nullable=False)
    description = Column(Text)
    metadata_ = Column("metadata", JSONB, default=dict)
    triggered_by = Column(String, default='system')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

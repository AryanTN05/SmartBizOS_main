from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.sql import func
from db.connection import Base
import uuid

class Enrichment(Base):
    __tablename__ = "enrichment"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, unique=True)

    company_size = Column(String)
    employee_count = Column(Integer)
    industry = Column(String)
    funding_stage = Column(String)
    funding_amount = Column(String)

    tech_stack = Column(ARRAY(String), default=list)
    pain_points = Column(Text)
    recent_news = Column(JSONB, default=list)
    competitor_tools = Column(ARRAY(String), default=list)

    enrichment_status = Column(String, default='pending')
    last_enriched_at = Column(DateTime(timezone=True))
    raw_data = Column(JSONB, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

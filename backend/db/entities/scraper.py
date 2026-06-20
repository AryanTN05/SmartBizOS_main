from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from db.connection import Base
import uuid

class ScraperResult(Base):
    __tablename__ = "scraper_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    source_type = Column(String, nullable=False)
    raw_data = Column(JSONB, nullable=False)

    extracted_name = Column(String)
    extracted_email = Column(String)
    extracted_company = Column(String)
    extracted_url = Column(String)

    relevance_score = Column(Integer)
    status = Column(String, default='pending', index=True)
    converted_lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"))

    scraped_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True))

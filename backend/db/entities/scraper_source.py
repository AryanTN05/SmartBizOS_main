import uuid

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.connection import Base


class ScraperSource(Base):
    __tablename__ = "scrapers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    source_key = Column(String, nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="available")
    schedule = Column(String, default="—")
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    leads_last_run = Column(Integer, default=0)
    leads_total = Column(Integer, default=0)
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

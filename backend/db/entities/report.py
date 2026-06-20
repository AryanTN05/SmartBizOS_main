import uuid

from sqlalchemy import Boolean, Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from db.connection import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    kind = Column(String, nullable=False, default="weekly")
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    headline = Column(Text)
    narrative = Column(Text)
    stats = Column(JSONB, nullable=False, default=dict)
    prompt_version = Column(String, default="v1")
    model = Column(String, default="gemini/gemini-2.5-flash")
    has_embedding = Column(Boolean, default=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

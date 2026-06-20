import uuid

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func

from db.connection import Base


class AutomationTemplate(Base):
    __tablename__ = "automation_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    version = Column(String, nullable=False, default="v1")
    status = Column(String, nullable=False, default="active")
    step_count = Column(Integer, nullable=False, default=0)
    channels_used = Column(ARRAY(String), default=list)
    steps = Column(JSONB, nullable=False, default=list)
    placeholder_schema = Column(ARRAY(String), default=list)
    previews = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)

    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"))
    template_id = Column(UUID(as_uuid=True), ForeignKey("automation_templates.id", ondelete="SET NULL"))
    template_key = Column(String, nullable=False)
    inngest_event_id = Column(String)

    status = Column(String, nullable=False, default="running")
    current_step_name = Column(String)
    next_fire_at = Column(DateTime(timezone=True))

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    created_by = Column(String, default="admin:demo")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AutomationEvent(Base):
    __tablename__ = "automation_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("automation_runs.id", ondelete="CASCADE"), nullable=False)
    step_name = Column(String, nullable=False)
    channel = Column(String)
    outcome = Column(String, nullable=False)
    payload = Column(JSONB, default=dict)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())

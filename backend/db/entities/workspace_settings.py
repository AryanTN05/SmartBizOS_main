import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from db.connection import Base


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, unique=True)

    icp_description = Column(Text)
    workspace_name = Column(String)
    sender_name = Column(String)

    # Incoming-webhook URL the workspace pastes from Slack. We POST a Slack
    # blocks payload here when a scraper produces a lead with score >=
    # slack_alert_min_score. NULL = alerts off.
    slack_webhook_url = Column(Text)
    slack_alert_min_score = Column(Integer, nullable=False, default=80)

    # Queue runs at the prospect's likely 9-11 AM local instead of NOW.
    # Heuristic timezone via email TLD / company domain. Off by default
    # so existing dev workflows aren't surprised by parked sends.
    send_time_optimization = Column(Boolean, nullable=False, default=False)

    # Cal.com / Calendly URL the AI reply drafter and email renderer
    # inject as a soft CTA. Empty = no link inserted. Stored verbatim;
    # validated only by URL prefix.
    calendar_link = Column(String, nullable=True)

    # Apollo ICP overrides. JSON shape:
    #   {"titles": [...], "seniorities": [...], "headcount_ranges": [...]}
    # NULL = use the in-code default (VPs/Heads of Sales/RevOps at
    # mid-market SaaS). When set, the Apollo scraper substitutes these
    # filters per-workspace so each tenant can target their actual ICP.
    apollo_icp = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

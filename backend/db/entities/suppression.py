import uuid

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.connection import Base


class WorkspaceSuppression(Base):
    """Per-tenant suppression list.

    Any (tenant_id, email) pair here is never sent to again. The scheduler
    blocks send_day0 before render and the run is marked completed early
    with outcome="skipped_suppressed". Sources of entries:

      - manual         — user added via UI
      - user_unsub     — recipient clicked the 1-click unsubscribe link
      - bounce_hard    — Resend webhook reported a permanent bounce
      - bounce_soft    — soft-bounced 3+ times in 30 days
      - complained     — Resend webhook reported a spam complaint
    """
    __tablename__ = "workspace_suppressions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    email = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="ux_suppressions_tenant_email"),
    )

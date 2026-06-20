import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, LargeBinary, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.connection import Base


class WorkspaceMailbox(Base):
    """Per-tenant SMTP mailbox for the multi-domain send rotation.

    Each row is one inbox the user has connected. The scheduler picks the
    next eligible mailbox at send time, respecting daily_send_cap so a
    single inbox doesn't burn its reputation. Password is Fernet ciphertext
    using IMAP_ENCRYPTION_KEY — same key as the IMAP poller, since the
    threat model is identical (per-tenant secret at rest in Postgres).
    """
    __tablename__ = "workspace_mailboxes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)

    email = Column(Text, nullable=False)
    from_name = Column(Text, nullable=True)

    host = Column(Text, nullable=False)
    port = Column(Integer, nullable=False, default=587)
    username = Column(Text, nullable=False)
    password_ciphertext = Column(LargeBinary, nullable=False)
    use_tls = Column(Boolean, nullable=False, default=True)

    daily_send_cap = Column(Integer, nullable=False, default=50)
    sent_today = Column(Integer, nullable=False, default=0)
    reset_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_send_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="ux_mailboxes_tenant_email"),
    )

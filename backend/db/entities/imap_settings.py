import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.connection import Base


class WorkspaceImapSettings(Base):
    """Per-tenant IMAP credentials for the reply-detection poller.

    Password is stored as Fernet ciphertext using the IMAP_ENCRYPTION_KEY
    env var. NEVER returned by any GET endpoint — only used internally by
    the poller worker. Decrypted at use time, never logged.
    """
    __tablename__ = "workspace_imap_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    host = Column(Text, nullable=False)
    port = Column(Integer, nullable=False, default=993)
    email = Column(Text, nullable=False)
    password_ciphertext = Column(LargeBinary, nullable=False)
    use_ssl = Column(Boolean, nullable=False, default=True)
    last_poll_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

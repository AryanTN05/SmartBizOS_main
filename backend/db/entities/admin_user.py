from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from db.connection import Base
import uuid


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True, index=True)
    bcrypt_hash = Column(String, nullable=False)
    name = Column(String, nullable=False, default="")
    role = Column(String, nullable=False, default="admin")   # forward-compat hook
    status = Column(String, nullable=False, default="active")  # active | disabled

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

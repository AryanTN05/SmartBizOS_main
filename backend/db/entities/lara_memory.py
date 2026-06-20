import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime
from pgvector.sqlalchemy import Vector
from db.connection import Base

def generate_uuid():
    return str(uuid.uuid4())

class LaraMemory(Base):
    __tablename__ = "lara_memory"

    id = Column(String, primary_key=True, default=generate_uuid)
    vector = Column(Vector(1536))
    session_id = Column(String, index=True)
    source_type = Column(String)
    source_id = Column(String)
    chunk_text = Column(Text)

    # Optional fields for documents — populated per chunk row (same value across
    # every chunk of a given document so the list endpoint can pull them via
    # any chunk).
    filename = Column(String, nullable=True)
    chunk_index = Column(Integer, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String, nullable=True)
    page_count = Column(Integer, nullable=True)
    extraction_status = Column(String, nullable=True)    # 'ready' | 'failed'
    extraction_error = Column(Text, nullable=True)

    # Optional field for conversation memory
    extracted_at = Column(DateTime, default=datetime.utcnow, nullable=True)

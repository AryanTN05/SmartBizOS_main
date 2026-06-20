import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, Float, DateTime, Boolean, JSON, DECIMAL, Date
from sqlalchemy.orm import relationship
from .connection import Base

def generate_uuid():
    return str(uuid.uuid4())

class AutomationSequence(Base):
    __tablename__ = "automation_sequences"
    id = Column(String, primary_key=True, default=generate_uuid)
    lead_id = Column(String) # References main DB leads.id
    sequence_type = Column(String) # nurture, followup, reengagement, breakup
    current_step = Column(Integer, default=1)
    status = Column(String, default="active") # active, paused, completed
    last_sent = Column(DateTime)
    next_send = Column(DateTime)

class Email(Base):
    __tablename__ = "emails"
    id = Column(String, primary_key=True, default=generate_uuid)
    lead_id = Column(String) # References main DB leads.id
    subject = Column(String)
    body = Column(Text)
    status = Column(String, default="sent") # sent, opened, clicked, replied
    sent_at = Column(DateTime, default=datetime.utcnow)
    opened_at = Column(DateTime)

class Report(Base):
    # Renamed from "reports" so this sync-engine model can coexist with the
    # main async backend's reports table (db/entities/report.py) on the same
    # Neon DB. Without the rename, both engines define a "reports" table
    # with different schemas and the second create_all silently skips,
    # leaving Lara's tool reading the wrong row shape.
    __tablename__ = "lara_reports"
    id = Column(String, primary_key=True, default=generate_uuid)
    period_start = Column(Date)
    period_end = Column(Date)
    new_leads = Column(Integer)
    qualified = Column(Integer)
    emails_sent = Column(Integer)
    open_rate = Column(Float)
    narrative = Column(Text)
    raw_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(String, primary_key=True, default=generate_uuid)
    vendor = Column(String)
    amount = Column(DECIMAL(10, 2))
    currency = Column(String, default="USD")
    status = Column(String) # paid, overdue, pending
    due_date = Column(Date)
    category = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, index=True)
    role = Column(String) # "user", "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

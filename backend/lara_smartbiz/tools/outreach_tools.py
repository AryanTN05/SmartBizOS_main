import json
import uuid
from datetime import datetime
from sqlalchemy import select
from lara_smartbiz.db.connection import SessionLocal as LaraSessionLocal
from lara_smartbiz.db.models import Email
from db.connection import SessionLocal as MainSessionLocal
from db.entities import Lead

async def send_email(lead_id: str, subject: str, body: str, send_immediately: bool = True):
    try:
        lead_uuid = uuid.UUID(lead_id)
    except ValueError:
        return json.dumps({"error": "Invalid Lead ID format"})
        
    async with MainSessionLocal() as main_db:
        result_lead = await main_db.execute(select(Lead).filter(Lead.id == lead_uuid))
        lead = result_lead.scalars().first()
        if not lead:
            return json.dumps({"error": "Lead not found"})
            
    db = LaraSessionLocal()
    try:
        email = Email(
            lead_id=lead_id,
            subject=subject,
            body=body,
            status="sent" if send_immediately else "draft",
            sent_at=datetime.utcnow() if send_immediately else None
        )
        db.add(email)
        db.commit()
        db.refresh(email)
        
        return json.dumps({
            "message": "Email queued/sent successfully",
            "email_id": email.id,
            "status": email.status
        })
    finally:
        db.close()

async def get_email_thread(lead_id: str):
    try:
        lead_uuid = uuid.UUID(lead_id)
    except ValueError:
        return json.dumps({"error": "Invalid Lead ID format"})
        
    async with MainSessionLocal() as main_db:
        result_lead = await main_db.execute(select(Lead).filter(Lead.id == lead_uuid))
        lead = result_lead.scalars().first()
        if not lead:
            return json.dumps({"error": "Lead not found"})
            
    db = LaraSessionLocal()
    try:
        emails = db.query(Email).filter(Email.lead_id == lead_id).order_by(Email.sent_at.desc()).all()
        result = []
        for e in emails:
            result.append({
                "id": e.id,
                "subject": e.subject,
                "body": e.body,
                "status": e.status,
                "sent_at": str(e.sent_at) if e.sent_at else None,
                "opened_at": str(e.opened_at) if e.opened_at else None
            })
            
        return json.dumps({"lead": lead.name, "thread": result})
    finally:
        db.close()

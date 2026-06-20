import json
import uuid
from datetime import datetime
from sqlalchemy import select
from lara_smartbiz.db.connection import SessionLocal as LaraSessionLocal
from lara_smartbiz.db.models import AutomationSequence, Email
from db.connection import SessionLocal as MainSessionLocal
from db.entities import Lead

async def get_automation_status(lead_id: str):
    db = LaraSessionLocal()
    try:
        sequences = db.query(AutomationSequence).filter(AutomationSequence.lead_id == lead_id).all()
        result = []
        for seq in sequences:
            result.append({
                "id": seq.id,
                "sequence_type": seq.sequence_type,
                "current_step": seq.current_step,
                "status": seq.status,
                "last_sent": str(seq.last_sent) if seq.last_sent else None,
                "next_send": str(seq.next_send) if seq.next_send else None
            })
        return json.dumps(result if result else {"message": "No active automations for this lead."})
    finally:
        db.close()

async def trigger_sequence(lead_id: str, sequence_type: str):
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
        seq = AutomationSequence(
            lead_id=lead_id,
            sequence_type=sequence_type,
            current_step=1,
            status="active"
        )
        db.add(seq)
        db.commit()
        db.refresh(seq)
        return json.dumps({
            "message": f"Sequence '{sequence_type}' triggered successfully.",
            "sequence_id": seq.id
        })
    finally:
        db.close()

async def get_lead_timeline(lead_id: str):
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
        emails = db.query(Email).filter(Email.lead_id == lead_id).all()
        sequences = db.query(AutomationSequence).filter(AutomationSequence.lead_id == lead_id).all()
        
        timeline = []
        timeline.append({"event": "Lead Created", "date": str(lead.created_at)})
        
        for email in emails:
            timeline.append({
                "event": f"Email Sent: {email.subject}",
                "date": str(email.sent_at),
                "status": email.status
            })
            if email.opened_at:
                timeline.append({
                    "event": f"Email Opened: {email.subject}",
                    "date": str(email.opened_at)
                })
                
        for seq in sequences:
            timeline.append({
                "event": f"Sequence '{seq.sequence_type}' started",
                "status": seq.status
            })
            
        return json.dumps({"timeline": timeline})
    finally:
        db.close()

import json
import uuid
from sqlalchemy import select
from db.connection import SessionLocal
from db.entities import Lead, Enrichment
from config import settings

async def get_leads(status: str = None, min_score: int = None, name: str = None, limit: int = 10):
    async with SessionLocal() as db:
        # Always exclude soft-deleted rows so retired/offensive content never
        # leaks back into Lara responses.
        query = select(Lead).filter(Lead.deleted_at.is_(None))
        if status:
            query = query.filter(Lead.status == status)
        if min_score is not None:
            query = query.filter(Lead.score >= min_score)
        if name:
            query = query.filter(Lead.name.ilike(f"%{name}%"))

        query = query.order_by(Lead.score.desc()).limit(limit)
        result_db = await db.execute(query)
        leads = result_db.scalars().all()

        result = [
            {"id": str(l.id), "name": l.name, "company": l.company_name, "email": l.email, "phone": l.phone, "title": l.title, "score": l.score, "status": l.status}
            for l in leads
        ]
        return json.dumps(result)

async def get_lead_dossier(lead_id: str):
    async with SessionLocal() as db:
        try:
            lead_uuid = uuid.UUID(lead_id)
        except ValueError:
            return json.dumps({"error": "Invalid Lead ID format"})
            
        result_lead = await db.execute(
            select(Lead).filter(Lead.id == lead_uuid, Lead.deleted_at.is_(None))
        )
        lead = result_lead.scalars().first()
        if not lead:
            return json.dumps({"error": "Lead not found"})
        
        result_enrichment = await db.execute(select(Enrichment).filter(Enrichment.lead_id == lead_uuid))
        enrichment = result_enrichment.scalars().first()
        
        result = {
            "id": str(lead.id),
            "name": lead.name,
            "company": lead.company_name,
            "email": lead.email,
            "phone": lead.phone,
            "title": lead.title,
            "linkedin_url": lead.linkedin_url,
            "score": lead.score,
            "status": lead.status,
            "notes": lead.notes
        }
        
        if enrichment:
            result["enrichment"] = {
                "company_size": enrichment.company_size,
                "funding": enrichment.funding_stage,
                "tech_stack": enrichment.tech_stack,
                "pain_points": enrichment.pain_points,
                "recent_news": enrichment.recent_news,
                "score_reason": lead.score_reason # Moved to lead in main DB
            }
            
        return json.dumps(result)

async def create_lead(name: str, company: str = None, email: str = None, phone: str = None, title: str = None, linkedin_url: str = None, source: str = "lara", status: str = "new", score: int = 0):
    async with SessionLocal() as db:
        tenant_id = uuid.UUID(settings.default_tenant_id)
        lead = Lead(
            tenant_id=tenant_id,
            name=name, 
            company_name=company, 
            email=email, 
            phone=phone,
            title=title,
            linkedin_url=linkedin_url,
            source=source, 
            status=status, 
            score=score
        )
        db.add(lead)
        await db.commit()
        await db.refresh(lead)
        return json.dumps({
            "id": str(lead.id), "name": lead.name, "company": lead.company_name, "email": lead.email, "phone": lead.phone, "title": lead.title, "linkedin_url": lead.linkedin_url, "status": lead.status
        })

async def update_lead(lead_id: str, status: str = None, score: int = None, notes: str = None, email: str = None, company: str = None, name: str = None, phone: str = None, title: str = None, linkedin_url: str = None):
    async with SessionLocal() as db:
        try:
            lead_uuid = uuid.UUID(lead_id)
        except ValueError:
            return json.dumps({"error": "Invalid Lead ID format"})
            
        result_lead = await db.execute(
            select(Lead).filter(Lead.id == lead_uuid, Lead.deleted_at.is_(None))
        )
        lead = result_lead.scalars().first()
        if not lead:
            return json.dumps({"error": "Lead not found"})
        
        if status is not None:
            lead.status = status
        if score is not None:
            lead.score = score
        if notes is not None:
            lead.notes = notes
        if email is not None:
            lead.email = email
        if company is not None:
            lead.company_name = company
        if name is not None:
            lead.name = name
        if phone is not None:
            lead.phone = phone
        if title is not None:
            lead.title = title
        if linkedin_url is not None:
            lead.linkedin_url = linkedin_url
            
        await db.commit()
        await db.refresh(lead)
        return json.dumps({
            "id": str(lead.id), "name": lead.name, "company": lead.company_name, "email": lead.email, "phone": lead.phone, "title": lead.title, "linkedin_url": lead.linkedin_url, "status": lead.status, "score": lead.score, "notes": lead.notes
        })

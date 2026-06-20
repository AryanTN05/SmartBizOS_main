import json
import asyncio
from datetime import datetime, timedelta, date
from lara_smartbiz.db.connection import engine, Base, SessionLocal as LaraSessionLocal
from lara_smartbiz.db.models import AutomationSequence, Email, Report, Invoice
from db.connection import SessionLocal as MainSessionLocal
from db.entities import Lead, Enrichment
from config import settings
import uuid

async def seed_db_async():
    print("Creating Lara local tables...")
    Base.metadata.create_all(bind=engine)
    
    lara_db = LaraSessionLocal()
    
    try:
        # We will seed leads into the main async DB
        tenant_id = uuid.UUID(settings.default_tenant_id)
        
        async with MainSessionLocal() as main_db:
            from sqlalchemy import select
            existing_leads = await main_db.execute(select(Lead).limit(1))
            if existing_leads.scalars().first():
                print("Database already seeded. Skipping.")
                return

            print("Seeding Leads into main DB...")
            leads_data = [
                {"name": "Rahul Mehta", "company_name": "GrowFast SaaS", "score": 85, "status": "qualified", "source": "linkedin"},
                {"name": "Priya Shah", "company_name": "FinEdge Capital", "score": 72, "status": "contacted", "source": "hubspot"},
                {"name": "James Liu", "company_name": "TechScale Inc", "score": 68, "status": "new", "source": "widget"},
                {"name": "Sara Al-Amri", "company_name": "Gulf Ventures", "score": 61, "status": "cold", "source": "scraped"},
                {"name": "Tom Eriksson", "company_name": "Nordic SaaS AB", "score": 55, "status": "cold", "source": "hubspot"},
                {"name": "Alice Wonderland", "company_name": "MadHatter Corp", "score": 90, "status": "qualified", "source": "referral"},
                {"name": "Bob Builder", "company_name": "Construction Tech", "score": 45, "status": "new", "source": "widget"},
                {"name": "Charlie Chaplin", "company_name": "Silent Films LLC", "score": 30, "status": "cold", "source": "scraped"},
                {"name": "Diana Prince", "company_name": "Amazonian Ventures", "score": 95, "status": "contacted", "source": "linkedin"},
                {"name": "Eve Smith", "company_name": "Eavesdrop Security", "score": 80, "status": "qualified", "source": "hubspot"}
            ]
            
            leads = []
            for l_data in leads_data:
                lead = Lead(tenant_id=tenant_id, **l_data)
                main_db.add(lead)
                leads.append(lead)
            await main_db.commit()
            
            for lead in leads:
                await main_db.refresh(lead)
            
            print("Seeding Enrichment into main DB...")
            enrichment_data = [
                {"lead_id": leads[0].id, "company_size": "50-200", "funding_stage": "Series B", "tech_stack": ["React", "Python", "AWS"], "pain_points": "Scaling sales team, poor CRM adoption", "recent_news": [{"title": "Raised $15M Series B last month"}], "enrichment_status": "ready"},
                {"lead_id": leads[1].id, "company_size": "10-50", "funding_stage": "Seed", "tech_stack": ["Vue", "Node.js", "GCP"], "pain_points": "Manual reporting, scattered lead data", "recent_news": [{"title": "Launched new fintech product"}], "enrichment_status": "ready"},
                {"lead_id": leads[8].id, "company_size": "1000+", "funding_stage": "Public", "tech_stack": ["Angular", "Java", "Azure"], "pain_points": "Enterprise compliance, siloed data", "recent_news": [{"title": "Expanding to Europe"}], "enrichment_status": "ready"}
            ]
            for e_data in enrichment_data:
                main_db.add(Enrichment(tenant_id=tenant_id, **e_data))
            await main_db.commit()

        print("Seeding Automation Sequences into Lara DB...")
        sequences_data = [
            {"lead_id": str(leads[2].id), "sequence_type": "nurture", "current_step": 2, "status": "active", "last_sent": datetime.utcnow() - timedelta(days=2), "next_send": datetime.utcnow() + timedelta(days=5)},
            {"lead_id": str(leads[3].id), "sequence_type": "reengagement", "current_step": 1, "status": "active", "last_sent": None, "next_send": datetime.utcnow() + timedelta(days=1)},
            {"lead_id": str(leads[4].id), "sequence_type": "breakup", "current_step": 3, "status": "completed", "last_sent": datetime.utcnow() - timedelta(days=10), "next_send": None},
        ]
        for s_data in sequences_data:
            lara_db.add(AutomationSequence(**s_data))
        lara_db.commit()

        print("Seeding Emails into Lara DB...")
        emails_data = [
            {"lead_id": str(leads[0].id), "subject": "Following up on your CRM needs", "body": "Hi Rahul, saw your recent Series B...", "status": "opened", "sent_at": datetime.utcnow() - timedelta(days=3), "opened_at": datetime.utcnow() - timedelta(days=2)},
            {"lead_id": str(leads[1].id), "subject": "SmartBiz intro", "body": "Hi Priya, we help fintechs scale...", "status": "replied", "sent_at": datetime.utcnow() - timedelta(days=5), "opened_at": datetime.utcnow() - timedelta(days=4)},
            {"lead_id": str(leads[2].id), "subject": "Resource: Scaling sales", "body": "James, thought you'd find this useful...", "status": "sent", "sent_at": datetime.utcnow() - timedelta(days=1), "opened_at": None},
        ]
        for em_data in emails_data:
            lara_db.add(Email(**em_data))
        lara_db.commit()

        print("Seeding Reports into Lara DB...")
        reports_data = [
            {"period_start": date.today() - timedelta(days=21), "period_end": date.today() - timedelta(days=15), "new_leads": 45, "qualified": 12, "emails_sent": 150, "open_rate": 0.35, "narrative": "Solid week, driven by the new LinkedIn campaign.", "raw_data": {"campaign": "linkedin_q1"}},
            {"period_start": date.today() - timedelta(days=14), "period_end": date.today() - timedelta(days=8), "new_leads": 52, "qualified": 15, "emails_sent": 180, "open_rate": 0.40, "narrative": "Growth accelerating. High qualification rate from referrals.", "raw_data": {"campaign": "referral_program"}},
            {"period_start": date.today() - timedelta(days=7), "period_end": date.today() - timedelta(days=1), "new_leads": 38, "qualified": 8, "emails_sent": 200, "open_rate": 0.25, "narrative": "Slight dip in new leads, but email volume is up as we focus on nurture.", "raw_data": {"campaign": "nurture"}},
        ]
        for r_data in reports_data:
            lara_db.add(Report(**r_data))
        lara_db.commit()

        print("Seeding Invoices into Lara DB...")
        invoices_data = [
            {"vendor": "AWS", "amount": 1250.00, "status": "paid", "due_date": date.today() - timedelta(days=5), "category": "Infrastructure"},
            {"vendor": "Salesforce", "amount": 3400.00, "status": "overdue", "due_date": date.today() - timedelta(days=2), "category": "Software"},
            {"vendor": "WeWork", "amount": 4500.00, "status": "pending", "due_date": date.today() + timedelta(days=10), "category": "Office"},
            {"vendor": "Google Workspace", "amount": 250.00, "status": "paid", "due_date": date.today() - timedelta(days=15), "category": "Software"},
        ]
        for i_data in invoices_data:
            lara_db.add(Invoice(**i_data))
        lara_db.commit()

        print("Seed data populated successfully!")
    finally:
        lara_db.close()

def seed_db():
    asyncio.run(seed_db_async())

if __name__ == "__main__":
    seed_db()

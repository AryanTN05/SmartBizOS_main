"""
scripts/seed_all.py — populate Postgres with demo data for SmartBiz OS.

Idempotent: re-running is a no-op if seed leads already exist (matched by
deterministic email). Run after `psql -f db/schema.sql` and after enabling
the pgvector extension.

    DATABASE_URL=postgresql+asyncpg://... python -m scripts.seed_all

The lead identities here match the frontend's `seed.js` so the UI lights up
with the same six names whether it's reading from Postgres or falling back to
the bundled seed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as a script (python scripts/seed_all.py) without -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import SessionLocal, engine
from db.models import Lead, Enrichment, ScoreHistory, ActivityLog, Integration, AdminUser
from db.entities import (
    AutomationEvent, AutomationRun, AutomationTemplate, Report, ScraperSource,
)
from config import settings
import bcrypt


TENANT_ID = uuid.UUID(settings.default_tenant_id)

# ─────────────────────────────────────────
# Demo admin — seeded on every run so the team always has a working login.
# Override either field via env in production deploys.
# ─────────────────────────────────────────
DEMO_ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@smartbiz.demo")
DEMO_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "smartbiz-demo")
DEMO_ADMIN_NAME = os.getenv("SEED_ADMIN_NAME", "Demo Admin")


# ─────────────────────────────────────────
# Seed data — mirrors frontend src/modules/*/lib/seed.js
# ─────────────────────────────────────────

LEADS: list[dict] = [
    {
        "key": "lead_priya",
        "name": "Priya Krishnan", "email": "priya@rupee.co", "phone": "+91 99876 12345",
        "company_name": "Rupee.co", "company_domain": "rupee.co",
        "title": "Head of Growth", "linkedin_url": "https://linkedin.com/in/priyakrishnan",
        "status": "qualified", "score": 87, "score_reason": "Hot — high enrichment match + recent funding",
        "source": "Product Hunt", "tags": ["fintech", "warm"],
        "enrichment": {
            "company_size": "11-50", "employee_count": 32, "industry": "Fintech",
            "funding_stage": "Series A", "funding_amount": "$8M",
            "tech_stack": ["React", "Node.js", "Stripe", "AWS"],
            "pain_points": "Manual lead qualification taking 4-6 hours per day for the SDR team.",
            "recent_news": [
                {"date": "2026-04-12", "title": "Rupee.co raises $8M Series A led by Lightspeed"},
                {"date": "2026-03-30", "title": "Rupee.co launches B2B card for Indian SMBs"},
            ],
            "competitor_tools": ["Razorpay", "Open Money"],
        },
        "activity_count": 6,
    },
    {
        "key": "lead_deepak",
        "name": "Deepak Reddy", "email": "deepak@stacklane.io", "phone": "+91 98765 43210",
        "company_name": "Stacklane", "company_domain": "stacklane.io",
        "title": "Founder & CEO", "linkedin_url": "https://linkedin.com/in/deepakreddy",
        "status": "contacted", "score": 72, "score_reason": "ICP fit but slow to engage",
        "source": "LinkedIn scraper", "tags": ["devtools", "cold"],
        "enrichment": {
            "company_size": "11-50", "employee_count": 22, "industry": "Developer Tools",
            "funding_stage": "Seed", "funding_amount": "$3M",
            "tech_stack": ["Go", "Postgres", "Cloud Run", "Vercel"],
            "pain_points": "Inbound is strong but sales-ops is a single-person team drowning in manual triage.",
            "recent_news": [
                {"date": "2026-04-08", "title": "Stacklane releases v2.0 of edge-runtime CLI"},
            ],
            "competitor_tools": ["Vercel", "Netlify"],
        },
        "activity_count": 4,
    },
    {
        "key": "lead_rohan",
        "name": "Rohan Shah", "email": "rohan@lendly.in", "phone": "+91 97654 32109",
        "company_name": "Lendly", "company_domain": "lendly.in",
        "title": "VP Sales", "linkedin_url": "https://linkedin.com/in/rohanshah",
        "status": "qualified", "score": 91, "score_reason": "Hottest deal of the week — biggest forecast",
        "source": "HubSpot", "tags": ["fintech", "lending", "hot"],
        "enrichment": {
            "company_size": "51-200", "employee_count": 87, "industry": "Lending",
            "funding_stage": "Series B", "funding_amount": "$22M",
            "tech_stack": ["Python", "Django", "Postgres", "Snowflake"],
            "pain_points": "Sales cycle is 6-9 months and the team needs better lead scoring to prioritize.",
            "recent_news": [
                {"date": "2026-04-15", "title": "Lendly partners with HDFC for SMB lending"},
                {"date": "2026-04-01", "title": "Lendly hires former Razorpay VP Sales"},
            ],
            "competitor_tools": ["Salesforce", "HubSpot"],
        },
        "activity_count": 8,
    },
    {
        "key": "lead_nisha",
        "name": "Nisha Varma", "email": "nisha@flux.dev", "phone": None,
        "company_name": "Flux", "company_domain": "flux.dev",
        "title": "Co-founder", "linkedin_url": "https://linkedin.com/in/nishavarma",
        "status": "new", "score": 54, "score_reason": "Mid-tier — needs more enrichment",
        "source": "LinkedIn scraper", "tags": ["devtools", "cold"],
        "enrichment": {
            "company_size": "1-10", "employee_count": 7, "industry": "Developer Tools",
            "funding_stage": "Pre-seed", "funding_amount": "$500K",
            "tech_stack": ["TypeScript", "Bun", "Postgres"],
            "pain_points": "Too small for full sales motion; founder doing manual outreach.",
            "recent_news": [],
            "competitor_tools": ["Replit"],
        },
        "activity_count": 2,
    },
    {
        "key": "lead_arjun",
        "name": "Arjun Mehta", "email": "arjun@tidepool.ai", "phone": "+91 99988 77665",
        "company_name": "Tidepool", "company_domain": "tidepool.ai",
        "title": "CTO", "linkedin_url": "https://linkedin.com/in/arjunmehta",
        "status": "contacted", "score": 78, "score_reason": "Engaged on day-2 follow-up",
        "source": "Sheets import", "tags": ["ai", "warm"],
        "enrichment": {
            "company_size": "11-50", "employee_count": 18, "industry": "AI / ML",
            "funding_stage": "Seed", "funding_amount": "$5M",
            "tech_stack": ["Python", "PyTorch", "Modal", "Vercel"],
            "pain_points": "Need to scale outreach to enterprise without losing personalization.",
            "recent_news": [
                {"date": "2026-04-10", "title": "Tidepool launches enterprise AI eval platform"},
            ],
            "competitor_tools": ["Braintrust", "Humanloop"],
        },
        "activity_count": 5,
    },
    {
        "key": "lead_tanya",
        "name": "Tanya Iyer", "email": "tanya@northlight.co", "phone": None,
        "company_name": "Northlight", "company_domain": "northlight.co",
        "title": "Marketing Lead", "linkedin_url": None,
        "status": "lost", "score": 32, "score_reason": "Bounced — not a decision-maker",
        "source": "Lara", "tags": ["enterprise", "cold"],
        "enrichment": {
            "company_size": "201-500", "employee_count": 320, "industry": "SaaS",
            "funding_stage": "Series C", "funding_amount": "$45M",
            "tech_stack": ["Java", "AWS", "Salesforce"],
            "pain_points": "Already using Salesforce — replacement risk too high.",
            "recent_news": [],
            "competitor_tools": ["Salesforce", "Marketo"],
        },
        "activity_count": 1,
    },
    # Additional filler leads so the list looks alive (no enrichment, no activity).
    {"key": "lead_kavya",  "name": "Kavya Menon",  "email": "kavya@brightline.io",  "phone": None, "company_name": "BrightLine",  "company_domain": "brightline.io",  "title": "Product Lead",   "linkedin_url": None, "status": "new",        "score": 48, "score_reason": "Recent inbound", "source": "Tally form",       "tags": ["saas"],     "enrichment": None, "activity_count": 0},
    {"key": "lead_vikram", "name": "Vikram Singh", "email": "vikram@portcove.com",   "phone": None, "company_name": "PortCove",   "company_domain": "portcove.com",   "title": "Founder",        "linkedin_url": None, "status": "new",        "score": 41, "score_reason": "ICP fit",         "source": "Apollo",            "tags": ["logistics"], "enrichment": None, "activity_count": 0},
    {"key": "lead_simran", "name": "Simran Kaur",  "email": "simran@northpath.io",   "phone": None, "company_name": "Northpath",  "company_domain": "northpath.io",   "title": "Head of Ops",    "linkedin_url": None, "status": "contacted",  "score": 65, "score_reason": "Replied to day-2","source": "HubSpot",           "tags": ["hr-tech"],  "enrichment": None, "activity_count": 1},
    {"key": "lead_zaid",   "name": "Zaid Hussain", "email": "zaid@meridianlabs.com", "phone": None, "company_name": "Meridian",   "company_domain": "meridianlabs.com","title": "Engineering Manager","linkedin_url": None, "status": "qualified", "score": 81, "score_reason": "Strong discovery", "source": "LinkedIn scraper", "tags": ["devtools"], "enrichment": None, "activity_count": 3},
]


INTEGRATIONS_SEED = [
    {"type": "hubspot",       "status": "connected", "last_sync_count": 38},
    {"type": "google_sheets", "status": "connected", "last_sync_count": 14},
    {"type": "resend",        "status": "connected", "last_sync_count": 0},
    {"type": "tally",         "status": "available", "last_sync_count": 0},
    {"type": "apollo",        "status": "available", "last_sync_count": 0},
]


ACTIVITY_TEMPLATES = [
    ("lead_created",   "Lead imported from {source}",                             "system"),
    ("enrichment_run", "Enrichment dossier completed (Apollo + LinkedIn)",         "system"),
    ("score_updated",  "AI rescored from {prev_score} → {score}",                 "ai"),
    ("email_sent",     "Outbound: '{subject}'",                                    "automation"),
    ("email_opened",   "Email opened (msg_a8f2cd)",                                "webhook"),
    ("note_added",     "Note: {note}",                                             "admin:demo"),
    ("status_changed", "Stage moved from {prev} → {new}",                          "admin:demo"),
    ("call_logged",    "Discovery call — 22 min, strong signal on pricing",       "admin:demo"),
]


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

async def ensure_pgvector(db: AsyncSession) -> None:
    """Best-effort enable of pgvector. No-op if already installed."""
    try:
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"[seed] pgvector setup skipped: {e}")


async def already_seeded(db: AsyncSession) -> bool:
    result = await db.execute(
        select(Lead).where(Lead.tenant_id == TENANT_ID, Lead.email == "priya@rupee.co").limit(1)
    )
    return result.scalar_one_or_none() is not None


async def upsert_demo_admin(db: AsyncSession) -> None:
    """Idempotent admin upsert — runs every seed regardless of leads state.

    Default credentials live in this file because SmartBiz is a public
    capability-demo, not a multi-tenant SaaS. For production deploys, override
    via SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD env vars before running.
    """
    hash_ = bcrypt.hashpw(DEMO_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()

    existing = (await db.execute(
        select(AdminUser).where(AdminUser.email == DEMO_ADMIN_EMAIL)
    )).scalar_one_or_none()

    if existing:
        existing.bcrypt_hash = hash_
        existing.name = DEMO_ADMIN_NAME
        existing.status = "active"
        action = "updated"
    else:
        db.add(AdminUser(
            email=DEMO_ADMIN_EMAIL,
            bcrypt_hash=hash_,
            name=DEMO_ADMIN_NAME,
            role="admin",
            status="active",
        ))
        action = "created"

    await db.commit()
    print(f"[seed] admin {action}: {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")


def _activity_for(lead: Lead, count: int, source: str, status: str) -> list[ActivityLog]:
    out: list[ActivityLog] = []
    base = datetime.now(timezone.utc) - timedelta(days=14)
    chosen = ACTIVITY_TEMPLATES[:count]
    for i, (action, tmpl, who) in enumerate(chosen):
        msg = (tmpl
               .replace("{source}", source)
               .replace("{prev_score}", str(max(lead.score - 12, 30)))
               .replace("{score}", str(lead.score))
               .replace("{subject}", "Quick idea for " + (lead.company_name or "your company"))
               .replace("{note}", "Mentioned interest in pgvector + Inngest combo")
               .replace("{prev}", "new")
               .replace("{new}", status))
        out.append(
            ActivityLog(
                tenant_id=TENANT_ID,
                lead_id=lead.id,
                action_type=action,
                description=msg,
                metadata_={},
                triggered_by=who,
                created_at=base + timedelta(hours=i * 6),
            )
        )
    return out


async def seed() -> None:
    async with SessionLocal() as db:
        await ensure_pgvector(db)

        # Admin upsert always runs — even if leads are already seeded — so the
        # team gets a working login on a re-run after pulling new code.
        await upsert_demo_admin(db)

        leads_already = await already_seeded(db)
        if leads_already:
            print("[seed] Leads already seeded — skipping leads/enrichment/scoring (delete leads to re-run those).")
            # Still seed automations / scrapers / reports below — they're independent.
            existing_leads = (await db.execute(select(Lead).where(Lead.tenant_id == TENANT_ID))).scalars().all()
            leads_by_key: dict[str, Lead] = {}
            for spec in LEADS:
                match = next((l for l in existing_leads if l.email == spec["email"]), None)
                if match:
                    leads_by_key[spec["key"]] = match
            await seed_templates(db)
            await seed_scrapers(db)
            await seed_runs_and_events(db, leads_by_key)
            await seed_reports(db)
            await db.commit()
            print(f"[seed] Done. Tenant: {TENANT_ID}")
            return

        print("[seed] Inserting leads…")
        leads_by_key: dict[str, Lead] = {}
        for spec in LEADS:
            lead = Lead(
                tenant_id=TENANT_ID,
                name=spec["name"], email=spec["email"], phone=spec.get("phone"),
                company_name=spec.get("company_name"), company_domain=spec.get("company_domain"),
                title=spec.get("title"), linkedin_url=spec.get("linkedin_url"),
                status=spec["status"], score=spec["score"], score_reason=spec.get("score_reason"),
                source=spec["source"], tags=spec.get("tags", []),
            )
            db.add(lead)
            leads_by_key[spec["key"]] = lead
        await db.flush()
        print(f"[seed]   → {len(leads_by_key)} leads")

        print("[seed] Inserting enrichment…")
        enrich_count = 0
        for spec in LEADS:
            if not spec.get("enrichment"):
                continue
            e = spec["enrichment"]
            db.add(Enrichment(
                tenant_id=TENANT_ID, lead_id=leads_by_key[spec["key"]].id,
                company_size=e.get("company_size"), employee_count=e.get("employee_count"),
                industry=e.get("industry"), funding_stage=e.get("funding_stage"),
                funding_amount=e.get("funding_amount"),
                tech_stack=e.get("tech_stack", []), pain_points=e.get("pain_points"),
                recent_news=e.get("recent_news", []),
                competitor_tools=e.get("competitor_tools", []),
                enrichment_status="completed",
                last_enriched_at=datetime.now(timezone.utc) - timedelta(days=2),
                raw_data={"seed": True},
            ))
            enrich_count += 1
        print(f"[seed]   → {enrich_count} enrichment rows")

        print("[seed] Inserting score history…")
        score_count = 0
        for spec in LEADS:
            if not spec.get("enrichment"):
                continue
            lead = leads_by_key[spec["key"]]
            # Two history points: the initial score, and the current.
            db.add(ScoreHistory(
                tenant_id=TENANT_ID, lead_id=lead.id,
                score=max(lead.score - 12, 30),
                reason="Initial AI score from enrichment dossier",
                factors={"company_size": "match", "industry": "match"},
                scored_by="ai",
                scored_at=datetime.now(timezone.utc) - timedelta(days=10),
            ))
            db.add(ScoreHistory(
                tenant_id=TENANT_ID, lead_id=lead.id,
                score=lead.score, reason=lead.score_reason or "Rescored after activity",
                factors={"engagement": "positive", "seniority": "high"},
                scored_by="ai",
                scored_at=datetime.now(timezone.utc) - timedelta(days=1),
            ))
            score_count += 2
        print(f"[seed]   → {score_count} score-history rows")

        print("[seed] Inserting activity log…")
        activity_total = 0
        for spec in LEADS:
            count = spec.get("activity_count", 0)
            if not count:
                continue
            for entry in _activity_for(leads_by_key[spec["key"]], count, spec["source"], spec["status"]):
                db.add(entry)
                activity_total += 1
        print(f"[seed]   → {activity_total} activity rows")

        print("[seed] Inserting integrations…")
        for entry in INTEGRATIONS_SEED:
            db.add(Integration(
                tenant_id=TENANT_ID,
                type=entry["type"], status=entry["status"],
                config={"account_label": entry.get("label")} if entry["status"] == "connected" else {},
                last_sync_count=entry["last_sync_count"],
                last_synced_at=datetime.now(timezone.utc) - timedelta(hours=4) if entry["status"] == "connected" else None,
            ))

        await db.flush()

        await seed_templates(db)
        await seed_scrapers(db)
        await seed_runs_and_events(db, leads_by_key)
        await seed_reports(db)

        await db.commit()
        print(f"[seed] Done. Tenant: {TENANT_ID}")


# ─────────────────────────────────────────
# Templates (idempotent via UNIQUE key)
# ─────────────────────────────────────────

DAY = 86400

TEMPLATES_SEED = [
    {
        "key": "cold_outbound_v1",
        "name": "Cold outbound (5-step with breakup)",
        "description": "Five-touch cold sequence with a breakup. Real send-path swaps Resend for Smartlead/Instantly via the ChannelAdapter registry.",
        "step_count": 5, "channels_used": ["email"],
        "steps": [
            {"order": 0, "kind": "send",   "channel": "email", "wait_duration_seconds": None,    "template_key": "cold_v1_day0",     "branch_on": None,           "description": "Send cold day-0 intro"},
            {"order": 1, "kind": "wait",   "channel": None,    "wait_duration_seconds": 3 * DAY, "template_key": None,                "branch_on": None,           "description": "Wait 3 days for open"},
            {"order": 2, "kind": "branch", "channel": None,    "wait_duration_seconds": None,    "template_key": None,                "branch_on": "email.opened", "description": "Branch on open → follow_up OR breakup"},
            {"order": 3, "kind": "send",   "channel": "email", "wait_duration_seconds": None,    "template_key": "cold_v1_followup",  "branch_on": None,           "description": "Send follow-up value pitch"},
            {"order": 4, "kind": "send",   "channel": "email", "wait_duration_seconds": None,    "template_key": "cold_v1_breakup",   "branch_on": None,           "description": "Send breakup email"},
        ],
        "placeholder_schema": ["lead.first_name", "lead.company", "sender.name"],
        "previews": [
            {"step_order": 0, "template_key": "cold_v1_day0", "channel": "email", "subject": "Quick idea for {company}", "body_html": "<p>Hi {first_name},</p><p>Noticed {company} just raised — we help teams like yours automate sales ops in week one.</p>", "body_markdown": "Hi {first_name}…"},
            {"step_order": 3, "template_key": "cold_v1_followup", "channel": "email", "subject": "Re: Quick idea for {company}", "body_html": "<p>Circling back — here's a one-pager.</p>", "body_markdown": "Circling back…"},
            {"step_order": 4, "template_key": "cold_v1_breakup", "channel": "email", "subject": "Last note from me", "body_html": "<p>{first_name} — last ping from me.</p>", "body_markdown": "{first_name} — last ping…"},
        ],
    },
    {
        "key": "welcome_v1",
        "name": "Welcome (4-step onboarding)",
        "description": "Warm intro after signup or inbound. Lighter cadence, product-first copy, ends with a soft demo ask.",
        "step_count": 4, "channels_used": ["email"],
        "steps": [
            {"order": 0, "kind": "send", "channel": "email", "wait_duration_seconds": None,    "template_key": "welcome_v1_day0", "branch_on": None, "description": "Send welcome email"},
            {"order": 1, "kind": "wait", "channel": None,    "wait_duration_seconds": 2 * DAY, "template_key": None,              "branch_on": None, "description": "Wait 2 days"},
            {"order": 2, "kind": "send", "channel": "email", "wait_duration_seconds": None,    "template_key": "welcome_v1_day2", "branch_on": None, "description": "Product tour follow-up"},
            {"order": 3, "kind": "send", "channel": "email", "wait_duration_seconds": None,    "template_key": "welcome_v1_day5", "branch_on": None, "description": "Soft demo ask"},
        ],
        "placeholder_schema": ["lead.first_name", "lead.company", "sender.name"],
        "previews": [
            {"step_order": 0, "template_key": "welcome_v1_day0", "channel": "email", "subject": "Welcome to SmartBiz, {first_name}", "body_html": "<p>Hey {first_name} — glad you're in.</p>", "body_markdown": "Hey {first_name}…"},
            {"step_order": 2, "template_key": "welcome_v1_day2", "channel": "email", "subject": "Two things most teams miss", "body_html": "<p>A quick tour.</p>", "body_markdown": "A quick tour…"},
            {"step_order": 3, "template_key": "welcome_v1_day5", "channel": "email", "subject": "Want a 15-min walkthrough?", "body_html": "<p>Happy to do a live walkthrough.</p>", "body_markdown": "Happy to do…"},
        ],
    },
    {
        "key": "reengagement_v1",
        "name": "Re-engagement (3-step win-back)",
        "description": "For leads who went quiet for >30 days. Short, no-pitch, curious — last message is a graceful close.",
        "step_count": 3, "channels_used": ["email"],
        "steps": [
            {"order": 0, "kind": "send", "channel": "email", "wait_duration_seconds": None,    "template_key": "reeng_v1_day0",    "branch_on": None, "description": "Curious check-in"},
            {"order": 1, "kind": "wait", "channel": None,    "wait_duration_seconds": 4 * DAY, "template_key": None,               "branch_on": None, "description": "Wait 4 days"},
            {"order": 2, "kind": "send", "channel": "email", "wait_duration_seconds": None,    "template_key": "reeng_v1_breakup", "branch_on": None, "description": "Graceful close"},
        ],
        "placeholder_schema": ["lead.first_name", "lead.company"],
        "previews": [
            {"step_order": 0, "template_key": "reeng_v1_day0", "channel": "email", "subject": "Still on your radar?", "body_html": "<p>Hi {first_name}, anything changed on your end?</p>", "body_markdown": "Hi {first_name}…"},
            {"step_order": 2, "template_key": "reeng_v1_breakup", "channel": "email", "subject": "Closing the loop", "body_html": "<p>Going to close the loop here.</p>", "body_markdown": "Going to close…"},
        ],
    },
]


async def seed_templates(db: AsyncSession) -> None:
    existing = (await db.execute(select(AutomationTemplate.key))).scalars().all()
    skip = set(existing)
    inserted = 0
    for spec in TEMPLATES_SEED:
        if spec["key"] in skip:
            continue
        db.add(AutomationTemplate(
            key=spec["key"], name=spec["name"], description=spec["description"],
            step_count=spec["step_count"], channels_used=spec["channels_used"],
            steps=spec["steps"], placeholder_schema=spec["placeholder_schema"],
            previews=spec["previews"],
        ))
        inserted += 1
    if inserted:
        await db.flush()
    print(f"[seed] Inserting templates… → {inserted} (existed: {len(skip)})")


# ─────────────────────────────────────────
# Scrapers
# ─────────────────────────────────────────

SCRAPERS_SEED = [
    {"source_key": "producthunt",     "name": "Product Hunt (launches)",      "status": "running", "schedule": "daily",     "leads_last_run": 0, "leads_total": 0, "note": "Pulls top-30 daily launches via Atom feed."},
    {"source_key": "hn_show_hn",      "name": "Hacker News (Show HN)",        "status": "running", "schedule": "every 4h",  "leads_last_run": 0, "leads_total": 0, "note": "Show-HN posts via Algolia API — early-stage launches, often founder-reachable."},
    {"source_key": "hn_hiring",       "name": "Hacker News (Who's hiring)",   "status": "running", "schedule": "monthly",   "leads_last_run": 0, "leads_total": 0, "note": "Hiring-intent signal — companies spending on hires are also tooling up."},
    {"source_key": "techcrunch",      "name": "TechCrunch (funding)",         "status": "running", "schedule": "daily",     "leads_last_run": 0, "leads_total": 0, "note": "Startup feed — funding rounds get flagged + scored higher."},
    {"source_key": "github_trending", "name": "GitHub trending",              "status": "running", "schedule": "every 6h",  "leads_last_run": 0, "leads_total": 0, "note": "Recently-pushed repos tagged saas/b2b/crm — founders building in our space."},
    {"source_key": "directories",     "name": "Y Combinator (recent batches)","status": "running", "schedule": "weekly",    "leads_last_run": 0, "leads_total": 0, "note": "Last 2 years of YC batches from the public directory mirror. All currently funded + ICP-fit-ready."},
    {"source_key": "apollo",          "name": "Apollo (B2B contact db)",      "status": "running", "schedule": "every 4h",  "leads_last_run": 0, "leads_total": 0, "note": "Real LinkedIn-data alternative — searches Apollo's 230M+ contact db filtered to ICP titles + headcount. Needs APOLLO_API_KEY (free tier: 100/mo)."},
    {"source_key": "linkedin_seed",   "name": "LinkedIn (seeded fixtures)",   "status": "available", "schedule": "—",       "leads_last_run": 0, "leads_total": 0, "note": "Demo fixtures only. Real LinkedIn scraping is OUT (hiQ + bot detection). Use the Apollo source above for real LinkedIn-derived data."},
    {"source_key": "job_boards",      "name": "Job boards (Greenhouse / Lever / Ashby)", "status": "running", "schedule": "every 6h", "leads_last_run": 0, "leads_total": 0, "note": "Public unauthenticated JSON APIs. Hiring velocity = buying-intent. Seed company tokens via JOB_BOARD_TOKENS env (greenhouse:stripe,lever:figma,...)."},
    {"source_key": "edgar_s1",        "name": "SEC EDGAR (S-1 filings)",       "status": "running", "schedule": "daily",     "leads_last_run": 0, "leads_total": 0, "note": "Pre-IPO companies — highest-budget buying segment. Free no-auth government API. 30-45 day window post-filing is when buying decisions accelerate."},
    {"source_key": "reddit_intent",   "name": "Reddit intent monitor",         "status": "running", "schedule": "every 2h",  "leads_last_run": 0, "leads_total": 0, "note": "r/SaaS / r/devops / r/sysadmin / r/startups — keyword-filtered for explicit buying intent ('looking for X', 'switched from Y'). Different signal class than launches."},
]


async def seed_scrapers(db: AsyncSession) -> None:
    existing = (await db.execute(
        select(ScraperSource.source_key).where(ScraperSource.tenant_id == TENANT_ID)
    )).scalars().all()
    skip = set(existing)
    inserted = 0
    for s in SCRAPERS_SEED:
        if s["source_key"] in skip:
            continue
        last_run = datetime.now(timezone.utc) - timedelta(hours=2) if s["status"] in ("running", "paused") else None
        next_run = (datetime.now(timezone.utc) + timedelta(hours=4)) if s["status"] == "running" else None
        db.add(ScraperSource(
            tenant_id=TENANT_ID, source_key=s["source_key"], name=s["name"],
            status=s["status"], schedule=s["schedule"],
            last_run_at=last_run, next_run_at=next_run,
            leads_last_run=s["leads_last_run"], leads_total=s["leads_total"],
            note=s["note"],
        ))
        inserted += 1
    if inserted:
        await db.flush()
    print(f"[seed] Inserting scrapers… → {inserted} (existed: {len(skip)})")


# ─────────────────────────────────────────
# Historical automation runs + per-step events for the timeline UI.
# ─────────────────────────────────────────

RUNS_SEED = [
    # (lead_key, template_key, status, started_days_ago, current_step, completed_offset_hours)
    ("lead_priya",  "cold_outbound_v1",   "running",   2.5, "wait_open",     None),
    ("lead_deepak", "cold_outbound_v1",   "running",   3,   "send_day0",     None),
    ("lead_rohan",  "welcome_v1",         "completed", 5,   "wait_open",     -24),
    ("lead_nisha",  "reengagement_v1",    "failed",    5,   "send_day0",     -12),
    ("lead_arjun",  "welcome_v1",         "paused",    6,   "wait_3_days",   None),
    ("lead_tanya",  "cold_outbound_v1",   "cancelled", 8,   "send_day0",     -24),
]


async def seed_runs_and_events(db: AsyncSession, leads_by_key: dict[str, Lead]) -> None:
    existing_count = (await db.execute(
        select(func.count(AutomationRun.id))
        .where(AutomationRun.tenant_id == TENANT_ID)
    )).scalar()
    if existing_count and existing_count > 0:
        print(f"[seed] Automation runs already present ({existing_count}) — skipping")
        return

    templates = {t.key: t for t in (await db.execute(select(AutomationTemplate))).scalars().all()}
    now = datetime.now(timezone.utc)
    inserted = 0
    skipped = 0
    for lead_key, tpl_key, status, days_ago, step, complete_off in RUNS_SEED:
        lead = leads_by_key.get(lead_key)
        tpl = templates.get(tpl_key)
        if not lead or not tpl:
            skipped += 1
            continue
        started = now - timedelta(days=days_ago)
        completed = (started + timedelta(hours=24 + (complete_off or 0))) if complete_off is not None else None
        run = AutomationRun(
            tenant_id=TENANT_ID, lead_id=lead.id, template_id=tpl.id,
            template_key=tpl.key, status=status,
            current_step_name=step, started_at=started,
            completed_at=completed, created_by="admin:seed",
        )
        db.add(run)
        await db.flush()
        # Generate a small set of events that match the template's progress.
        evs = [
            {"step": "load_lead",        "ch": None,    "out": "wait_completed", "off": 1,    "p": {"snapshot": {"name": lead.name, "email": lead.email}}},
            {"step": "render_email_day0","ch": "email", "out": "rendered",       "off": 3,    "p": {"template_key": f"{tpl_key}_day0", "tokens": 312}},
            {"step": "send_day0",        "ch": "email", "out": "sent",           "off": 5,    "p": {"provider": "resend", "message_id": f"msg_{lead_key}_day0"}},
        ]
        if status in ("completed", "running"):
            evs.append({"step": "wait_3_days", "ch": None,    "out": "wait_completed", "off": 3 * 86400, "p": {"duration": "3d"}})
        if status == "completed":
            evs.append({"step": "wait_open",   "ch": "email", "out": "opened",        "off": 3 * 86400 + 3600, "p": {"detail": "email.opened"}})
        if status == "failed":
            evs.append({"step": "send_day0",   "ch": "email", "out": "failed",        "off": 7,    "p": {"error": "resend 401"}})
        for ev in evs:
            db.add(AutomationEvent(
                run_id=run.id, step_name=ev["step"], channel=ev["ch"],
                outcome=ev["out"], occurred_at=started + timedelta(seconds=ev["off"]),
                payload=ev["p"],
            ))
        inserted += 1
    await db.flush()
    print(f"[seed] Inserting automation runs… → {inserted} (skipped {skipped} for missing leads/templates)")


# ─────────────────────────────────────────
# Historical reports — a few weeks back so the list/detail/compare pages
# have content even before the user generates a fresh one.
# ─────────────────────────────────────────

async def seed_reports(db: AsyncSession) -> None:
    existing = (await db.execute(
        select(func.count(Report.id)).where(Report.tenant_id == TENANT_ID)
    )).scalar()
    if existing and existing > 0:
        print(f"[seed] Reports already present ({existing}) — skipping")
        return

    now = datetime.now(timezone.utc)
    samples = [
        {"weeks_ago": 1, "leads": 89, "hot": 16, "rate": 0.084, "headline": "A quiet week. Three hot signals."},
        {"weeks_ago": 2, "leads": 72, "hot": 13, "rate": 0.072, "headline": "Steady cadence, fewer surprises."},
        {"weeks_ago": 3, "leads": 68, "hot": 12, "rate": 0.078, "headline": "Re-engagement template paid off."},
        {"weeks_ago": 4, "leads": 58, "hot": 10, "rate": 0.061, "headline": "Slow start; closed strong."},
    ]
    for s in samples:
        end = now - timedelta(days=(s["weeks_ago"] - 1) * 7)
        start = end - timedelta(days=7)
        stats = {
            "leads": {"new_leads_count": s["leads"], "hot_count": s["hot"],
                      "median_score": 54 + s["weeks_ago"],
                      "sources": [
                          {"source": "manual", "count": int(s["leads"] * 0.42)},
                          {"source": "scraper:linkedin", "count": int(s["leads"] * 0.20)},
                          {"source": "scraper:producthunt", "count": int(s["leads"] * 0.15)},
                          {"source": "webhook", "count": int(s["leads"] * 0.10)},
                      ],
                      "history": [42, 51, 48, 63, 58, 72, 68, s["leads"]]},
            "automations": {"reply_rate": s["rate"], "runs_total": 6 + s["weeks_ago"], "runs_failed": 1 if s["weeks_ago"] == 4 else 0},
            "forecast": None,
        }
        db.add(Report(
            tenant_id=TENANT_ID, kind="weekly",
            period_start=start, period_end=end,
            headline=s["headline"],
            narrative=f"Week of {start.date()} → {end.date()}: {s['leads']} new leads ({s['hot']} hot). Reply rate {s['rate']*100:.1f}%.",
            stats=stats, prompt_version="v1", model="seed",
            generated_at=end + timedelta(hours=33),
            has_embedding=False,
        ))
    await db.flush()
    print(f"[seed] Inserting reports… → {len(samples)}")


if __name__ == "__main__":
    if "DATABASE_URL" not in os.environ:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(2)
    asyncio.run(seed())

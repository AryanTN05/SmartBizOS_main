"""Gold Batch Seed Script — populate the DB with 10 enriched leads.

Usage (from backend/):
    python -m enrichment_engine.scripts.seed_gold_batch

Requires: .env at backend/ with DATABASE_URL, GOOGLE_API_KEY, FIRECRAWL_API_KEY.
"""

import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Run from backend/ so `config`, `db`, `enrichment_engine` resolve correctly.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from config import settings  # noqa: E402
from db.connection import SessionLocal, engine  # noqa: E402
from db.models import ActivityLog, Enrichment, Lead, ScoreHistory  # noqa: E402
from sqlalchemy import text, update  # noqa: E402

from enrichment_engine.agents.enrichment import enrich_lead, score_lead  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)s │ %(message)s",
)
logger = logging.getLogger(__name__)


# ── Target prospects ────────────────────────────────────────────────────────
# DB uses `company_domain` (no separate company/website columns).
SEED_LEADS = [
    {"name": "Sarah Chen", "company_domain": "runwayml.com", "email": "contact@runwayml.com"},
    {"name": "Alex Graveley", "company_domain": "pieces.app", "email": "hello@pieces.app"},
    {"name": "Matt Shumer", "company_domain": "hyperwriteai.com", "email": "info@hyperwriteai.com"},
    {"name": "Harrison Chase", "company_domain": "langchain.com", "email": "contact@langchain.com"},
    {"name": "Aman Chadha", "company_domain": "ai21.com", "email": "info@ai21.com"},
    {"name": "Amjad Masad", "company_domain": "replit.com", "email": "contact@replit.com"},
    {"name": "Jerry Liu", "company_domain": "llamaindex.ai", "email": "contact@llamaindex.ai"},
    {"name": "Clement Delangue", "company_domain": "huggingface.co", "email": "info@huggingface.co"},
    {"name": "Emmet Shear", "company_domain": "twitch.tv", "email": "press@twitch.tv"},
    {"name": "Yann LeCun", "company_domain": "meta.com", "email": "press@meta.com"},
]


async def _verify_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("✅ Database connection verified")


def _derive_company_name(domain: str) -> str:
    dom = domain.strip().lower()
    for p in ("http://", "https://", "www."):
        if dom.startswith(p):
            dom = dom[len(p):]
    return dom.split("/")[0].split(".")[0]


async def seed_one(lead_data: dict, tenant_id: uuid.UUID) -> dict:
    company = _derive_company_name(lead_data["company_domain"])
    website = f"https://{lead_data['company_domain']}"

    # 1. Insert lead
    async with SessionLocal() as session:
        lead = Lead(
            tenant_id=tenant_id,
            name=lead_data["name"],
            email=lead_data.get("email"),
            company_domain=lead_data["company_domain"],
            source="manual",
            notes=lead_data.get("notes"),
            status="new",
            tags=["gold-batch", "seed"],
        )
        session.add(lead)
        await session.flush()
        lead_id = lead.id
        session.add(ActivityLog(
            lead_id=lead_id,
            tenant_id=tenant_id,
            action_type="lead_created",
            description="Seeded via gold batch script",
            triggered_by="seed_script",
        ))
        await session.commit()
    logger.info(f"   ✅ Lead created: {lead_id}")

    # 2. Enrichment
    logger.info("   🤖 Running enrichment agent…")
    enrichment_result = await enrich_lead(
        name=lead_data["name"], company=company, website=website
    )
    enrichment_dict = enrichment_result.model_dump()

    async with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        session.add(Enrichment(
            lead_id=lead_id,
            tenant_id=tenant_id,
            company_size=enrichment_dict.get("company_size"),
            employee_count=enrichment_dict.get("employee_count"),
            industry=enrichment_dict.get("industry"),
            funding_stage=enrichment_dict.get("funding_stage"),
            funding_amount=enrichment_dict.get("funding_amount"),
            tech_stack=enrichment_dict.get("tech_stack", []) or [],
            pain_points=enrichment_dict.get("pain_points"),
            recent_news=enrichment_dict.get("recent_news", []) or [],
            competitor_tools=enrichment_dict.get("competitor_tools", []) or [],
            enrichment_status="completed",
            last_enriched_at=now,
            raw_data=enrichment_dict,
        ))
        session.add(ActivityLog(
            lead_id=lead_id,
            tenant_id=tenant_id,
            action_type="enrichment_completed",
            description="AI enrichment completed via seed script",
            triggered_by="seed_script",
        ))
        await session.commit()
    logger.info("   ✅ Enrichment saved")

    # 3. Scoring
    logger.info("   📊 Scoring lead…")
    score_result = await score_lead(
        name=lead_data["name"], company=company, enrichment_data=enrichment_result
    )
    factors = score_result.factors.model_dump() if hasattr(score_result.factors, "model_dump") else score_result.factors

    async with SessionLocal() as session:
        session.add(ScoreHistory(
            lead_id=lead_id,
            tenant_id=tenant_id,
            score=score_result.score,
            reason=score_result.reason,
            factors=factors,
            scored_by="ai",
        ))
        await session.execute(
            update(Lead)
            .where(Lead.id == lead_id)
            .values(
                score=score_result.score,
                score_reason=score_result.reason,
                last_activity=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    logger.info(f"   ✅ Score: {score_result.score}/100 — {score_result.reason}")
    return {
        "name": lead_data["name"],
        "company": company,
        "score": score_result.score,
        "industry": enrichment_dict.get("industry"),
    }


async def main() -> None:
    await _verify_db()
    tenant_id = uuid.UUID(settings.default_tenant_id)
    results: list[dict] = []

    for i, lead_data in enumerate(SEED_LEADS, 1):
        logger.info(f"\n{'─' * 50}")
        logger.info(f"[{i}/{len(SEED_LEADS)}] {lead_data['name']} @ {lead_data['company_domain']}")
        logger.info(f"{'─' * 50}")
        try:
            results.append(await seed_one(lead_data, tenant_id))
        except Exception as exc:
            logger.error(f"   ❌ Failed: {exc}", exc_info=True)
            results.append({
                "name": lead_data["name"],
                "company": lead_data["company_domain"],
                "score": 0,
                "industry": None,
                "error": str(exc),
            })

    logger.info("\n" + "═" * 60)
    logger.info("SEED BATCH SUMMARY")
    logger.info("═" * 60)
    for r in results:
        if "error" in r:
            logger.info(f"  ❌ {r['name']:<25} @ {r['company']:<20} — {r['error']}")
        else:
            logger.info(f"  ✅ {r['name']:<25} @ {r['company']:<20} — {r['score']}/100 ({r['industry']})")


if __name__ == "__main__":
    asyncio.run(main())

"""
Workflow for lead enrichment — runs as an async background task.

Responsibilities:
  1. Fetch the lead from DB (orchestrator schema).
  2. Mark enrichment as in-progress.
  3. Run the Gemini enrichment agent.
  4. Persist the enrichment result.
  5. Score the lead and persist to score_history + leads.score.
  6. Emit an activity_log entry.

This module uses the orchestrator's SQLAlchemy session factory and models —
the enrichment_engine no longer owns its own DB layer.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update

from db.connection import SessionLocal
from db.models import Lead, Enrichment, ScoreHistory, ActivityLog
from enrichment_engine.agents.enrichment import (
    EnrichmentResult,
    enrich_lead,
    score_lead,
)

logger = logging.getLogger(__name__)


# ── Lead field derivation ───────────────────────────────────────────────────

def _derive_company_name(lead: Lead) -> str:
    """Best-effort company name for prompt context.

    Prefers `company_name`; falls back to a derivation from `company_domain`,
    and finally to the lead's personal name.
    """
    if lead.company_name:
        return lead.company_name
    if lead.company_domain:
        dom = lead.company_domain.strip().lower()
        for p in ("http://", "https://", "www."):
            if dom.startswith(p):
                dom = dom[len(p):]
        head = dom.split("/")[0].split(".")[0]
        if head:
            return head
    return lead.name


def _derive_website(lead: Lead) -> Optional[str]:
    """Return a canonical https:// URL for the company domain, or None."""
    if not lead.company_domain:
        return None
    dom = lead.company_domain.strip()
    if dom.startswith(("http://", "https://")):
        return dom
    return f"https://{dom}"


# ── DB helpers ──────────────────────────────────────────────────────────────

async def _fetch_lead(lead_id: str, tenant_id: str) -> dict:
    """Fetch the lead row and return a dict the agent can consume."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Lead).where(
                Lead.id == uuid.UUID(lead_id),
                Lead.tenant_id == uuid.UUID(tenant_id),
                Lead.deleted_at == None
            )
        )
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")
        return {
            "id": str(lead.id),
            "tenant_id": str(lead.tenant_id),
            "name": lead.name,
            "company": _derive_company_name(lead),
            "website": _derive_website(lead),
            "email": lead.email,
        }


async def _mark_enriching(lead_id: str, tenant_id: str) -> None:
    """Upsert an enrichment row into 'in_progress' state."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Enrichment).where(Enrichment.lead_id == uuid.UUID(lead_id))
        )
        enrichment = result.scalar_one_or_none()
        if enrichment:
            enrichment.enrichment_status = "in_progress"
        else:
            session.add(Enrichment(
                lead_id=uuid.UUID(lead_id),
                tenant_id=uuid.UUID(tenant_id),
                enrichment_status="in_progress",
            ))
        await session.commit()


async def _run_enrichment(lead_data: dict) -> dict:
    """Run the Gemini enrichment agent."""
    result = await enrich_lead(
        name=lead_data["name"],
        company=lead_data["company"],
        website=lead_data.get("website"),
    )
    return result.model_dump()


async def _save_enrichment(lead_id: str, tenant_id: str, enrichment_data: dict) -> None:
    """Persist enrichment to DB. Rich fields land in raw_data JSONB."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Enrichment).where(Enrichment.lead_id == uuid.UUID(lead_id))
        )
        enrichment = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        recent_news = enrichment_data.get("recent_news", []) or []

        if enrichment:
            enrichment.company_size = enrichment_data.get("company_size")
            enrichment.employee_count = enrichment_data.get("employee_count")
            enrichment.industry = enrichment_data.get("industry")
            enrichment.funding_stage = enrichment_data.get("funding_stage")
            enrichment.funding_amount = enrichment_data.get("funding_amount")
            enrichment.tech_stack = enrichment_data.get("tech_stack", []) or []
            enrichment.pain_points = enrichment_data.get("pain_points")
            enrichment.recent_news = recent_news
            enrichment.competitor_tools = enrichment_data.get("competitor_tools", []) or []
            enrichment.enrichment_status = "completed"
            enrichment.last_enriched_at = now
            enrichment.raw_data = enrichment_data
        else:
            session.add(Enrichment(
                lead_id=uuid.UUID(lead_id),
                tenant_id=uuid.UUID(tenant_id),
                company_size=enrichment_data.get("company_size"),
                employee_count=enrichment_data.get("employee_count"),
                industry=enrichment_data.get("industry"),
                funding_stage=enrichment_data.get("funding_stage"),
                funding_amount=enrichment_data.get("funding_amount"),
                tech_stack=enrichment_data.get("tech_stack", []) or [],
                pain_points=enrichment_data.get("pain_points"),
                recent_news=recent_news,
                competitor_tools=enrichment_data.get("competitor_tools", []) or [],
                enrichment_status="completed",
                last_enriched_at=now,
                raw_data=enrichment_data,
            ))
        await session.commit()


async def _score(lead_data: dict, enrichment_data: dict) -> dict:
    """Run the scoring agent off a hydrated EnrichmentResult."""
    enrichment = EnrichmentResult.model_validate(enrichment_data)
    result = await score_lead(
        name=lead_data["name"],
        company=lead_data["company"],
        enrichment_data=enrichment,
    )
    return result.model_dump()


async def _save_score(lead_id: str, tenant_id: str, score_data: dict) -> None:
    """Insert a score_history row and update leads.score/score_reason."""
    async with SessionLocal() as session:
        factors = score_data.get("factors", {}) or {}
        if hasattr(factors, "model_dump"):
            factors = factors.model_dump()

        session.add(ScoreHistory(
            lead_id=uuid.UUID(lead_id),
            tenant_id=uuid.UUID(tenant_id),
            score=score_data["score"],
            reason=score_data.get("reason"),
            factors=factors,
            scored_by="ai",
        ))
        await session.execute(
            update(Lead)
            .where(Lead.id == uuid.UUID(lead_id))
            .values(
                score=score_data["score"],
                score_reason=score_data.get("reason"),
                last_activity=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _log_activity(
    lead_id: str,
    tenant_id: str,
    action_type: str,
    description: str,
    metadata: Optional[dict] = None,
) -> None:
    async with SessionLocal() as session:
        session.add(ActivityLog(
            lead_id=uuid.UUID(lead_id),
            tenant_id=uuid.UUID(tenant_id),
            action_type=action_type,
            description=description,
            metadata_=metadata or {},
            triggered_by="system",
        ))
        await session.commit()


async def _mark_failed(lead_id: str) -> None:
    """Best-effort: flip the enrichment row to 'failed' so the UI can recover."""
    try:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Enrichment).where(Enrichment.lead_id == uuid.UUID(lead_id))
            )
            enrichment = result.scalar_one_or_none()
            if enrichment:
                enrichment.enrichment_status = "failed"
                await session.commit()
    except Exception as cleanup_err:
        logger.warning(f"Could not mark enrichment failed for {lead_id}: {cleanup_err}")


# ── Public Pipeline ─────────────────────────────────────────────────────────

async def enrich_lead_pipeline(lead_id: str, tenant_id: str) -> dict:
    """Run the full enrichment + scoring pipeline for a single lead.

    This is the callable `backend/routers/enrichment.py` hands to
    FastAPI's BackgroundTasks. All DB access uses the orchestrator's session
    factory so there is a single pool, single config, single source of truth.
    """
    try:
        lead_data = await _fetch_lead(lead_id, tenant_id)
        resolved_tenant = tenant_id

        await _mark_enriching(lead_id, resolved_tenant)

        enrichment_data = await _run_enrichment(lead_data)
        await _save_enrichment(lead_id, resolved_tenant, enrichment_data)
        await _log_activity(
            lead_id, resolved_tenant,
            action_type="enrichment_completed",
            description=f"Enrichment completed for {lead_data['company']}",
            metadata={"source": "enrichment_engine"},
        )

        score_data = await _score(lead_data, enrichment_data)
        await _save_score(lead_id, resolved_tenant, score_data)
        await _log_activity(
            lead_id, resolved_tenant,
            action_type="score_changed",
            description=f"AI scored lead {score_data['score']}/100",
            metadata={"score": score_data["score"], "reason": score_data.get("reason")},
        )

        return {
            "lead_id": lead_id,
            "status": "enriched",
            "score": score_data["score"],
            "reason": score_data.get("reason", ""),
        }
    except Exception as e:
        logger.error(f"Failed enrichment pipeline for {lead_id}: {e}", exc_info=True)
        await _mark_failed(lead_id)
        raise

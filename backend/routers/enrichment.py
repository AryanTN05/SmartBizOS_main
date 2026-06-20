"""Enrichment + scoring endpoints — the M2 AI Sales Intelligence surface.

Spec: docs/specs/api-contracts/m2-sales-intel.md

Implements:
  - POST  /api/leads/{id}/enrich         (202, async background task)
  - GET   /api/leads/{id}/enrichment     (read enrichment dossier)
  - POST  /api/leads/{id}/rescore        (synchronous scoring)
  - GET   /api/leads/{id}/score/history  (most-recent score history)

This is the ONLY place outside backend/enrichment_engine/ that imports from
the enrichment_engine package.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth.dependencies import require_admin
from db.connection import get_db
from db.models import ActivityLog, Enrichment, Lead, ScoreHistory
from enrichment_engine.agents.enrichment import EnrichmentResult, score_lead
from enrichment_engine.workflows.lead_pipeline import enrich_lead_pipeline
from routers.leads import get_tenant_id

router = APIRouter(
    prefix="/api/leads",
    tags=["Enrichment & Scoring"],
    # Enrichment hits Firecrawl + LLM (real $ per call). Admin-only.
    dependencies=[Depends(require_admin)],
)


# ── Freshness windows (per M2 spec) ──────────────────────────────────────────

ENRICH_CACHE_SECONDS = 7 * 24 * 3600   # 7 days
RESCORE_CACHE_SECONDS = 48 * 3600      # 48 hours


# ── Request / Response models ────────────────────────────────────────────────

class EnrichTriggerRequest(BaseModel):
    """Optional body for POST /api/leads/{id}/enrich.

    Matches the spec's EnrichTriggerRequest dataclass.
    """
    providers: Optional[List[str]] = None
    force: bool = False


class EnrichTriggerResponse(BaseModel):
    """Matches the spec's EnrichTriggerResponse dataclass."""
    lead_id: str
    job_id: str
    status: str  # "queued" | "already_fresh"
    existing_enrichment_age_seconds: Optional[int] = None


class EnrichmentDataResponse(BaseModel):
    """Spec-shape projection of the `enrichment` row.

    Richer internal fields (hiring_signals, leadership, expansion_signals, etc.)
    remain inside `raw_data` JSONB and are not exposed on this projection —
    they're available to the scoring agent but the public contract stays narrow.
    """
    id: str
    lead_id: str
    company_size: Optional[str] = None
    employee_count: Optional[int] = None
    industry: Optional[str] = None
    funding_stage: Optional[str] = None
    funding_amount: Optional[str] = None
    tech_stack: List[str] = Field(default_factory=list)
    pain_points: Optional[str] = None
    recent_news: List[Any] = Field(default_factory=list)
    competitor_tools: List[str] = Field(default_factory=list)
    enrichment_status: Optional[str] = None
    last_enriched_at: Optional[datetime] = None


class RescoreRequest(BaseModel):
    """Optional body for POST /api/leads/{id}/rescore."""
    force: bool = False


class ScoreResponse(BaseModel):
    """Projection of a single score_history row — spec's Score dataclass shape."""
    id: str
    lead_id: str
    score: int
    reason: Optional[str] = None
    factors: Optional[Any] = None
    scored_by: str
    scored_at: Optional[datetime] = None


class RescoreResponse(BaseModel):
    """Matches the spec's RescoreResponse dataclass."""
    score: ScoreResponse
    was_cached: bool


class ScoreHistoryResponse(BaseModel):
    """List envelope for score history."""
    items: List[ScoreResponse]
    total: int


# ── Internal helpers ─────────────────────────────────────────────────────────

async def _get_lead_or_404(
    session: AsyncSession, lead_id: UUID, tenant_id: UUID
) -> Lead:
    result = await session.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.tenant_id == tenant_id,
            Lead.deleted_at == None
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


async def _get_enrichment(
    session: AsyncSession, lead_id: UUID
) -> Optional[Enrichment]:
    result = await session.execute(
        select(Enrichment).where(Enrichment.lead_id == lead_id)
    )
    return result.scalar_one_or_none()


def _score_to_response(row: ScoreHistory) -> ScoreResponse:
    return ScoreResponse(
        id=str(row.id),
        lead_id=str(row.lead_id),
        score=row.score,
        reason=row.reason,
        factors=row.factors,
        scored_by=row.scored_by or "ai",
        scored_at=row.scored_at,
    )


def _derive_company_name(lead: Lead) -> str:
    """Best-effort company name for scoring prompt context.

    Prefers the explicit `company_name` column; falls back to a derivation
    from `company_domain`, and finally to the lead's personal name.
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


# ── POST /api/leads/{id}/enrich ─────────────────────────────────────────────

@router.post(
    "/{lead_id}/enrich",
    response_model=EnrichTriggerResponse,
    status_code=202,
)
async def trigger_enrichment(
    lead_id: UUID,
    background_tasks: BackgroundTasks,
    body: Optional[EnrichTriggerRequest] = Body(default=None),
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an async enrichment run.

    Spec behavior:
      - 202 on success with a job_id (opaque uuid; Inngest not yet wired).
      - If `force=false` and an enrichment row is <7d old, returns status
        `already_fresh` without re-queueing.
      - Otherwise schedules `enrich_lead_pipeline` as a BackgroundTask.
    """
    payload = body or EnrichTriggerRequest()
    await _get_lead_or_404(db, lead_id, tenant_id)
    existing = await _get_enrichment(db, lead_id)
    job_id = str(uuid4())

    if (
        existing
        and existing.last_enriched_at
        and existing.enrichment_status == "completed"
        and not payload.force
    ):
        age_seconds = int(
            (datetime.now(timezone.utc) - existing.last_enriched_at).total_seconds()
        )
        if age_seconds < ENRICH_CACHE_SECONDS:
            return EnrichTriggerResponse(
                lead_id=str(lead_id),
                job_id=job_id,
                status="already_fresh",
                existing_enrichment_age_seconds=age_seconds,
            )

    background_tasks.add_task(
        enrich_lead_pipeline, str(lead_id), str(tenant_id)
    )

    return EnrichTriggerResponse(
        lead_id=str(lead_id),
        job_id=job_id,
        status="queued",
        existing_enrichment_age_seconds=None,
    )


# ── GET /api/leads/{id}/enrichment ──────────────────────────────────────────

@router.get(
    "/{lead_id}/enrichment",
    response_model=EnrichmentDataResponse,
)
async def get_enrichment(
    lead_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the current enrichment dossier for a lead."""
    await _get_lead_or_404(db, lead_id, tenant_id)
    enrichment = await _get_enrichment(db, lead_id)
    if not enrichment:
        raise HTTPException(
            status_code=404, detail="No enrichment found for this lead"
        )

    return EnrichmentDataResponse(
        id=str(enrichment.id),
        lead_id=str(enrichment.lead_id),
        company_size=enrichment.company_size,
        employee_count=enrichment.employee_count,
        industry=enrichment.industry,
        funding_stage=enrichment.funding_stage,
        funding_amount=enrichment.funding_amount,
        tech_stack=list(enrichment.tech_stack or []),
        pain_points=enrichment.pain_points,
        recent_news=list(enrichment.recent_news or []),
        competitor_tools=list(enrichment.competitor_tools or []),
        enrichment_status=enrichment.enrichment_status,
        last_enriched_at=enrichment.last_enriched_at,
    )


# ── POST /api/leads/{id}/rescore ────────────────────────────────────────────

@router.post(
    "/{lead_id}/rescore",
    response_model=RescoreResponse,
)
async def rescore_lead(
    lead_id: UUID,
    body: Optional[RescoreRequest] = Body(default=None),
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Synchronously re-score a lead against its existing enrichment.

    Spec behavior:
      - 409 with `reason=needs_enrichment_first` if no enrichment row yet.
      - If `force=false` and the latest score is <48h old, returns it with
        `was_cached=true`.
      - Otherwise runs the scoring agent, persists a new score_history row,
        updates leads.score/score_reason, emits an activity_log entry.
        
    Note: If the `enrichment.raw_data` was written by an older schema and fails
    validation against `EnrichmentResult`, this will hard-fail with a 502. In that
    case, `force=true` will not rescue it. A full re-enrich via `/enrich` with `force=true`
    is required.
    """
    payload = body or RescoreRequest()
    lead = await _get_lead_or_404(db, lead_id, tenant_id)
    enrichment = await _get_enrichment(db, lead_id)

    if not enrichment or not enrichment.raw_data:
        raise HTTPException(
            status_code=409,
            detail={"reason": "needs_enrichment_first"},
        )

    # 48h cache
    if not payload.force:
        latest_result = await db.execute(
            select(ScoreHistory)
            .where(ScoreHistory.lead_id == lead_id)
            .order_by(desc(ScoreHistory.scored_at))
            .limit(1)
        )
        last_score = latest_result.scalar_one_or_none()
        if last_score and last_score.scored_at:
            age = (
                datetime.now(timezone.utc) - last_score.scored_at
            ).total_seconds()
            if age < RESCORE_CACHE_SECONDS:
                return RescoreResponse(
                    score=_score_to_response(last_score),
                    was_cached=True,
                )

    # Hydrate the rich EnrichmentResult so the scoring agent sees full context.
    try:
        enrichment_result = EnrichmentResult.model_validate(enrichment.raw_data)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "reason": "enrichment_data_unparseable",
                "message": str(exc),
            },
        )

    try:
        score_out = await score_lead(
            name=lead.name,
            company=_derive_company_name(lead),
            enrichment_data=enrichment_result,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"reason": "upstream_failed", "message": str(exc)},
        )

    factors = (
        score_out.factors.model_dump()
        if hasattr(score_out.factors, "model_dump")
        else score_out.factors
    )

    new_score = ScoreHistory(
        tenant_id=tenant_id,
        lead_id=lead_id,
        score=score_out.score,
        reason=score_out.reason,
        factors=factors,
        scored_by="ai",
    )
    db.add(new_score)

    lead.score = score_out.score
    lead.score_reason = score_out.reason
    lead.last_activity = datetime.now(timezone.utc)

    db.add(ActivityLog(
        tenant_id=tenant_id,
        lead_id=lead_id,
        action_type="score_changed",
        description=f"Re-scored: {score_out.score}/100",
        metadata_={
            "score": score_out.score,
            "reason": score_out.reason,
            "forced": payload.force,
        },
        triggered_by="admin",
    ))

    await db.commit()
    await db.refresh(new_score)

    return RescoreResponse(
        score=_score_to_response(new_score),
        was_cached=False,
    )


# ── GET /api/leads/{id}/score/history ───────────────────────────────────────

@router.get(
    "/{lead_id}/score/history",
    response_model=ScoreHistoryResponse,
)
async def get_score_history(
    lead_id: UUID,
    limit: int = Query(default=25, ge=1, le=100),
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent score_history entries for a lead (newest first)."""
    await _get_lead_or_404(db, lead_id, tenant_id)

    result = await db.execute(
        select(ScoreHistory)
        .where(
            ScoreHistory.lead_id == lead_id,
            ScoreHistory.tenant_id == tenant_id,
        )
        .order_by(desc(ScoreHistory.scored_at))
        .limit(limit)
    )
    rows = result.scalars().all()

    total_result = await db.execute(
        select(func.count())
        .select_from(ScoreHistory)
        .where(
            ScoreHistory.lead_id == lead_id,
            ScoreHistory.tenant_id == tenant_id,
        )
    )
    total = total_result.scalar() or 0

    return ScoreHistoryResponse(
        items=[_score_to_response(r) for r in rows],
        total=total,
    )

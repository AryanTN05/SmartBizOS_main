import csv
import io
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone

from db.connection import get_db
from db.models import Lead, ActivityLog
from db.entities.admin_user import AdminUser
from db.entities import ScraperResult
from auth.dependencies import require_admin
import schemas

from config import settings

router = APIRouter(prefix="/api/leads", tags=["Leads"])


def _score_category(value: int | None) -> str | None:
    """Map a 0-100 score to the hot/warm/cool/cold buckets the UI renders."""
    if value is None:
        return None
    if value >= 80:
        return "hot"
    if value >= 60:
        return "warm"
    if value >= 40:
        return "cool"
    return "cold"


def _lead_to_dict(lead: Lead) -> dict:
    """
    Shape leads the way the frontend kit expects:
      - `company` mirrors `company_name`
      - `score` is an object {value, category, reasons, rubric_version, model}
        rather than a bare int, so the score-explainer card can render badges
        without a separate roundtrip.

    Keeps `company_name` and `score_reason` so legacy callers don't break.
    """
    score_value = lead.score
    reasons = []
    if lead.score_reason:
        reasons.append({"r": lead.score_reason, "w": None})
    return {
        "id": str(lead.id),
        "tenant_id": str(lead.tenant_id),
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "company": lead.company_name,            # frontend-friendly alias
        "company_name": lead.company_name,       # legacy
        "company_domain": lead.company_domain,
        "title": lead.title,
        "linkedin_url": lead.linkedin_url,
        "status": lead.status,
        "score": {
            "value": score_value,
            "category": _score_category(score_value),
            "reasons": reasons,
            "rubric_version": "v1",
            "model": "ai",
        },
        "score_reason": lead.score_reason,
        "source": lead.source,
        "source_ref_id": lead.source_ref_id,
        "notes": lead.notes,
        "tags": list(lead.tags or []),
        "opening_line": lead.opening_line,
        "opening_line_generated_at_unix": int(lead.opening_line_generated_at.timestamp())
            if lead.opening_line_generated_at else None,
        "opening_line_variants": list(lead.opening_line_variants or []),
        "sequence_state": lead.sequence_state or "active",
        "last_reply_at_unix": int(lead.last_reply_at.timestamp())
            if lead.last_reply_at else None,
        "last_reply_intent": lead.last_reply_intent,
        "triggers": list(lead.triggers or []),
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
        "last_activity": lead.last_activity.isoformat() if lead.last_activity else None,
    }


# ─────────────────────────────────────────
# MOCK TENANT — will be replaced by real auth later
# TODO(auth): replace with JWT/session-derived tenant_id
# ─────────────────────────────────────────
async def get_tenant_id() -> UUID:
    return UUID(settings.default_tenant_id)


# ─────────────────────────────────────────
# CREATE LEAD
# ─────────────────────────────────────────
@router.post("/", response_model=schemas.LeadResponse, status_code=201)
async def create_lead(
    lead: schemas.LeadCreate,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Create a new lead manually."""
    new_lead = Lead(**lead.model_dump(), tenant_id=tenant_id)
    db.add(new_lead)
    await db.commit()
    await db.refresh(new_lead)

    # Log the creation in the activity timeline
    activity = ActivityLog(
        tenant_id=tenant_id,
        lead_id=new_lead.id,
        action_type="lead_created",
        description=f"Lead '{new_lead.name}' created via {new_lead.source}",
        metadata_={"source": new_lead.source},
        triggered_by="admin"
    )
    db.add(activity)
    await db.commit()

    return new_lead


# ─────────────────────────────────────────
# ACCOUNT ROLLUP — same data, ABM lens. Groups leads by company_domain
# (falling back to company_name when domain is null). The Home dashboard
# can answer "which accounts are heating up?" without scrolling through
# individual lead rows.
# ─────────────────────────────────────────
@router.get("/icp-retrospective")
async def icp_retrospective(
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
    top_n: int = Query(20, ge=5, le=100),
):
    """Cluster the workspace's top-performing leads (replied or hot) and
    surface the patterns. Closes the ICP feedback loop: the user gets a
    "your top 20 hot leads have these common attributes — here's what
    your ICP description might be missing" view.

    Pure SQL aggregation + tag/source/trigger frequency counts. No LLM
    involved; the user reads the raw distribution and decides what to
    edit. Skipping LLM keeps the endpoint cheap to call and explainable.
    """
    candidates = (await db.execute(
        select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.deleted_at == None,  # noqa: E711
        ).where(
            (Lead.sequence_state == "paused_replied")
            | (Lead.score >= 80)
        ).order_by(desc(Lead.score), desc(Lead.last_activity)).limit(top_n)
    )).scalars().all()

    if not candidates:
        return {
            "ok": False,
            "code": "no_signal",
            "message": "Not enough hot/replied leads yet. Get a few replies "
                       "or run scrapers to land more 80+ leads, then re-check.",
            "lead_count": 0,
        }

    from collections import Counter
    sources = Counter()
    titles = Counter()
    triggers = Counter()
    domains = Counter()
    tag_words = Counter()
    intents = Counter()
    score_sum = 0
    replied_count = 0
    for l in candidates:
        if l.source:
            sources[l.source] += 1
        if l.title:
            titles[l.title.split(",")[0].split(" - ")[0].strip()[:80]] += 1
        for t in (l.triggers or []):
            triggers[t] += 1
        if l.company_domain:
            # Group by TLD + last-meaningful-label combo for clustering.
            parts = l.company_domain.lower().split(".")
            if len(parts) >= 2:
                domains[".".join(parts[-2:])] += 1
        for tag in (l.tags or []):
            tag_words[tag.lower()] += 1
        if l.last_reply_intent:
            intents[l.last_reply_intent] += 1
        score_sum += (l.score or 0)
        if l.sequence_state == "paused_replied":
            replied_count += 1

    def _top(c: Counter, n=5) -> list[dict]:
        return [{"value": k, "count": v} for k, v in c.most_common(n)]

    suggestions: list[str] = []
    # Source concentration
    if sources:
        top_src, top_n_count = sources.most_common(1)[0]
        share = top_n_count / max(sum(sources.values()), 1)
        if share >= 0.4:
            suggestions.append(
                f"{int(share*100)}% of hot/replied leads come from `{top_src}` — "
                f"prioritize that source in your scraper schedule."
            )
    # Common titles
    if titles:
        top_title, _ = titles.most_common(1)[0]
        if titles[top_title] >= 3:
            suggestions.append(
                f"`{top_title}` is the most common title across hot leads — "
                f"consider adding it explicitly to the ICP description."
            )
    # Triggers
    if triggers:
        top_trigger = triggers.most_common(1)[0]
        if top_trigger[1] >= 3:
            suggestions.append(
                f"`{top_trigger[0]}` trigger appears in {top_trigger[1]} of "
                f"the top leads — emphasize timing-related signals in your scoring."
            )
    # Reply intent quality
    if intents and replied_count >= 3:
        positive = intents.get("positive", 0)
        if positive == 0:
            suggestions.append(
                f"None of {replied_count} replies were positive — your ICP may "
                f"be matching the wrong persona, or your messaging is missing the mark."
            )

    return {
        "ok": True,
        "lead_count": len(candidates),
        "replied_count": replied_count,
        "avg_score": round(score_sum / max(len(candidates), 1)),
        "top_sources": _top(sources),
        "top_titles": _top(titles),
        "top_triggers": _top(triggers),
        "top_company_domains": _top(domains, n=10),
        "top_tags": _top(tag_words),
        "intents": dict(intents),
        "suggestions": suggestions,
    }


@router.get("/accounts")
async def list_accounts(
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query("hot", description="hot | replied | recent"),
):
    """Aggregate leads by company. Each row:
       {key, company_name, lead_count, hot_count, replied_count,
        avg_score, last_activity_unix, lead_ids[:5]}
    """
    rows = (await db.execute(
        select(Lead).where(
            Lead.tenant_id == tenant_id, Lead.deleted_at == None,  # noqa: E711
        )
    )).scalars().all()

    # Group in Python — at the small-team scale this product targets, that
    # avoids a complicated SQL aggregate while keeping the response shape
    # honest. If a tenant ever crosses ~50k leads, swap for a SQL GROUP BY.
    accounts: dict[str, dict] = {}
    for lead in rows:
        key = (lead.company_domain or "").strip().lower() or \
              (lead.company_name or "").strip().lower() or "(unknown)"
        a = accounts.setdefault(key, {
            "key": key,
            "company_name": lead.company_name or lead.company_domain or "(unknown)",
            "company_domain": lead.company_domain,
            "lead_count": 0, "hot_count": 0, "replied_count": 0,
            "score_sum": 0, "score_count": 0,
            "last_activity_unix": 0, "lead_ids": [], "triggers": set(),
        })
        a["lead_count"] += 1
        score = lead.score or 0
        if score >= 80:
            a["hot_count"] += 1
        if lead.sequence_state == "paused_replied":
            a["replied_count"] += 1
        a["score_sum"] += score
        a["score_count"] += 1
        last = int(lead.last_activity.timestamp()) if lead.last_activity else 0
        if last > a["last_activity_unix"]:
            a["last_activity_unix"] = last
        if len(a["lead_ids"]) < 5:
            a["lead_ids"].append(str(lead.id))
        for t in (lead.triggers or []):
            a["triggers"].add(t)

    items = []
    for a in accounts.values():
        items.append({
            "key": a["key"],
            "company_name": a["company_name"],
            "company_domain": a["company_domain"],
            "lead_count": a["lead_count"],
            "hot_count": a["hot_count"],
            "replied_count": a["replied_count"],
            "avg_score": round(a["score_sum"] / a["score_count"]) if a["score_count"] else 0,
            "last_activity_unix": a["last_activity_unix"] or None,
            "lead_ids": a["lead_ids"],
            "triggers": sorted(a["triggers"]),
        })

    if sort == "replied":
        items.sort(key=lambda x: (x["replied_count"], x["hot_count"], x["lead_count"]), reverse=True)
    elif sort == "recent":
        items.sort(key=lambda x: x["last_activity_unix"] or 0, reverse=True)
    else:  # hot
        items.sort(key=lambda x: (x["hot_count"], x["replied_count"], x["avg_score"]), reverse=True)

    return {"items": items[:limit], "total": len(items)}


# ─────────────────────────────────────────
# LIVE SEQUENCE STATS — used by the Home dashboard so the user gets a live
# reply-rate the moment a reply lands, instead of waiting for the manually-
# triggered weekly report. Single round-trip, no joins beyond what the lead
# row already carries; safe to call from the Home `useEffect`.
# ─────────────────────────────────────────
@router.get("/sequence-stats")
async def sequence_stats(
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Returns live counts for the sequence loop:
       - in_sequence_total : leads with any sequence state (active or replied)
       - replied_total     : leads currently in paused_replied
       - replied_7d        : replies received in the last 7 days
       - reply_rate        : replied_total / in_sequence_total (0.0..1.0)
       - last_reply_at_unix: most recent last_reply_at across the workspace
    """
    base = select(Lead).where(
        Lead.tenant_id == tenant_id,
        Lead.deleted_at == None,  # noqa: E711
    )
    in_sequence_total = (await db.execute(
        select(func.count()).select_from(
            base.where(Lead.sequence_state.in_(("active", "paused_replied"))).subquery()
        )
    )).scalar() or 0
    replied_total = (await db.execute(
        select(func.count()).select_from(
            base.where(Lead.sequence_state == "paused_replied").subquery()
        )
    )).scalar() or 0
    seven_d = datetime.now(timezone.utc) - timedelta(days=7)
    replied_7d = (await db.execute(
        select(func.count()).select_from(
            base.where(
                Lead.sequence_state == "paused_replied",
                Lead.last_reply_at != None,  # noqa: E711
                Lead.last_reply_at >= seven_d,
            ).subquery()
        )
    )).scalar() or 0
    last_reply = (await db.execute(
        select(func.max(Lead.last_reply_at)).where(
            Lead.tenant_id == tenant_id,
            Lead.deleted_at == None,  # noqa: E711
        )
    )).scalar()

    rate = round(replied_total / in_sequence_total, 4) if in_sequence_total else 0.0
    return {
        "in_sequence_total": int(in_sequence_total),
        "replied_total": int(replied_total),
        "replied_7d": int(replied_7d),
        "reply_rate": rate,
        "last_reply_at_unix": int(last_reply.timestamp()) if last_reply else None,
    }


# ─────────────────────────────────────────
# LIST LEADS (with filters)
# ─────────────────────────────────────────
@router.get("/")
async def list_leads(
    status: Optional[str] = Query(None, description="Filter by pipeline stage"),
    source: Optional[str] = Query(None, description="Filter by lead source"),
    min_score: Optional[int] = Query(None, description="Minimum score"),
    max_score: Optional[int] = Query(None, description="Maximum score"),
    q: Optional[str] = Query(None, description="Free-text search across name, email, company"),
    intent: Optional[str] = Query(None, description="Filter by last_reply_intent (positive, negative, neutral, wrong_person, unsubscribe, auto_reply)"),
    view: Optional[str] = Query(None, description="View mode: kanban | table (frontend-only hint)"),
    limit: int = Query(25, ge=1, le=100),
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """List leads with optional filters.

    Returns the paginated `{items, total_estimate}` shape the frontend
    expects (matches the rest of the M2 API contract). The earlier flat-
    array shape silently broke list pages that did `res.items || []`.
    """
    base = select(Lead).where(Lead.tenant_id == tenant_id, Lead.deleted_at == None)

    if status:
        base = base.where(Lead.status == status)
    if source:
        base = base.where(Lead.source == source)
    if min_score is not None:
        base = base.where(Lead.score >= min_score)
    if max_score is not None:
        base = base.where(Lead.score <= max_score)
    if intent and intent.strip():
        base = base.where(Lead.last_reply_intent == intent.strip())
    if q and q.strip():
        # Case-insensitive substring across the three fields a user actually
        # types into. ILIKE is fine at small-team scale; if this list ever
        # grows past ~10k rows per tenant, swap for a tsvector index.
        from sqlalchemy import or_
        like = f"%{q.strip()}%"
        base = base.where(or_(
            Lead.name.ilike(like),
            Lead.email.ilike(like),
            Lead.company_name.ilike(like),
        ))

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    page_q = base.order_by(desc(Lead.last_activity), desc(Lead.created_at)).limit(limit)
    items = (await db.execute(page_q)).scalars().all()

    return {
        "items": [_lead_to_dict(it) for it in items],
        "total_estimate": total,
        "next_cursor": None,
    }


# ─────────────────────────────────────────
# REPLIES — leads ordered by most recent inbound reply
# ─────────────────────────────────────────
@router.get("/replies")
async def list_reply_leads(
    intent: Optional[str] = Query(None, description="positive | negative | neutral | wrong_person | unsubscribe | auto_reply"),
    limit: int = Query(50, ge=1, le=200),
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """All leads that have an inbound reply, ordered by most recent reply.

    Fills the gap where the IMAP poller writes last_reply_intent + last_reply_at
    on Lead rows but no UI surface lists them. Same response shape as
    GET /api/leads so the frontend can render with existing LeadCard.
    """
    base = (
        select(Lead)
        .where(
            Lead.tenant_id == tenant_id,
            Lead.deleted_at == None,  # noqa: E711
            Lead.last_reply_at != None,  # noqa: E711
        )
    )
    if intent and intent.strip():
        base = base.where(Lead.last_reply_intent == intent.strip())

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    page = (await db.execute(base.order_by(desc(Lead.last_reply_at)).limit(limit))).scalars().all()

    return {
        "items": [_lead_to_dict(it) for it in page],
        "total_estimate": total,
        "next_cursor": None,
    }


# ─────────────────────────────────────────
# GET SINGLE LEAD
# ─────────────────────────────────────────
@router.get("/{lead_id}")
async def get_lead(
    lead_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Get a single lead by ID."""
    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id, Lead.deleted_at == None)
    result = await db.execute(query)
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _lead_to_dict(lead)


# ─────────────────────────────────────────
# UPDATE LEAD (PATCH)
# ─────────────────────────────────────────
@router.patch("/{lead_id}", response_model=schemas.LeadResponse)
async def update_lead(
    lead_id: UUID,
    updates: schemas.LeadUpdate,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Update specific fields on a lead. Only provided fields are changed."""
    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id, Lead.deleted_at == None)
    result = await db.execute(query)
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Validate status if provided
    update_data = updates.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] not in schemas.VALID_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Must be one of: {schemas.VALID_STAGES}"
        )

    # Track what changed for the activity log
    changes = {}
    for field, value in update_data.items():
        old_value = getattr(lead, field, None)
        if old_value != value:
            changes[field] = {"from": str(old_value), "to": str(value)}
            setattr(lead, field, value)

    if changes:
        # Log the update
        activity = ActivityLog(
            tenant_id=tenant_id,
            lead_id=lead.id,
            action_type="lead_updated",
            description=f"Updated fields: {', '.join(changes.keys())}",
            metadata_=changes,
            triggered_by="admin"
        )
        db.add(activity)

    await db.commit()
    await db.refresh(lead)
    return lead


# ─────────────────────────────────────────
# DELETE LEAD (soft delete)
# ─────────────────────────────────────────
@router.delete("/{lead_id}", status_code=204)
async def delete_lead(
    lead_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Soft-delete a lead. Row is kept in the database for audit purposes."""
    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id, Lead.deleted_at == None)
    result = await db.execute(query)
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.deleted_at = datetime.now(timezone.utc)

    activity = ActivityLog(
        tenant_id=tenant_id,
        lead_id=lead.id,
        action_type="lead_deleted",
        description=f"Lead '{lead.name}' soft-deleted",
        metadata_={},
        triggered_by="admin"
    )
    db.add(activity)
    await db.commit()


# ─────────────────────────────────────────
# BULK ACTIONS — multi-select operations from the leads table.
#
# Single endpoint dispatches by `action` so the FE only has one URL to call
# regardless of which bulk operation it's performing. Per-id results are
# reported back so partial failures (e.g. one lead already deleted) don't
# silently swallow the others.
# ─────────────────────────────────────────
class BulkActionBody(BaseModel):
    ids: List[UUID] = Field(..., min_length=1, max_length=500)
    action: str  # delete | add_tags | remove_tags | set_status
    args: Dict[str, Any] = Field(default_factory=dict)


@router.post("/bulk")
async def bulk_lead_action(
    body: BulkActionBody,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    rows = (await db.execute(
        select(Lead).where(Lead.id.in_(body.ids), Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalars().all()
    by_id = {l.id: l for l in rows}
    affected = 0
    skipped = 0
    now = datetime.now(timezone.utc)

    if body.action == "delete":
        for lid in body.ids:
            l = by_id.get(lid)
            if not l:
                skipped += 1
                continue
            l.deleted_at = now
            db.add(ActivityLog(
                tenant_id=tenant_id, lead_id=l.id,
                action_type="lead_deleted",
                description=f"Lead '{l.name}' bulk-deleted",
                metadata_={"bulk": True}, triggered_by="admin",
            ))
            affected += 1
    elif body.action in ("add_tags", "remove_tags"):
        new_tags = [t.strip() for t in (body.args.get("tags") or []) if t and t.strip()]
        if not new_tags:
            raise HTTPException(status_code=422, detail={"code": "no_tags", "message": "Pass args.tags=[...]"})
        for lid in body.ids:
            l = by_id.get(lid)
            if not l:
                skipped += 1
                continue
            current = set(l.tags or [])
            if body.action == "add_tags":
                merged = sorted(current | set(new_tags))
            else:
                merged = sorted(current - set(new_tags))
            l.tags = merged
            l.last_activity = now
            affected += 1
    elif body.action == "set_status":
        target = (body.args.get("status") or "").strip()
        if not target:
            raise HTTPException(status_code=422, detail={"code": "no_status", "message": "Pass args.status='New' etc."})
        for lid in body.ids:
            l = by_id.get(lid)
            if not l:
                skipped += 1
                continue
            old = l.status
            l.status = target
            l.last_activity = now
            db.add(ActivityLog(
                tenant_id=tenant_id, lead_id=l.id,
                action_type="status_change",
                description=f"Stage {old} → {target} (bulk)",
                metadata_={"from": old, "to": target, "bulk": True},
                triggered_by="admin",
            ))
            affected += 1
    else:
        raise HTTPException(status_code=422, detail={"code": "unknown_action",
            "message": f"action must be one of delete | add_tags | remove_tags | set_status; got {body.action!r}"})

    await db.commit()
    return {"affected": affected, "skipped": skipped, "action": body.action}


# ─────────────────────────────────────────
# KANBAN MOVE — change pipeline stage
# ─────────────────────────────────────────
@router.post("/{lead_id}/kanban-move", response_model=schemas.KanbanMoveResponse)
async def kanban_move(
    lead_id: UUID,
    body: schemas.KanbanMoveRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Move a lead to a different pipeline stage (Kanban column)."""
    if body.stage not in schemas.VALID_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid stage '{body.stage}'. Must be one of: {schemas.VALID_STAGES}"
        )

    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id, Lead.deleted_at == None)
    result = await db.execute(query)
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    old_stage = lead.status

    # Idempotent: if already at this stage, just return
    if lead.status == body.stage:
        return {"lead": lead}

    lead.status = body.stage

    # Log the stage change in the activity timeline
    activity = ActivityLog(
        tenant_id=tenant_id,
        lead_id=lead.id,
        action_type="status_change",
        description=f"Stage changed from '{old_stage}' to '{body.stage}'",
        metadata_={"from": old_stage, "to": body.stage},
        triggered_by="admin"
    )
    db.add(activity)
    await db.commit()
    await db.refresh(lead)

    return {"lead": lead}


# ─────────────────────────────────────────
# CSV IMPORT
# Two-step flow: (1) /import-csv/preview parses headers + first 5 rows so the
# UI can show a column-mapping dropdown; (2) /import-csv commits the import
# with the chosen mapping. Dedup on (tenant_id, lower(email)) — duplicates are
# silently skipped so re-uploads of the same list don't multiply rows.
# ─────────────────────────────────────────

# Heuristics — header text → canonical lead field. Lower-cased substring match.
_HEADER_HINTS = {
    "email": ["email", "e-mail", "mail", "contact"],
    "name":  ["name", "full name", "contact name", "person"],
    "company_name":   ["company", "organization", "organisation", "account", "employer"],
    "company_domain": ["domain", "website", "url", "site"],
    "title":   ["title", "role", "position", "job"],
    "phone":   ["phone", "mobile", "tel", "cell"],
    "linkedin_url": ["linkedin", "li url", "profile"],
    "tags":    ["tag", "tags", "labels", "list"],
}


def _guess_mapping(headers: List[str]) -> Dict[str, Optional[str]]:
    """Best-effort header → lead-field mapping the FE seeds the picker with."""
    mapping: Dict[str, Optional[str]] = {k: None for k in _HEADER_HINTS}
    used: set[str] = set()
    for field, hints in _HEADER_HINTS.items():
        for h in headers:
            if h in used:
                continue
            low = (h or "").strip().lower()
            if any(hint in low for hint in hints):
                mapping[field] = h
                used.add(h)
                break
    return mapping


def _parse_csv(text: str) -> tuple[list[str], list[dict]]:
    """Sniff dialect, return (headers, rows-as-dicts). Rejects non-CSV cleanly."""
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail={"code": "empty", "message": "CSV is empty"})
    try:
        # Try to sniff but fall back to default if sample is weird.
        sample = text[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        headers = [h for h in (reader.fieldnames or []) if h is not None]
        if not headers:
            raise HTTPException(status_code=422, detail={"code": "no_headers", "message": "CSV has no header row"})
        rows = [{(k or ""): (v or "").strip() for k, v in r.items() if k is not None} for r in reader]
        return headers, rows
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail={"code": "parse_failed", "message": str(e)[:200]})


class CsvPreviewBody(BaseModel):
    csv_text: str = Field(..., max_length=2_000_000)


class CsvImportBody(BaseModel):
    csv_text: str = Field(..., max_length=2_000_000)
    mapping: Dict[str, Optional[str]]
    source: str = Field(default="csv_import", max_length=80)
    tags: List[str] = Field(default_factory=list)


@router.post("/import-csv/preview")
async def preview_csv_import(
    body: CsvPreviewBody,
    admin: AdminUser = Depends(require_admin),
):
    """Parse + return headers, suggested mapping, and first 5 rows for UI."""
    headers, rows = _parse_csv(body.csv_text)
    return {
        "headers": headers,
        "row_count": len(rows),
        "suggested_mapping": _guess_mapping(headers),
        "preview_rows": rows[:5],
        "supported_fields": list(_HEADER_HINTS.keys()),
    }


@router.post("/import-csv", status_code=201)
async def commit_csv_import(
    body: CsvImportBody,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Insert rows from a CSV using a header→field mapping. Dedupes on email."""
    headers, rows = _parse_csv(body.csv_text)
    if not rows:
        return {"inserted": 0, "skipped_duplicates": 0, "skipped_invalid": 0, "errors": []}

    name_col  = body.mapping.get("name")
    email_col = body.mapping.get("email")
    if not name_col and not email_col:
        raise HTTPException(status_code=422, detail={"code": "no_identity",
            "message": "Mapping must include at least one of `name` or `email`."})

    # Pre-load the existing emails for this tenant once so we don't issue
    # one SELECT per row. Cheap until tens of thousands of leads — fine for
    # the small-team segment we're targeting.
    existing_emails: set[str] = set()
    if email_col:
        existing = (await db.execute(
            select(Lead.email).where(Lead.tenant_id == tenant_id,
                                     Lead.deleted_at == None,
                                     Lead.email != None)
        )).scalars().all()
        existing_emails = {e.lower() for e in existing if e}

    inserted = 0
    skipped_dup = 0
    skipped_invalid = 0
    errors: list[dict] = []
    seen_in_batch: set[str] = set()  # also dedupe within the upload itself

    def _v(row: dict, key: Optional[str]) -> Optional[str]:
        if not key:
            return None
        val = (row.get(key) or "").strip()
        return val or None

    for idx, row in enumerate(rows, start=2):  # row 1 is the header
        try:
            email = (_v(row, email_col) or "").lower() or None
            if email and email in existing_emails:
                skipped_dup += 1
                continue
            if email and email in seen_in_batch:
                skipped_dup += 1
                continue
            name = _v(row, name_col) or (email.split("@")[0] if email else None)
            if not name:
                skipped_invalid += 1
                errors.append({"row": idx, "reason": "missing both name and email"})
                continue
            lead = Lead(
                tenant_id=tenant_id,
                name=name[:200],
                email=email,
                phone=_v(row, body.mapping.get("phone")),
                company_name=_v(row, body.mapping.get("company_name")),
                company_domain=_v(row, body.mapping.get("company_domain")),
                title=_v(row, body.mapping.get("title")),
                linkedin_url=_v(row, body.mapping.get("linkedin_url")),
                status="new",
                source=body.source,
                tags=list(body.tags) or [],
                score=0,
            )
            db.add(lead)
            inserted += 1
            if email:
                seen_in_batch.add(email)
            # Flush in chunks of 100 so a bad row late in a 10k-row file
            # doesn't blow away the whole import.
            if inserted % 100 == 0:
                await db.commit()
        except Exception as e:
            skipped_invalid += 1
            errors.append({"row": idx, "reason": str(e)[:200]})
    await db.commit()
    return {
        "inserted": inserted,
        "skipped_duplicates": skipped_dup,
        "skipped_invalid": skipped_invalid,
        "errors": errors[:25],  # cap so a broken file doesn't bloat the response
    }


# ─────────────────────────────────────────
# ADD A MANUAL NOTE — appears in the lead's activity timeline.
# ─────────────────────────────────────────
class NoteBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


@router.post("/{lead_id}/notes", status_code=201)
async def add_lead_note(
    lead_id: UUID,
    body: NoteBody,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    activity = ActivityLog(
        tenant_id=tenant_id,
        lead_id=lead_id,
        action_type="note",
        description=body.text.strip()[:280],
        metadata_={"text": body.text.strip(), "by": admin.email if admin else None},
        triggered_by=admin.email if admin else "admin",
    )
    db.add(activity)
    lead.last_activity = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(activity)
    return {
        "id": str(activity.id),
        "lead_id": str(activity.lead_id),
        "kind": "note",
        "summary": activity.description,
        "payload": activity.metadata_ or {},
        "occurred_at_unix": int(activity.created_at.timestamp()) if activity.created_at else None,
    }


# ─────────────────────────────────────────
# REPLY DETECTION — flip the lead's sequence_state to paused_replied so the
# scheduler stops firing send_* steps. Two ingestion paths share this code:
#   1. Manual: user clicks "Mark as replied" in LeadDrawer → source="manual"
#   2. IMAP poller: matches inbound message to a sent message_id → source="imap"
#
# Idempotent on (lead_id, source, received_at) — the IMAP poller will see the
# same message across multiple poll cycles until it's marked read; we don't
# want to write a new activity event each time.
# ─────────────────────────────────────────
class ReplyBody(BaseModel):
    snippet: Optional[str] = Field(None, max_length=2000)
    source: str = Field(default="manual")  # "manual" | "imap"
    received_at_unix: Optional[int] = None  # IMAP path passes the actual time


@router.post("/{lead_id}/reply", status_code=201)
async def mark_lead_replied(
    lead_id: UUID,
    body: ReplyBody,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    if body.source not in ("manual", "imap"):
        raise HTTPException(status_code=422, detail={
            "code": "bad_source",
            "message": "source must be 'manual' or 'imap'",
        })
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    received_at = (datetime.fromtimestamp(body.received_at_unix, tz=timezone.utc)
                   if body.received_at_unix else datetime.now(timezone.utc))

    # Idempotency: if we already wrote a reply_received event from the same
    # source within ±60s of this one, return the existing record. Stops the
    # IMAP poller from minting duplicate timeline rows.
    cutoff_low  = received_at - timedelta(seconds=60)
    cutoff_high = received_at + timedelta(seconds=60)
    existing = (await db.execute(
        select(ActivityLog).where(
            ActivityLog.lead_id == lead_id,
            ActivityLog.tenant_id == tenant_id,
            ActivityLog.action_type == "reply_received",
            ActivityLog.created_at >= cutoff_low,
            ActivityLog.created_at <= cutoff_high,
        ).limit(1)
    )).scalar_one_or_none()
    if existing and (existing.metadata_ or {}).get("source") == body.source:
        return {
            "ok": True,
            "lead_id": str(lead_id),
            "sequence_state": lead.sequence_state,
            "deduped": True,
        }

    # Classify the reply intent. Falls back to "neutral" silently when no
    # LLM key configured — never blocks the manual-mark-replied flow.
    from automations.reply_intent import classify_reply_intent
    intent = await classify_reply_intent(body.snippet or "")

    # Track the reply against the active opener variant.
    from automations.variant_picker import record_reply
    new_variants = record_reply(list(lead.opening_line_variants or []),
                                  lead.opening_line)
    if new_variants is not None and new_variants != lead.opening_line_variants:
        lead.opening_line_variants = new_variants

    # Flip the state. Idempotent — re-marking an already-paused lead is a
    # no-op aside from refreshing last_reply_at.
    lead.sequence_state = "paused_replied"
    lead.last_reply_at = received_at
    lead.last_reply_intent = intent
    lead.last_activity = received_at
    activity = ActivityLog(
        tenant_id=tenant_id,
        lead_id=lead_id,
        action_type="reply_received",
        description=(body.snippet or "(no snippet)").strip()[:280],
        metadata_={
            "snippet": (body.snippet or "").strip()[:2000],
            "source": body.source,
            "intent": intent,
            "received_at_unix": int(received_at.timestamp()),
        },
        triggered_by=admin.email if admin else body.source,
    )
    db.add(activity)
    await db.commit()
    return {
        "ok": True,
        "lead_id": str(lead_id),
        "sequence_state": lead.sequence_state,
        "intent": intent,
        "deduped": False,
    }


class DirectSendBody(BaseModel):
    subject: str = Field(..., min_length=1, max_length=400)
    body_html: str = Field(..., min_length=1, max_length=20000)


@router.post("/{lead_id}/draft-reply")
async def draft_reply(
    lead_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """LLM-draft a contextual response to the prospect's most recent reply.

    Takes the most recent reply_received activity and the lead's enrichment
    context, prompts the model to draft a response in user tone. Returns
    {subject, body_html, model}. Designed to load into the drawer compose
    modal which the user can edit + send. Always falls back to a stub
    template when no LLM key is configured."""
    import os
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    last_reply_act = (await db.execute(
        select(ActivityLog).where(
            ActivityLog.lead_id == lead.id,
            ActivityLog.tenant_id == tenant_id,
            ActivityLog.action_type == "reply_received",
        ).order_by(ActivityLog.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    snippet = ""
    if last_reply_act and last_reply_act.metadata_:
        snippet = (last_reply_act.metadata_.get("snippet") or "").strip()

    first_name = ((lead.name or "").split() or ["there"])[0]
    company = lead.company_name or "your team"

    # Workspace calendar link — when present, both the stub and the LLM
    # output get a soft CTA. Empty = no link injected.
    from db.entities import WorkspaceSettings
    ws = (await db.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.tenant_id == tenant_id)
    )).scalar_one_or_none()
    cal_link = (ws.calendar_link if ws else None) or ""
    cta_block = ""
    if cal_link:
        cta_block = (
            f'<p>If easier — pick a slot here: '
            f'<a href="{cal_link}">{cal_link}</a></p>'
        )

    # Stub fallback when no LLM key — still returns a usable starting point
    # rather than 503'ing the user.
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
        return {
            "subject": f"Re: {company}",
            "body_html": (
                f"<p>Hi {first_name},</p>"
                f"<p>Thanks for the quick reply — happy to keep this short. "
                f"What's the best slot on your end for a 15-min chat this week?</p>"
                f"{cta_block}"
                f"<p>— SmartBiz OS</p>"
            ),
            "model": "stub",
        }

    sys_p = (
        "You draft a short, plain B2B sales reply to a prospect who just "
        "responded positively to a cold email. Keep it under 80 words. No "
        "marketing copy, no buzzwords. Confirm the next step (a 15-min "
        "call) and offer a soft scheduling option. Sign as 'SmartBiz OS'. "
        "Output a JSON object with keys 'subject' and 'body_html'. "
        "body_html must be plain <p>...</p> blocks. Nothing else."
    )
    user_p = (
        f"Prospect first name: {first_name}\n"
        f"Company: {company}\n\n"
        f"Their reply:\n{snippet[:2000] or '(no snippet captured)'}"
    )

    try:
        from lara_smartbiz.utils.llm import complete_text
        text = await complete_text(
            user_p, system=sys_p,
            temperature=0.5, max_output_tokens=400,
        )
        # Strip markdown code fences the model may wrap around the JSON.
        for fence in ("```json", "```"):
            text = text.replace(fence, "")
        text = text.strip()

        import json
        parsed = json.loads(text)
        subject = (parsed.get("subject") or f"Re: {company}").strip()[:300]
        body = (parsed.get("body_html") or "").strip()
        if not body.startswith("<p>"):
            body = f"<p>{body}</p>"
        # If the LLM didn't already weave the calendar link into the body,
        # append the soft CTA before the sign-off.
        if cta_block and cal_link not in body:
            body = body + cta_block
        return {"subject": subject, "body_html": body[:8000],
                "model": resp.model}
    except Exception as e:
        # Last-resort fallback so the drawer doesn't have to handle 502.
        return {
            "subject": f"Re: {company}",
            "body_html": (
                f"<p>Hi {first_name},</p>"
                f"<p>Thanks for the reply — appreciate you getting back. "
                f"What works on your end for a quick 15-min chat?</p>"
                f"{cta_block}"
                f"<p>— SmartBiz OS</p>"
            ),
            "model": "fallback",
            "warning": str(e)[:160],
        }


@router.post("/{lead_id}/send-now")
async def send_email_now(
    lead_id: UUID,
    body: DirectSendBody,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Direct send from the lead drawer — kills the convert → leads list →
    drawer → start sequence → modal chain that the flow audit flagged.

    Routes through the same multi-mailbox / Resend fallback as the scheduler
    so volume caps + suppression + List-Unsubscribe headers all apply.
    Records an `email` activity row so the timeline reflects the send.
    """
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.email:
        raise HTTPException(status_code=422, detail={
            "code": "no_email", "message": "Lead has no email on file"})

    # Pre-flight suppression gate.
    from automations.suppression import is_suppressed, list_unsubscribe_headers
    if await is_suppressed(tenant_id, lead.email):
        raise HTTPException(status_code=409, detail={
            "code": "suppressed",
            "message": f"{lead.email} is on the workspace suppression list — "
                       "cannot send. Remove from /admin/settings to re-enable.",
        })

    # Always inject the unsubscribe footer + headers so direct sends meet
    # the same RFC 8058 bar as scheduler sends.
    headers = list_unsubscribe_headers(lead.id, tenant_id)
    from automations.suppression import public_unsubscribe_url
    unsub_url = public_unsubscribe_url(lead.id, tenant_id)
    html_with_footer = body.body_html + (
        f'<p style="font-size:11px;color:#999;margin-top:24px;">'
        f'Don\'t want these? <a href="{unsub_url}" '
        f'style="color:#999;text-decoration:underline;">Unsubscribe</a>.</p>'
    )

    from automations.smtp_email import send_via_mailbox
    result = await send_via_mailbox(
        tenant_id=tenant_id, to=lead.email,
        subject=body.subject, html=html_with_footer, headers=headers,
    )
    if not result.get("ok"):
        if result.get("code") in ("no_mailbox", "no_capacity", "no_fernet"):
            from automations.email import send_email
            result = await send_email(
                to=lead.email, subject=body.subject, html=html_with_footer,
                headers=headers,
            )
            provider = "resend"
        else:
            provider = "smtp"
            raise HTTPException(status_code=502, detail={
                "code": "send_failed",
                "message": result.get("error") or "send failed",
                "mailbox": result.get("mailbox_email"),
            })
    else:
        provider = "smtp"

    if not result.get("ok"):
        raise HTTPException(status_code=502, detail={
            "code": "send_failed",
            "message": result.get("error") or "send failed",
        })

    # Activity row so the drawer timeline shows the send.
    activity = ActivityLog(
        tenant_id=tenant_id,
        lead_id=lead.id,
        action_type="email",
        description=body.subject[:280],
        metadata_={
            "subject": body.subject,
            "to": lead.email,
            "provider": provider,
            "message_id": result.get("message_id"),
            "mailbox_email": result.get("mailbox_email"),
            "source": "direct_send",
        },
        triggered_by=admin.email if admin else "admin",
    )
    db.add(activity)
    lead.last_activity = datetime.now(timezone.utc)
    await db.commit()

    return {
        "ok": True,
        "lead_id": str(lead.id),
        "provider": provider,
        "message_id": result.get("message_id"),
        "mailbox_email": result.get("mailbox_email"),
    }


@router.get("/{lead_id}/data-export")
async def lead_data_export(
    lead_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """GDPR baseline — return everything we have on a lead in one JSON
    blob. Lead row, score history, activity log, scraper origin (if any).
    Used to satisfy "show me everything you have on me" requests without
    a manual DB dump.
    """
    from db.entities import ScoreHistory
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    activity = (await db.execute(
        select(ActivityLog)
        .where(ActivityLog.lead_id == lead.id, ActivityLog.tenant_id == tenant_id)
        .order_by(ActivityLog.created_at.asc())
    )).scalars().all()

    score_history = (await db.execute(
        select(ScoreHistory)
        .where(ScoreHistory.lead_id == lead.id)
        .order_by(ScoreHistory.scored_at.asc())
    )).scalars().all()

    scraper = None
    if lead.source_ref_id and (lead.source or "").startswith("scraper:"):
        try:
            sr = (await db.execute(
                select(ScraperResult).where(ScraperResult.id == UUID(lead.source_ref_id),
                                            ScraperResult.tenant_id == tenant_id)
            )).scalar_one_or_none()
            if sr:
                scraper = {
                    "source_type": sr.source_type,
                    "extracted_url": sr.extracted_url,
                    "extracted_email": sr.extracted_email,
                    "scraped_at": sr.scraped_at.isoformat() if sr.scraped_at else None,
                    "raw_data": sr.raw_data,
                }
        except Exception:
            pass

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "lead": _lead_to_dict(lead),
        "activity": [
            {
                "id": str(a.id),
                "kind": a.action_type,
                "description": a.description,
                "metadata": a.metadata_,
                "triggered_by": a.triggered_by,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            } for a in activity
        ],
        "score_history": [
            {
                "id": str(s.id),
                "score": s.score,
                "reason": s.reason,
                "factors": s.factors,
                "scored_by": s.scored_by,
                "scored_at": s.scored_at.isoformat() if s.scored_at else None,
            } for s in score_history
        ],
        "scraper_origin": scraper,
    }


@router.post("/{lead_id}/detect-triggers")
async def detect_triggers_endpoint(
    lead_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Re-scan a lead's existing data for trigger signals and update the
    triggers + score. Useful when notes have been edited or enrichment
    was re-run; doesn't fetch new data, just re-classifies what's there."""
    from automations.trigger_detector import detect_triggers, score_boost_for
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    scraper_raw: Optional[dict] = None
    enrichment: Optional[dict] = None
    if lead.source_ref_id and (lead.source or "").startswith("scraper:"):
        try:
            sr = (await db.execute(
                select(ScraperResult).where(ScraperResult.id == UUID(lead.source_ref_id),
                                            ScraperResult.tenant_id == tenant_id)
            )).scalar_one_or_none()
            if sr and sr.raw_data:
                scraper_raw = sr.raw_data
                enrichment = sr.raw_data.get("enrichment") or {}
        except Exception:
            pass

    new_triggers = detect_triggers(
        notes=lead.notes, title=lead.title, company_name=lead.company_name,
        scraper_raw=scraper_raw, enrichment=enrichment,
    )
    old_triggers = list(lead.triggers or [])
    # Only adjust score for newly-added triggers; removing one doesn't roll
    # back its earlier boost (the SDR may have already seen the old score
    # and acted on it).
    added = [t for t in new_triggers if t not in old_triggers]
    if added:
        boost = score_boost_for(added)
        lead.score = min(100, (lead.score or 0) + boost)
    lead.triggers = new_triggers or None
    await db.commit()
    return {
        "lead_id": str(lead_id),
        "triggers": new_triggers,
        "added": added,
        "score": lead.score,
    }


# Toggle the sequence state back to active — for accidental marks or for
# users who want to resume a manually-paused sequence.
@router.post("/{lead_id}/resume-sequence", status_code=200)
async def resume_sequence(
    lead_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.sequence_state = "active"
    lead.last_activity = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "sequence_state": "active"}


# ─────────────────────────────────────────
# ACTIVITY TIMELINE — per lead
# ─────────────────────────────────────────
@router.get("/{lead_id}/activity")
async def get_lead_activity(
    lead_id: UUID,
    kind: Optional[str] = Query(None, description="Filter by action_type"),
    limit: int = Query(25, ge=1, le=100),
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Get the activity timeline for a lead."""
    # First verify the lead exists
    lead_query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id, Lead.deleted_at == None)
    lead_result = await db.execute(lead_query)
    if not lead_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Lead not found")

    # Build activity query
    query = select(ActivityLog).where(
        ActivityLog.lead_id == lead_id,
        ActivityLog.tenant_id == tenant_id
    )

    if kind:
        query = query.where(ActivityLog.action_type == kind)

    # Count total
    count_query = select(func.count()).select_from(ActivityLog).where(
        ActivityLog.lead_id == lead_id,
        ActivityLog.tenant_id == tenant_id
    )
    if kind:
        count_query = count_query.where(ActivityLog.action_type == kind)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Fetch activities, newest first
    query = query.order_by(desc(ActivityLog.created_at)).limit(limit)
    result = await db.execute(query)
    activities = result.scalars().all()

    items = [
        {
            "id": str(a.id),
            "lead_id": str(a.lead_id),
            "kind": a.action_type,                                 # frontend-friendly alias
            "action_type": a.action_type,                          # legacy
            "summary": a.description,
            "description": a.description,
            "payload": a.metadata_ or {},
            "metadata": a.metadata_ or {},
            "actor": a.triggered_by,
            "triggered_by": a.triggered_by,
            "occurred_at_unix": int(a.created_at.timestamp()) if a.created_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in activities
    ]
    return {"items": items, "total": total}


# ─────────────────────────────────────────
# OPENING LINE — AI-drafted personalized first sentence per lead.
#
# The pitch (per the May 2026 competitive scan): every cold-email tool ships
# template-merged personalization ("I noticed you work at {{company}}") that
# both spam filters and humans recognize as slop, with reply rates at
# 0.5-1.5%. The differentiator is grounding ONE sentence in a fresh signal
# the lead actually shipped — their PH launch, YC batch, HN post, GitHub
# trending repo. We already capture those signals via scrapers; this
# endpoint wraps a single LLM call around the richest signal we have.
#
# Stored on the lead so the user can edit it once and reuse across
# sequence steps via {{opening_line}}.
# ─────────────────────────────────────────

class OpeningLineBody(BaseModel):
    force: bool = False  # regenerate even if one already exists


def _build_opening_line_context(lead: Lead, sr_data: Optional[dict]) -> tuple[str, str]:
    """Return (system, user) prompts for the opener call.

    Multi-source grounding: gather every signal we have on the prospect
    (scraper raw, enrichment, hiring/funding triggers, lead notes) and
    ask the model to STACK 2-3 of them into one sentence. Per the May-
    2026 trend scan, stacked-signal openers get 15-25% reply rates vs
    the 3-5% baseline for generic mail-merge style.

    Caller must have already gated on whether enough signal exists.
    """
    sys_prompt = (
        "You write ONE personalized opening sentence for a B2B sales email. "
        "It must STACK 2-3 specific, concrete signals from the prospect — "
        "e.g. their product launch + recent hiring + tech stack, or their "
        "funding round + a blog topic. The more *signal-dense* the sentence, "
        "the better. NEVER use generic firmographics like 'I see you work at "
        "X.' NEVER invent facts. If only one weak signal is available, write "
        "a curious question instead of asserting. Output ONE sentence, 15-30 "
        "words, no preamble, no sign-off, no quotes, plain prose. The "
        "sentence should feel like one human noticed something specific "
        "about another, not like marketing copy."
    )
    enrich = (sr_data or {}).get("enrichment") or {}
    raw = (sr_data or {}).get("raw") or {}
    bits: list[str] = ["[SIGNALS — use 2-3, ignore weaker ones]"]
    bits.append(f"Prospect: {lead.name}{f' ({lead.title})' if lead.title else ''}")
    if lead.company_name:
        bits.append(f"Company: {lead.company_name}")
    if (sr_data or {}).get("source_type"):
        bits.append(f"Origin signal: {sr_data['source_type']}")
    if raw.get("title"):
        bits.append(f"Headline: {_sanitize_for_opener(raw['title'])}")
    # Tagline / one-liner often holds the most distinctive signal.
    if raw.get("tagline"):
        bits.append(f"Tagline: {_sanitize_for_opener(raw['tagline'], 200)}")
    if enrich.get("description"):
        bits.append(f"Page snippet: {_sanitize_for_opener(enrich['description'], 600)}")
    if enrich.get("summary") and enrich.get("summary") != enrich.get("description"):
        bits.append(f"Summary: {_sanitize_for_opener(enrich['summary'], 400)}")
    # Highlights = bullet-point distinctives the scraper extracted.
    if enrich.get("highlights"):
        highlights = enrich["highlights"]
        if isinstance(highlights, list):
            joined = "; ".join(str(h) for h in highlights[:5])
            bits.append(f"Highlights: {_sanitize_for_opener(joined, 400)}")
    # Funding stage is one of the highest-signal triggers (per trend scan).
    funding = enrich.get("funding") or {}
    if funding.get("stage") or funding.get("total_raised"):
        stage = funding.get("stage") or "—"
        raised = funding.get("total_raised")
        suffix = f" ({raised})" if raised else ""
        bits.append(f"Funding: {stage}{suffix}")
    if enrich.get("tech"):
        bits.append(f"Tech detected: {', '.join(enrich['tech'][:8])}")
    # Triggers we already detected at convert-time — feeding them back to
    # the LLM lets it weave them in. ("hiring + funded" is a powerful combo.)
    triggers = list(lead.triggers or [])
    if triggers:
        bits.append(f"Detected triggers: {', '.join(triggers)}")
    # Manual notes the user typed in the drawer.
    if lead.notes:
        bits.append(f"User notes: {_sanitize_for_opener(lead.notes, 400)}")
    if (sr_data or {}).get("extracted_url"):
        bits.append(f"URL: {sr_data['extracted_url']}")
    user_prompt = (
        "Write ONE opening sentence using only these signals. Stack the "
        "2-3 strongest into a single sentence (ignore the weaker ones). "
        "If only one usable signal is here, write a curious question.\n\n"
        + "\n".join(bits)
    )
    return sys_prompt, user_prompt


def _sanitize_for_opener(text: str, max_chars: int = 240) -> str:
    """Tight version of the enrichment sanitizer — opener is the smallest
    surface we have so we keep prompt-injection patterns out hard."""
    if not text:
        return ""
    cleaned = " ".join(text.split())[:max_chars]
    low = cleaned.lower()
    blocks = ("ignore previous", "system prompt", "</untrusted>",
              "you are now", "new instructions", "respond with")
    for b in blocks:
        if b in low:
            cleaned = cleaned.replace(b, "[redacted]")
    return cleaned


async def _load_scraper_signal(db: AsyncSession, lead: Lead, tenant_id: UUID) -> Optional[dict]:
    """Pull the scraper-origin signal for a lead, if it has one. Single-source
    today; the multi-signal-grounding feature in the roadmap will widen this
    to return a list of stacked signals."""
    if not lead.source_ref_id or not (lead.source or "").startswith("scraper:"):
        return None
    try:
        sr = (await db.execute(
            select(ScraperResult).where(ScraperResult.id == UUID(lead.source_ref_id),
                                        ScraperResult.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not sr:
            return None
        return {
            "source_type": sr.source_type,
            "extracted_url": sr.extracted_url,
            "raw": sr.raw_data or {},
            "enrichment": (sr.raw_data or {}).get("enrichment") or {},
        }
    except Exception:
        return None


async def _generate_opening_line_for_lead(db: AsyncSession, lead: Lead, tenant_id: UUID,
                                          *, force: bool) -> dict:
    """Pure helper: returns {ok, opening_line?, code?, message?}.

    Single-lead and bulk paths both call this. The bulk path catches errors
    per-lead so one bad signal doesn't fail the whole batch."""
    import os
    from datetime import datetime, timezone

    if lead.opening_line and not force:
        return {"ok": True, "opening_line": lead.opening_line, "was_cached": True,
                "generated_at_unix": int(lead.opening_line_generated_at.timestamp())
                    if lead.opening_line_generated_at else None}

    sr_data = await _load_scraper_signal(db, lead, tenant_id)
    if not sr_data and not (lead.notes or lead.title):
        return {"ok": False, "code": "no_signal",
                "message": "Need a scraper origin, notes, or title to ground the opener."}

    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return {"ok": False, "code": "no_llm_key",
                "message": "Set GOOGLE_API_KEY or OPENAI_API_KEY."}

    sys_p, user_p = _build_opening_line_context(lead, sr_data)
    try:
        from lara_smartbiz.utils.llm import complete_text
        text = await complete_text(
            user_p, system=sys_p,
            temperature=0.7, max_output_tokens=180,
        )
        for q in ('"', "'", "`", "*"):
            text = text.strip(q)
        text = text.split("\n")[0].strip()
        if not text:
            return {"ok": False, "code": "empty_response", "message": "LLM returned empty text"}
    except Exception as e:
        return {"ok": False, "code": "llm_failed", "message": str(e)[:200]}

    lead.opening_line = text[:600]
    lead.opening_line_generated_at = datetime.now(timezone.utc)
    return {"ok": True, "opening_line": lead.opening_line, "was_cached": False,
            "generated_at_unix": int(lead.opening_line_generated_at.timestamp())}


@router.post("/{lead_id}/opening-line/generate")
async def generate_opening_line(
    lead_id: UUID,
    body: Optional[OpeningLineBody] = Body(default=None),
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    payload = body or OpeningLineBody()
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    result = await _generate_opening_line_for_lead(db, lead, tenant_id, force=payload.force)
    if not result.get("ok"):
        # Map the helper's error codes to the same HTTP shape we used before.
        code_map = {"no_signal": 422, "no_llm_key": 503,
                    "empty_response": 502, "llm_failed": 502}
        status = code_map.get(result.get("code"), 500)
        raise HTTPException(status_code=status, detail={
            "code": result.get("code"), "message": result.get("message"),
        })
    if not result.get("was_cached"):
        await db.commit()
    return {k: v for k, v in result.items() if k != "ok"}


class BulkOpeningLineBody(BaseModel):
    lead_ids: List[UUID] = Field(..., min_length=1, max_length=50)
    force: bool = False


class VariantsBody(BaseModel):
    count: int = Field(default=3, ge=2, le=5)
    force: bool = False


@router.post("/{lead_id}/opening-line/variants")
async def generate_opening_line_variants(
    lead_id: UUID,
    body: Optional[VariantsBody] = Body(default=None),
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Generate N opener variants for the lead and store them as the
    candidate pool. Active variant (opening_line) is set to the first
    new variant. The scheduler rotates among variants until each has
    >=3 sends; then it picks the highest reply rate.

    Idempotent on `force=False` when variants already exist.
    """
    import asyncio
    import os
    from datetime import datetime, timezone

    payload = body or VariantsBody()
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    existing = list(lead.opening_line_variants or [])
    if existing and not payload.force:
        return {"variants": existing, "was_cached": True, "active": lead.opening_line}

    sr_data = await _load_scraper_signal(db, lead, tenant_id)
    if not sr_data and not (lead.notes or lead.title):
        raise HTTPException(status_code=422, detail={
            "code": "no_signal",
            "message": "Need a scraper origin, notes, or title to ground variants.",
        })

    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise HTTPException(status_code=503, detail={"code": "no_llm_key"})

    sys_p, user_p = _build_opening_line_context(lead, sr_data)
    # Append a per-call style nudge so the variants diverge meaningfully.
    style_nudges = [
        "Tone: direct + curious. Lead with a question.",
        "Tone: warm + observational. Lead with a specific compliment-by-detail.",
        "Tone: pragmatic + brief. Lead with a numbers-or-facts hook.",
        "Tone: founder-to-founder. Lead with a peer observation.",
        "Tone: insightful + thoughtful. Lead with a hypothesis about their challenge.",
    ]

    from lara_smartbiz.utils.llm import complete_text

    async def _gen_one(nudge: str) -> Optional[str]:
        try:
            text = await complete_text(
                user_p,
                system=sys_p + "\n\n" + nudge,
                temperature=0.85,  # higher for diversity across variants
                max_output_tokens=180,
            )
            for q in ('"', "'", "`", "*"):
                text = text.strip(q)
            text = text.split("\n")[0].strip()
            return text if text else None
        except Exception:
            return None

    nudges = style_nudges[: payload.count]
    texts = await asyncio.gather(*[_gen_one(n) for n in nudges])
    fresh = [t for t in texts if t]
    # Dedupe identical lines from the model.
    seen: set[str] = set()
    deduped: list[str] = []
    for t in fresh:
        k = t.lower().strip()
        if k and k not in seen:
            seen.add(k)
            deduped.append(t[:600])

    if not deduped:
        raise HTTPException(status_code=502, detail={"code": "all_failed",
            "message": "All variant generations failed"})

    now_unix = int(datetime.now(timezone.utc).timestamp())
    variants = [
        {"text": t, "sent_count": 0, "replied_count": 0,
         "generated_at_unix": now_unix}
        for t in deduped
    ]
    lead.opening_line_variants = variants
    lead.opening_line = variants[0]["text"]
    lead.opening_line_generated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"variants": variants, "was_cached": False, "active": lead.opening_line}


@router.post("/{lead_id}/opening-line/promote")
async def promote_opening_line_variant(
    lead_id: UUID,
    body: dict = Body(...),
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Manually pick which variant is active (overrides rotation).
    Body: {"index": int} or {"text": str}.
    """
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    variants = list(lead.opening_line_variants or [])
    if not variants:
        raise HTTPException(status_code=422, detail="no variants to promote")

    chosen: Optional[str] = None
    if "index" in body:
        idx = int(body["index"])
        if 0 <= idx < len(variants):
            chosen = variants[idx]["text"]
    elif "text" in body:
        wanted = (body.get("text") or "").strip()
        for v in variants:
            if v.get("text") == wanted:
                chosen = wanted
                break
    if chosen is None:
        raise HTTPException(status_code=422, detail="variant not found")

    lead.opening_line = chosen
    await db.commit()
    return {"opening_line": lead.opening_line, "variants": variants}


@router.post("/bulk/opening-lines")
async def bulk_generate_opening_lines(
    body: BulkOpeningLineBody,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Run the opener generator across N leads in parallel (concurrency 5).

    Returns a per-lead result dict so the UI can show "12 generated, 3
    skipped (no signal), 1 LLM error." Errors are surfaced per-lead — the
    batch never fails wholesale because of one bad lead. Daily-workflow
    feature: SDR converts 20 hot captures → one click → 20 personalized
    openers waiting in the drawer.
    """
    import asyncio

    leads = (await db.execute(
        select(Lead).where(Lead.id.in_(body.lead_ids),
                           Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalars().all()
    found_ids = {lead.id for lead in leads}
    missing = [str(lid) for lid in body.lead_ids if lid not in found_ids]

    sem = asyncio.Semaphore(5)
    async def _run(lead: Lead) -> tuple[Lead, dict]:
        async with sem:
            return lead, await _generate_opening_line_for_lead(
                db, lead, tenant_id, force=body.force,
            )

    pairs = await asyncio.gather(*[_run(l) for l in leads], return_exceptions=False)

    results = []
    summary = {"generated": 0, "cached": 0, "skipped_no_signal": 0,
               "errors": 0, "missing": len(missing)}
    for lead, r in pairs:
        entry = {"lead_id": str(lead.id), **{k: v for k, v in r.items() if k != "ok"}}
        if r.get("ok"):
            entry["ok"] = True
            if r.get("was_cached"):
                summary["cached"] += 1
            else:
                summary["generated"] += 1
        else:
            entry["ok"] = False
            if r.get("code") == "no_signal":
                summary["skipped_no_signal"] += 1
            else:
                summary["errors"] += 1
        results.append(entry)

    # Single commit — all successful generations are written together.
    if summary["generated"]:
        await db.commit()

    return {"summary": summary, "results": results, "missing": missing}


class OpeningLinePatchBody(BaseModel):
    opening_line: Optional[str] = Field(None, max_length=600)


@router.patch("/{lead_id}/opening-line")
async def patch_opening_line(
    lead_id: UUID,
    body: OpeningLinePatchBody,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    """Hand-edit the opener (or clear it by passing null/empty)."""
    from datetime import datetime, timezone
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    val = (body.opening_line or "").strip() or None
    lead.opening_line = val
    lead.opening_line_generated_at = datetime.now(timezone.utc) if val else None
    await db.commit()
    return {"opening_line": lead.opening_line}


# ─────────────────────────────────────────
# ENRICHMENT CONTEXT — surfaces scraper-source enrichment in the drawer.
#
# When a lead was promoted from a scraper capture, the rich enrichment dossier
# (page description, tech stack, hunter intel, ICP rubric) lives on the
# ScraperResult.raw_data["enrichment"] blob — not on the lead. The drawer
# calls this endpoint to render that context as structured fields instead of
# the unreadable `notes` text blob the converter creates.
# Returns 404 with no body when the lead has no scraper origin (drawer hides
# the section). Always returns 200 when origin exists, even if enrichment
# itself is still empty (so the drawer can show "not enriched yet").
# ─────────────────────────────────────────
@router.get("/{lead_id}/enrichment-context")
async def get_enrichment_context(
    lead_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id,
                           Lead.deleted_at == None)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.source_ref_id or not (lead.source or "").startswith("scraper:"):
        raise HTTPException(status_code=404, detail="No scraper origin")
    try:
        rid = UUID(lead.source_ref_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="No scraper origin")
    sr = (await db.execute(
        select(ScraperResult).where(ScraperResult.id == rid,
                                    ScraperResult.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Source row not found")
    enrich = (sr.raw_data or {}).get("enrichment") or {}
    return {
        "source": {
            "type": sr.source_type,
            "url": sr.extracted_url,
            "summary": (sr.raw_data or {}).get("summary"),
            "scraped_at_unix": int(sr.scraped_at.timestamp()) if sr.scraped_at else None,
            "relevance_score": sr.relevance_score,
            "scraper_result_id": str(sr.id),
        },
        "enrichment": {
            "domain":       enrich.get("domain"),
            "description":  enrich.get("description"),
            "emails":       list(enrich.get("emails") or []),
            "tech":         list(enrich.get("tech") or []),
            "fetcher":      enrich.get("fetcher"),
            "page_meta":    enrich.get("page_meta") or {},
            "hunter":       enrich.get("hunter"),
            "email_verification": enrich.get("email_verification"),
            "score":        enrich.get("score"),
            "reason":       enrich.get("reason"),
            "rubric":       enrich.get("rubric"),
        } if enrich else None,
    }

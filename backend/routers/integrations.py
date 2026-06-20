"""
routers/integrations.py — M2 Sales Intel integrations & scrapers endpoints.

DB-backed: integrations live in the `integrations` table (existing schema),
scrapers in `scrapers` (added in migration 001). The provider catalog used by
the connect flow is a static dict — providers don't change at runtime.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession

import logging

from auth.dependencies import require_admin
from automations.lead_enrichment import enrich_batch, enrich_one
from automations.scrapers import execute_scraper

log = logging.getLogger("smartbiz.integrations")

# Per-tenant in-memory lock for bulk enrichment. Prevents the user from firing
# 10 bulk jobs in a row and racking up 500 LLM calls. The lock auto-clears
# when the BackgroundTask finishes — see _run_bulk_enrich_locked below.
_BULK_ENRICH_INFLIGHT: set[str] = set()
from config import settings
from db.connection import SessionLocal, get_db
from db.entities import Integration, Lead, ScraperResult, ScraperSource

router = APIRouter(
    prefix="/api",
    tags=["Integrations"],
    # All integration + scraper endpoints require admin auth — bulk enrich
    # spends LLM credits, convert mints leads, etc.
    dependencies=[Depends(require_admin)],
)


def _tenant() -> uuid.UUID:
    return uuid.UUID(settings.default_tenant_id)


def _ts(dt: Optional[datetime]) -> Optional[int]:
    return int(dt.timestamp()) if dt else None


# Provider catalog — static, used to resolve display name + label on connect.
PROVIDERS: dict[str, dict] = {
    "hubspot": {
        "name": "HubSpot CRM",
        "scopes": ["crm.objects.contacts.read", "crm.objects.deals.read"],
        "note": "Two-way sync of contacts and deals. Bidirectional updates queued every 15 min.",
        "default_label": "ops@zerotoprod.tech",
    },
    "google_sheets": {
        "name": "Google Sheets",
        "scopes": ["https://www.googleapis.com/auth/spreadsheets.readonly"],
        "note": "Pulls from a configured sheet on schedule.",
        "default_label": "Leads — master list",
    },
    "tally": {
        "name": "Tally",
        "scopes": [],
        "note": "Webhook-based form ingest. Connect to capture form responses as leads.",
        "default_label": "Tally workspace",
    },
    "resend": {
        "name": "Resend (email)",
        "scopes": ["emails:send", "domains:read"],
        "note": "Outbound email + open/click webhooks.",
        "default_label": "send@demo.zerotoprod.tech",
    },
    "apollo": {
        "name": "Apollo.io",
        "scopes": [],
        "note": "Enrichment data source. Drop in API key to enable per-lead lookups.",
        "default_label": "Apollo workspace",
    },
}


def _shape_integration(it: Integration) -> dict:
    cfg = it.config or {}
    provider_meta = PROVIDERS.get(it.type, {})
    return {
        "id": str(it.id),
        "type": it.type,
        "provider": it.type,
        "name": provider_meta.get("name", it.type.title()),
        "status": it.status,
        "connected_at_unix": _ts(it.created_at) if it.status == "connected" else None,
        "connected_account_label": cfg.get("account_label") if it.status == "connected" else None,
        "scopes": provider_meta.get("scopes", []),
        "note": provider_meta.get("note"),
        "error_message": it.error_message,
    }


SOURCE_LABELS = {
    "linkedin_seed":   "LinkedIn (profiles)",
    "producthunt":     "Product Hunt (launches)",
    "directories":     "Directories (Crunchbase, Y Combinator)",
    "jobs":            "Job board signal (hiring intent)",
}


def _shape_scraper(s: ScraperSource) -> dict:
    enabled = s.status in ("running", "paused")
    return {
        "id": str(s.id),
        "source": s.source_key,
        "name": s.name,
        "status": s.status,
        "enabled": enabled,
        "schedule": s.schedule or "—",
        "last_run_unix": _ts(s.last_run_at),
        "last_run_at_unix": _ts(s.last_run_at),
        "next_run_unix": _ts(s.next_run_at),
        "leads_last_run": s.leads_last_run or 0,
        "last_run_leads_added": s.leads_last_run or 0,
        "leads_total": s.leads_total or 0,
        "last_run_status": s.status if s.status in ("running", "paused", "failed") else None,
        "note": s.note,
        "notes": s.note,
    }


# ─────────────────────────────────────────
# Integrations
# ─────────────────────────────────────────

@router.get("/integrations")
async def list_integrations(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Integration)
        .where(Integration.tenant_id == _tenant())
        .order_by(desc(Integration.created_at))
    )).scalars().all()
    # Always include providers that aren't connected yet so the UI can show
    # them as "available" tiles.
    seen_types = {r.type for r in rows}
    items = [_shape_integration(r) for r in rows]
    for ptype, meta in PROVIDERS.items():
        if ptype in seen_types:
            continue
        items.append({
            "id": f"available:{ptype}",
            "type": ptype, "provider": ptype,
            "name": meta["name"],
            "status": "disconnected",
            "connected_at_unix": None,
            "connected_account_label": None,
            "scopes": meta.get("scopes", []),
            "note": meta.get("note"), "error_message": None,
        })
    return {"items": items}


@router.get("/integrations/_meta")
async def integrations_meta(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Integration.status).where(Integration.tenant_id == _tenant())
    )).scalars().all()
    by_status: dict[str, int] = {}
    for s in rows:
        by_status[s] = by_status.get(s, 0) + 1
    # Include providers without rows as "available"
    available = sum(1 for ptype in PROVIDERS if ptype not in {r for r in rows})
    if available:
        by_status["available"] = available
    return {"by_status": by_status, "total": len(rows) + available}


@router.get("/integrations/{integration_id}")
async def get_integration(integration_id: str, db: AsyncSession = Depends(get_db)):
    # Handle the "available:<provider>" virtual rows from list().
    if integration_id.startswith("available:"):
        ptype = integration_id.split(":", 1)[1]
        meta = PROVIDERS.get(ptype)
        if not meta:
            raise HTTPException(status_code=404, detail={"code": "not_found",
                                "message": "Integration not found"})
        return {
            "id": integration_id, "type": ptype, "provider": ptype,
            "name": meta["name"], "status": "disconnected",
            "connected_at_unix": None,
            "connected_account_label": None, "scopes": meta.get("scopes", []),
            "note": meta.get("note"), "error_message": None,
        }
    try:
        iid = uuid.UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Integration not found"})
    item = (await db.execute(
        select(Integration).where(Integration.id == iid,
                                  Integration.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Integration not found"})
    return _shape_integration(item)


@router.post("/integrations/connect")
async def connect_provider(body: dict):
    """Reject connect attempts honestly.

    OAuth flows for HubSpot / Zoho / Sheets / Tally aren't implemented yet.
    Previously this endpoint shortcut to status='connected' without any actual
    auth — the UI would render a Connected badge against a non-existent
    connection, so a user converting a hot lead would silently "sync" to
    nowhere. Until a real adapter ships, return 501 so the UI can show a
    truthful "Coming soon" state.
    """
    provider = (body or {}).get("provider", "unknown")
    meta = PROVIDERS.get(provider)
    if not meta:
        raise HTTPException(status_code=422, detail={"code": "validation_failed",
                            "message": f"Unknown provider: {provider}"})
    raise HTTPException(status_code=501, detail={
        "code": "not_implemented",
        "message": f"OAuth for {meta['name']} is not implemented yet — coming soon.",
        "provider": provider,
    })


@router.post("/integrations/{integration_id}/disconnect")
async def disconnect_integration(integration_id: str, db: AsyncSession = Depends(get_db)):
    try:
        iid = uuid.UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Integration not found"})
    item = (await db.execute(
        select(Integration).where(Integration.id == iid,
                                  Integration.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Integration not found"})
    item.status = "disconnected"
    item.config = {}
    await db.commit()
    await db.refresh(item)
    return _shape_integration(item)


# ─────────────────────────────────────────
# Scrapers
# ─────────────────────────────────────────

@router.get("/scrapers")
async def list_scrapers(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ScraperSource).where(ScraperSource.tenant_id == _tenant())
        .order_by(ScraperSource.created_at)
    )).scalars().all()
    return {"items": [_shape_scraper(s) for s in rows]}


# ─────────────────────────────────────────
# Staging routes for captured rows. MUST be registered before the
# /scrapers/{scraper_id} catch-all below — otherwise FastAPI matches
# "results" as a scraper id and 404s.
# ─────────────────────────────────────────

def _shape_result(r: ScraperResult) -> dict:
    return {
        "id": str(r.id),
        "source_type": r.source_type,
        "name": r.extracted_name,
        "company": r.extracted_company,
        "email": r.extracted_email,
        "url": r.extracted_url,
        "relevance_score": r.relevance_score,
        "status": r.status,
        "scraped_at_unix": int(r.scraped_at.timestamp()) if r.scraped_at else None,
        "converted_lead_id": str(r.converted_lead_id) if r.converted_lead_id else None,
        "raw": r.raw_data or {},
    }


@router.get("/scrapers/results/_count")
async def scraper_results_pending_count(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func as sql_func
    count = (await db.execute(
        select(sql_func.count(ScraperResult.id)).where(
            ScraperResult.tenant_id == _tenant(),
            ScraperResult.status == "pending",
        )
    )).scalar() or 0
    return {"pending": int(count)}


@router.get("/inbox/diagnostics")
async def inbox_diagnostics(db: AsyncSession = Depends(get_db)):
    """
    Empty-Inbox diagnostics — answers "why is my inbox empty?" with a
    structured payload the FE renders as one of 4 distinct empty-state cards.

    Priority order for `recommended_action`:
      1. run_scraper       — no scraper has ever run
      2. check_sources     — scrapers ran but found nothing in 7d
      3. lower_threshold   — raw results exist but none cleared user's HOT bar
      4. loosen_icp        — raw results exist but ICP filter pushed them all
                             into the bottom buckets (most rows in 0–30)
      5. none              — sufficient pending captures exist (FE shouldn't
                             render the empty state at all)

    Cheap to run — small index scans on the existing tables. Called on
    Inbox page load whenever the lead-count query returns 0.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func as sql_func, case
    tenant = _tenant()
    since_7d = datetime.now(timezone.utc) - timedelta(days=7)

    # Most recent scraper run across all configured sources for this tenant.
    last_run = (await db.execute(
        select(sql_func.max(ScraperSource.last_run_at))
        .where(ScraperSource.tenant_id == tenant)
    )).scalar()

    raw_7d = (await db.execute(
        select(sql_func.count(ScraperResult.id))
        .where(ScraperResult.tenant_id == tenant,
               ScraperResult.scraped_at >= since_7d)
    )).scalar() or 0

    # Score histogram across pending results (the rows the Inbox would
    # actually surface). Uses CASE buckets so we don't pull every row.
    histogram_row = (await db.execute(
        select(
            sql_func.sum(case((ScraperResult.relevance_score < 30, 1), else_=0)).label("b0_30"),
            sql_func.sum(case((ScraperResult.relevance_score.between(30, 49), 1), else_=0)).label("b30_50"),
            sql_func.sum(case((ScraperResult.relevance_score.between(50, 69), 1), else_=0)).label("b50_70"),
            sql_func.sum(case((ScraperResult.relevance_score >= 70, 1), else_=0)).label("b70_100"),
            sql_func.count(ScraperResult.id).label("total"),
        )
        .where(ScraperResult.tenant_id == tenant,
               ScraperResult.status == "pending")
    )).first()
    h = {
        "0_30":   int(histogram_row.b0_30 or 0),
        "30_50":  int(histogram_row.b30_50 or 0),
        "50_70":  int(histogram_row.b50_70 or 0),
        "70_100": int(histogram_row.b70_100 or 0),
    }
    total_pending = int(histogram_row.total or 0)

    # Pull alert threshold from workspace settings — falls back to 80.
    from db.entities import WorkspaceSettings
    threshold = (await db.execute(
        select(WorkspaceSettings.slack_alert_min_score)
        .where(WorkspaceSettings.tenant_id == tenant)
    )).scalar() or 80

    # Decision tree.
    if last_run is None:
        action = "run_scraper"
    elif raw_7d == 0:
        action = "check_sources"
    elif total_pending == 0:
        # Distinct from "check_sources" — the user has been productive,
        # the queue is just drained. Different copy, different CTA.
        action = "all_triaged"
    elif h["70_100"] == 0 and threshold >= 70:
        action = "lower_threshold"
    elif h["0_30"] >= total_pending * 0.6:
        # >60% of captures are bottom-tier — ICP is rejecting almost
        # everything. The user's ICP description is too narrow.
        action = "loosen_icp"
    else:
        action = "none"

    # Reply pipeline health — surfaces silently-disabled IMAP polling. Without
    # IMAP_ENCRYPTION_KEY, the poller no-ops every cycle and replies never get
    # classified. The FE shows a banner so the user knows.
    import os as _os
    imap_key_present = bool(_os.getenv("IMAP_ENCRYPTION_KEY"))
    reply_pipeline = {
        "imap_encryption_key_set": imap_key_present,
        "imap_disabled_reason": None if imap_key_present
            else "IMAP_ENCRYPTION_KEY env var is unset — reply detection is disabled.",
    }

    return {
        "last_scraper_run_at_unix": int(last_run.timestamp()) if last_run else None,
        "raw_results_7d": raw_7d,
        "pending_total": total_pending,
        "score_histogram": h,
        "alert_threshold": int(threshold),
        "recommended_action": action,
        "reply_pipeline": reply_pipeline,
    }


@router.get("/scrapers/results")
async def list_scraper_results(
    status: Optional[str] = "pending",
    source_type: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    base = select(ScraperResult).where(ScraperResult.tenant_id == _tenant())
    if status and status != "all":
        base = base.where(ScraperResult.status == status)
    if source_type:
        base = base.where(ScraperResult.source_type == source_type)

    # Total before paging — lets the FE surface "Showing N of M" so the user
    # knows there's a tail of older captures hidden behind the cap. Same
    # filters as the page query so the count is accurate for the view.
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0

    capped = min(max(limit, 1), 500)
    rows = (await db.execute(
        base.order_by(desc(ScraperResult.scraped_at)).limit(capped)
    )).scalars().all()
    return {
        "items": [_shape_result(r) for r in rows],
        "total": int(total),
        "limit": capped,
    }


async def _run_bulk_enrich_locked(tenant_key: str, rows: list[uuid.UUID]) -> None:
    """BackgroundTask wrapper: runs enrich_batch and clears the tenant lock
    in a finally so a crash can't leave the lock held forever."""
    try:
        await enrich_batch(rows, None, 5, force=False)
    finally:
        _BULK_ENRICH_INFLIGHT.discard(tenant_key)


@router.post("/scrapers/results/bulk/enrich")
async def bulk_enrich_pending(
    background_tasks: BackgroundTasks,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Kick off enrichment on the N most-recent pending rows. Returns the
    job header; the FE polls /scrapers/results to see progress.
    NOTE: must be registered before /{result_id}/* — FastAPI matches in
    declaration order and "bulk" would otherwise be parsed as a UUID."""
    tenant_key = str(_tenant())
    if tenant_key in _BULK_ENRICH_INFLIGHT:
        # Don't burn LLM credits on duplicate clicks — the prior job will
        # process the new rows too since enrich_batch fetches at run time.
        raise HTTPException(status_code=409, detail={"code": "already_running",
                            "message": "A bulk enrichment job is already in flight for this workspace."})
    rows = (await db.execute(
        select(ScraperResult.id).where(
            ScraperResult.tenant_id == _tenant(),
            ScraperResult.status == "pending",
        ).order_by(desc(ScraperResult.scraped_at)).limit(min(limit, 100))
    )).scalars().all()
    if not rows:
        return {"job_id": None, "queued": 0}
    _BULK_ENRICH_INFLIGHT.add(tenant_key)
    background_tasks.add_task(_run_bulk_enrich_locked, tenant_key, rows)
    return {"job_id": f"enrich_{uuid.uuid4().hex[:10]}", "queued": len(rows)}


@router.post("/scrapers/results/{result_id}/convert", status_code=201)
async def convert_scraper_result(
    result_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Convert a scraped capture into a real Lead. Refuses to convert if
    enrichment hasn't landed yet (the lead would mint at score=50 default,
    polluting the scoring distribution). Pass ?force=true to override."""
    try:
        rid = uuid.UUID(result_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Result not found"})
    # Row-level lock prevents two concurrent /convert calls for the same row
    # from minting duplicate leads. Without FOR UPDATE both requests pass the
    # converted_lead_id check before either commits.
    r = (await db.execute(
        select(ScraperResult).where(ScraperResult.id == rid,
                                    ScraperResult.tenant_id == _tenant())
        .with_for_update()
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Result not found"})
    if r.converted_lead_id:
        raise HTTPException(status_code=409, detail={"code": "already_converted",
                            "message": "Already converted",
                            "details": {"lead_id": str(r.converted_lead_id)}})

    name = (r.extracted_name or r.extracted_company or "Untitled lead")[:200]
    enrich = (r.raw_data or {}).get("enrichment") or {}
    if not enrich.get("score") and not force:
        raise HTTPException(status_code=422, detail={
            "code": "not_enriched",
            "message": "Enrichment hasn't completed for this capture. "
                       "Run /scrapers/results/{id}/enrich first, or pass ?force=true to "
                       "convert anyway with a default score=50.",
        })
    notes_parts: list[str] = []
    if enrich.get("description"):
        notes_parts.append(enrich["description"])
    elif (r.raw_data or {}).get("summary"):
        notes_parts.append((r.raw_data or {}).get("summary"))
    if enrich.get("tech"):
        notes_parts.append("Tech: " + ", ".join(enrich["tech"][:8]))
    if enrich.get("emails") and len(enrich["emails"]) > 1:
        notes_parts.append("More emails: " + ", ".join(enrich["emails"][1:4]))
    lead = Lead(
        tenant_id=_tenant(),
        name=name,
        email=r.extracted_email or (enrich.get("emails") or [None])[0],
        company_name=r.extracted_company,
        company_domain=enrich.get("domain"),
        linkedin_url=r.extracted_url if (r.extracted_url or "").startswith("https://www.linkedin.com") else None,
        status="new",
        source=f"scraper:{r.source_type}",
        source_ref_id=str(r.id),
        score=enrich.get("score") or r.relevance_score or 50,
        score_reason=enrich.get("reason") or "Staged from scraper",
        notes="\n\n".join(notes_parts) or None,
    )
    db.add(lead)
    await db.flush()
    r.converted_lead_id = lead.id
    r.status = "converted"
    r.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"lead_id": str(lead.id), "result": _shape_result(r)}


@router.post("/scrapers/results/{result_id}/enrich")
async def enrich_scraper_result(result_id: str, db: AsyncSession = Depends(get_db)):
    """Force-enrich a single staged row (page fetch + ICP score). Per-row UI
    always passes force=True so the user's explicit click overrides any
    cached enrichment (the bulk path uses force=False to avoid the race)."""
    try:
        rid = uuid.UUID(result_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Result not found"})
    out = await enrich_one(rid, force=True)
    if not out.get("ok"):
        raise HTTPException(status_code=500, detail={"code": "enrich_failed",
                            "message": out.get("error") or "enrichment failed"})
    # Refetch to return the freshly-persisted shape.
    r = (await db.execute(
        select(ScraperResult).where(ScraperResult.id == rid,
                                    ScraperResult.tenant_id == _tenant())
    )).scalar_one_or_none()
    return _shape_result(r) if r else out


@router.post("/scrapers/results/{result_id}/dismiss")
async def dismiss_scraper_result(result_id: str, db: AsyncSession = Depends(get_db)):
    try:
        rid = uuid.UUID(result_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Result not found"})
    r = (await db.execute(
        select(ScraperResult).where(ScraperResult.id == rid,
                                    ScraperResult.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Result not found"})
    r.status = "dismissed"
    r.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return _shape_result(r)


# ─────────────────────────────────────────
# BULK CONVERT/DISMISS — batch triage for the Inbox view.
#
# /admin/inbox groups enriched captures by ICP tier and offers
# "convert all HOT" / "dismiss all SKIP" so a user can clear a 50-row
# batch in two clicks instead of fifty.
# ─────────────────────────────────────────
class BulkResultActionBody(BaseModel):
    ids: List[str]
    action: str  # "convert" | "dismiss" | "restore"
    force: bool = False  # convert-without-enrichment override; default off


@router.post("/scrapers/results/bulk")
async def bulk_scraper_result_action(
    body: BulkResultActionBody,
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("convert", "dismiss", "restore"):
        raise HTTPException(status_code=422, detail={
            "code": "bad_action",
            "message": f"action must be 'convert', 'dismiss', or 'restore'; got {body.action!r}",
        })
    if not body.ids or len(body.ids) > 200:
        raise HTTPException(status_code=422, detail={
            "code": "bad_ids",
            "message": "ids must be 1..200 entries",
        })
    try:
        rids = [uuid.UUID(s) for s in body.ids]
    except ValueError:
        raise HTTPException(status_code=422, detail={"code": "bad_id", "message": "non-uuid id"})

    rows = (await db.execute(
        select(ScraperResult).where(
            ScraperResult.id.in_(rids),
            ScraperResult.tenant_id == _tenant(),
        ).with_for_update()
    )).scalars().all()
    by_id = {r.id: r for r in rows}

    affected = 0
    skipped = 0
    new_lead_ids: list[str] = []
    now = datetime.now(timezone.utc)

    if body.action == "dismiss":
        for rid in rids:
            r = by_id.get(rid)
            if not r:
                skipped += 1
                continue
            if r.status in ("converted", "dismissed"):
                skipped += 1
                continue
            r.status = "dismissed"
            r.reviewed_at = now
            affected += 1
        await db.commit()
        return {"action": "dismiss", "affected": affected, "skipped": skipped}

    # action == "restore" — flip dismissed rows back to pending so an
    # accidental bulk-dismiss can be undone. Converted rows are NOT
    # restorable (they minted a Lead) — skip those silently.
    if body.action == "restore":
        for rid in rids:
            r = by_id.get(rid)
            if not r or r.status != "dismissed":
                skipped += 1
                continue
            r.status = "pending"
            r.reviewed_at = None
            affected += 1
        await db.commit()
        return {"action": "restore", "affected": affected, "skipped": skipped}

    # action == "convert" — promote each row to a Lead. Reuses the per-row
    # logic so the lead shape stays identical to single-row converts.
    # Without body.force, mirror the single-convert guard: rows whose
    # enrichment hasn't landed are skipped (not silently default-scored to
    # 50). The per-row skip is preferable to a 422 on the whole batch.
    from automations.trigger_detector import detect_triggers, score_boost_for, MAX_BOOST
    not_enriched = 0
    for rid in rids:
        r = by_id.get(rid)
        if not r or r.status in ("converted", "dismissed") or r.converted_lead_id:
            skipped += 1
            continue
        name = (r.extracted_name or r.extracted_company or "Untitled lead")[:200]
        raw_full = r.raw_data or {}
        enrich = raw_full.get("enrichment") or {}
        if not enrich.get("score") and not body.force:
            not_enriched += 1
            skipped += 1
            continue
        notes_parts: list[str] = []
        if enrich.get("description"):
            notes_parts.append(enrich["description"])
        if enrich.get("tech"):
            notes_parts.append("Tech: " + ", ".join(enrich["tech"][:8]))

        # Detect buying-intent triggers from the scraper signal + enrichment
        # before the row commits. Triggers add a +5/each score boost (cap +15)
        # so a hiring + funded company that scored 70 by ICP becomes 80 — past
        # the "hot" threshold.
        triggers = detect_triggers(
            notes="\n\n".join(notes_parts) or None,
            title=r.extracted_name,
            company_name=r.extracted_company,
            scraper_raw=raw_full,
            enrichment=enrich,
        )
        base_score = enrich.get("score") or r.relevance_score or 50
        boosted = min(100, base_score + score_boost_for(triggers))

        lead = Lead(
            tenant_id=_tenant(),
            name=name,
            email=r.extracted_email or (enrich.get("emails") or [None])[0],
            company_name=r.extracted_company,
            company_domain=enrich.get("domain"),
            linkedin_url=r.extracted_url if (r.extracted_url or "").startswith("https://www.linkedin.com") else None,
            status="new",
            source=f"scraper:{r.source_type}",
            source_ref_id=str(r.id),
            score=boosted,
            score_reason=enrich.get("reason") or "Bulk-promoted from inbox",
            notes="\n\n".join(notes_parts) or None,
            triggers=triggers or None,
        )
        db.add(lead)
        await db.flush()
        r.converted_lead_id = lead.id
        r.status = "converted"
        r.reviewed_at = now
        new_lead_ids.append(str(lead.id))
        affected += 1
    await db.commit()
    return {
        "action": "convert", "affected": affected, "skipped": skipped,
        "not_enriched": not_enriched,  # surfaces "N were skipped waiting on enrichment — retry or force"
        "new_lead_ids": new_lead_ids,
    }


@router.get("/scrapers/{scraper_id}")
async def get_scraper(scraper_id: str, db: AsyncSession = Depends(get_db)):
    try:
        sid = uuid.UUID(scraper_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Scraper not found"})
    item = (await db.execute(
        select(ScraperSource).where(ScraperSource.id == sid,
                                    ScraperSource.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Scraper not found"})
    return _shape_scraper(item)


@router.patch("/scrapers/{scraper_id}")
async def update_scraper(scraper_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    try:
        sid = uuid.UUID(scraper_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Scraper not found"})
    item = (await db.execute(
        select(ScraperSource).where(ScraperSource.id == sid,
                                    ScraperSource.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Scraper not found"})
    if "enabled" in body:
        item.status = "running" if body["enabled"] else "available"
    if "status" in body and body["status"] in ("available", "running", "paused", "failed"):
        item.status = body["status"]
    if "schedule" in body:
        item.schedule = body["schedule"]
    await db.commit()
    await db.refresh(item)
    return _shape_scraper(item)


async def _auto_enrich_recent(tenant_id: uuid.UUID, source_type: str, limit: int = 30) -> None:
    """Fire-and-forget: enrich the freshest pending rows from a source so the
    user sees real ICP scores + descriptions on the staging page within
    seconds, not "tomorrow when cron runs"."""
    try:
        async with SessionLocal() as db:
            rows = (await db.execute(
                select(ScraperResult.id).where(
                    ScraperResult.tenant_id == tenant_id,
                    ScraperResult.source_type == source_type,
                    ScraperResult.status == "pending",
                ).order_by(desc(ScraperResult.scraped_at)).limit(limit)
            )).scalars().all()
        if not rows:
            return
        await enrich_batch(rows, concurrency=5)
    except Exception as e:
        log.warning("auto_enrich_recent failed for %s: %s", source_type, e)


@router.post("/scrapers/{scraper_id}/run")
async def trigger_scraper(
    scraper_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        sid = uuid.UUID(scraper_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Scraper not found"})
    item = (await db.execute(
        select(ScraperSource).where(ScraperSource.id == sid,
                                    ScraperSource.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Scraper not found"})

    # Run the real scraper if we have a handler for this source key; otherwise
    # fall back to the no-op heartbeat (so the button still feels live for
    # sources we haven't implemented yet).
    item.status = "running"
    item.last_run_at = datetime.now(timezone.utc)
    await db.commit()

    result = await execute_scraper(item.source_key, _tenant())

    item.last_run_at = datetime.now(timezone.utc)
    if result.get("ran"):
        inserted = int(result.get("inserted") or 0)
        item.leads_last_run = inserted
        item.leads_total = (item.leads_total or 0) + inserted
        item.status = "running"  # ready for the next sweep
    else:
        item.status = "failed"
        item.note = (item.note or "") + f" · last error: {result.get('error', '')[:80]}"
    await db.commit()

    # Auto-enrich the fresh rows in the background. The user sees results in
    # the staging UI within ~10-30s without having to click a separate
    # "enrich now" button.
    if result.get("ran") and (result.get("inserted") or 0) > 0:
        background_tasks.add_task(_auto_enrich_recent, _tenant(), item.source_key,
                                   int(result.get("inserted") or 0))

    return {
        "job_id": f"job_{uuid.uuid4().hex[:12]}",
        "scraper_id": scraper_id,
        "enqueued_at_unix": int(time.time()),
        "status": "completed" if result.get("ran") else "failed",
        "inserted": int(result.get("inserted") or 0),
        "error": result.get("error"),
    }



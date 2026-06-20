"""
routers/reports.py — M6 Reports REST endpoints (DB-backed).

Reports live in the `reports` table. /generate runs synchronously, computing
real stats from the leads + activity_log + automation_runs tables and
optionally calling LiteLLM to write a short narrative.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from config import settings
from db.connection import get_db
from db.entities import (
    ActivityLog,
    AutomationRun,
    Lead,
    Report,
)

router = APIRouter(
    prefix="/api/reports",
    tags=["Reports"],
    # All endpoints require an admin session — including /generate which
    # spends LLM credits.
    dependencies=[Depends(require_admin)],
)
log = logging.getLogger("smartbiz.reports")


def _ts(dt: Optional[datetime]) -> Optional[int]:
    return int(dt.timestamp()) if dt else None


def _tenant() -> uuid.UUID:
    return uuid.UUID(settings.default_tenant_id)


def _shape_report(r: Report) -> dict:
    return {
        "id": str(r.id),
        "tenant_id": str(r.tenant_id),
        "kind": r.kind,
        "period_start_unix": _ts(r.period_start),
        "period_end_unix": _ts(r.period_end),
        "stats": r.stats or {},
        "narrative": r.narrative or "",
        "headline": r.headline or "",
        "prompt_version": r.prompt_version,
        "model": r.model,
        "generated_at_unix": _ts(r.generated_at),
        "has_embedding": bool(r.has_embedding),
    }


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────

@router.get("")
async def list_reports(
    cursor: Optional[str] = None,
    limit: int = Query(default=25, le=100),
    kind: Optional[str] = None,
    period_start_after: Optional[int] = None,
    period_end_before: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Report).where(Report.tenant_id == _tenant())
    if kind:
        stmt = stmt.where(Report.kind == kind)
    if period_start_after is not None:
        stmt = stmt.where(Report.period_start >= datetime.fromtimestamp(period_start_after, tz=timezone.utc))
    if period_end_before is not None:
        stmt = stmt.where(Report.period_end <= datetime.fromtimestamp(period_end_before, tz=timezone.utc))
    stmt = stmt.order_by(desc(Report.period_end)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_shape_report(r) for r in rows], "next_cursor": None}


@router.get("/latest")
async def latest_report(kind: str = "weekly", db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(Report)
        .where(Report.tenant_id == _tenant(), Report.kind == kind)
        .order_by(desc(Report.period_end)).limit(1)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"code": "not_found",
                            "message": "No report of that kind"})
    return _shape_report(row)


@router.get("/compare")
async def compare_reports(a: str, b: str, db: AsyncSession = Depends(get_db)):
    try:
        a_id, b_id = uuid.UUID(a), uuid.UUID(b)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found",
                            "message": "One or both reports not found"})
    rows = (await db.execute(
        select(Report).where(Report.id.in_([a_id, b_id]),
                             Report.tenant_id == _tenant())
    )).scalars().all()
    by_id = {str(r.id): r for r in rows}
    ra, rb = by_id.get(a), by_id.get(b)
    if not ra or not rb:
        raise HTTPException(status_code=404, detail={"code": "not_found",
                            "message": "One or both reports not found"})
    return {"a": _shape_report(ra), "b": _shape_report(rb)}


# ─────────────────────────────────────────
# Live analytics — source ROI + sequence performance.
# These are NOT period-bounded reports; they answer the two questions
# every paying SDR asks in their first week:
#   1. Which sources convert? (Source ROI)
#   2. Which sequences/templates get replies? (Sequence perf)
# Pure SQL aggregation, fast enough to render on the Reports page.
# ─────────────────────────────────────────

@router.get("/source-roi")
async def source_roi(db: AsyncSession = Depends(get_db)):
    """Aggregate replies + conversions per scraper source.

    Returns rows like:
       {source, lead_count, hot_count, replied_count, reply_rate}
    The reply_rate is replied_total / lead_count (cohort over the entire
    history of that source — gives the user a cumulative answer rather
    than a noisy 7-day window). Sorted by replied_count desc so the
    high-signal sources are first.
    """
    from db.entities import Lead
    rows = (await db.execute(
        select(
            Lead.source,
            sql_func.count().label("leads"),
            sql_func.count().filter(Lead.score >= 80).label("hot"),
            sql_func.count().filter(Lead.sequence_state == "paused_replied").label("replied"),
        ).where(
            Lead.tenant_id == _tenant(),
            Lead.deleted_at == None,  # noqa: E711
        ).group_by(Lead.source)
    )).all()
    items = []
    for source, leads, hot, replied in rows:
        items.append({
            "source": source or "(none)",
            "lead_count": int(leads or 0),
            "hot_count": int(hot or 0),
            "replied_count": int(replied or 0),
            "reply_rate": round((replied or 0) / leads, 4) if leads else 0.0,
        })
    items.sort(key=lambda x: (x["replied_count"], x["hot_count"], x["lead_count"]), reverse=True)
    return {"items": items}


@router.get("/sequence-performance")
async def sequence_performance(db: AsyncSession = Depends(get_db)):
    """Per-template send/reply numbers from automation_runs + leads.

    For each template:
      - runs_total       = automation_runs count
      - sends_total      = automation_events with step_name='send_day0' & outcome='sent'
      - replied_total    = leads tied to runs whose sequence_state='paused_replied'
      - reply_rate       = replied / sends
      - skipped_replied  = runs short-circuited because the lead replied
                           before send (the reply-pause guard's wins)
    """
    from db.entities import (
        AutomationRun, AutomationEvent, AutomationTemplate, Lead,
    )

    # AutomationTemplate has no tenant_id — templates are shared across
    # tenants. Per-tenant scoping happens on AutomationRun (which IS
    # tenant-scoped) inside each per-template count below.
    tpl_rows = (await db.execute(
        select(AutomationTemplate.id, AutomationTemplate.key,
               AutomationTemplate.name)
    )).all()
    items: list[dict] = []
    tenant = _tenant()

    for tpl_id, tpl_key, tpl_name in tpl_rows:
        runs_total = (await db.execute(
            select(sql_func.count()).select_from(
                select(AutomationRun.id).where(
                    AutomationRun.tenant_id == tenant,
                    AutomationRun.template_id == tpl_id,
                ).subquery()
            )
        )).scalar_one() or 0

        sends_total = (await db.execute(
            select(sql_func.count()).select_from(
                select(AutomationEvent.id)
                .join(AutomationRun, AutomationEvent.run_id == AutomationRun.id)
                .where(
                    AutomationRun.tenant_id == tenant,
                    AutomationRun.template_id == tpl_id,
                    AutomationEvent.step_name == "send_day0",
                    AutomationEvent.outcome == "sent",
                ).subquery()
            )
        )).scalar_one() or 0

        skipped_replied = (await db.execute(
            select(sql_func.count()).select_from(
                select(AutomationEvent.id)
                .join(AutomationRun, AutomationEvent.run_id == AutomationRun.id)
                .where(
                    AutomationRun.tenant_id == tenant,
                    AutomationRun.template_id == tpl_id,
                    AutomationEvent.outcome == "skipped_replied",
                ).subquery()
            )
        )).scalar_one() or 0

        replied_total = (await db.execute(
            select(sql_func.count()).select_from(
                select(Lead.id)
                .join(AutomationRun, AutomationRun.lead_id == Lead.id)
                .where(
                    Lead.tenant_id == tenant,
                    AutomationRun.template_id == tpl_id,
                    Lead.sequence_state == "paused_replied",
                ).distinct().subquery()
            )
        )).scalar_one() or 0

        items.append({
            "template_id": str(tpl_id),
            "template_key": tpl_key,
            "template_name": tpl_name or tpl_key,
            "runs_total": int(runs_total),
            "sends_total": int(sends_total),
            "replied_total": int(replied_total),
            "skipped_replied": int(skipped_replied),
            "reply_rate": round(replied_total / sends_total, 4) if sends_total else 0.0,
        })

    items.sort(key=lambda x: (x["replied_total"], x["sends_total"]), reverse=True)
    return {"items": items}


@router.get("/{report_id}")
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)):
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Report not found"})
    row = (await db.execute(
        select(Report).where(Report.id == rid, Report.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Report not found"})
    return _shape_report(row)


# ─────────────────────────────────────────
# Real generation: aggregates DB stats, optionally narrates with LiteLLM.
# ─────────────────────────────────────────

async def _aggregate_stats(db: AsyncSession, period_start: datetime, period_end: datetime) -> dict:
    tenant = _tenant()

    # New leads in window.
    new_leads_count = (await db.execute(
        select(func.count(Lead.id)).where(
            Lead.tenant_id == tenant,
            Lead.deleted_at.is_(None),
            Lead.created_at >= period_start,
            Lead.created_at < period_end,
        )
    )).scalar() or 0

    # Hot count = leads with score >= 75 in window.
    hot_count = (await db.execute(
        select(func.count(Lead.id)).where(
            Lead.tenant_id == tenant,
            Lead.deleted_at.is_(None),
            Lead.created_at >= period_start,
            Lead.created_at < period_end,
            Lead.score >= 75,
        )
    )).scalar() or 0

    # Median score (rough — Postgres percentile_cont).
    median_row = (await db.execute(
        select(func.percentile_cont(0.5).within_group(Lead.score.asc()))
        .where(Lead.tenant_id == tenant, Lead.deleted_at.is_(None),
               Lead.created_at >= period_start, Lead.created_at < period_end)
    )).scalar()
    median_score = int(median_row) if median_row is not None else 0

    # Sources breakdown.
    src_rows = (await db.execute(
        select(Lead.source, func.count(Lead.id))
        .where(Lead.tenant_id == tenant, Lead.deleted_at.is_(None),
               Lead.created_at >= period_start, Lead.created_at < period_end)
        .group_by(Lead.source).order_by(desc(func.count(Lead.id)))
    )).all()
    sources = [{"source": (s or "manual"), "count": c} for s, c in src_rows]

    # Trailing 8-week history of new-leads counts (for the bar series).
    history: list[int] = []
    for i in range(8, 0, -1):
        wk_end = period_end - timedelta(days=(i - 1) * 7)
        wk_start = wk_end - timedelta(days=7)
        c = (await db.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant, Lead.deleted_at.is_(None),
                Lead.created_at >= wk_start, Lead.created_at < wk_end,
            )
        )).scalar() or 0
        history.append(int(c))

    # Automation runs in window.
    runs_total = (await db.execute(
        select(func.count(AutomationRun.id)).where(
            AutomationRun.tenant_id == tenant,
            AutomationRun.started_at >= period_start,
            AutomationRun.started_at < period_end,
        )
    )).scalar() or 0
    runs_failed = (await db.execute(
        select(func.count(AutomationRun.id)).where(
            AutomationRun.tenant_id == tenant,
            AutomationRun.started_at >= period_start,
            AutomationRun.started_at < period_end,
            AutomationRun.status == "failed",
        )
    )).scalar() or 0

    # Reply rate proxy: openings counted via activity_log action_type='email_opened'.
    opens = (await db.execute(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.tenant_id == tenant,
            ActivityLog.action_type == "email_opened",
            ActivityLog.created_at >= period_start,
            ActivityLog.created_at < period_end,
        )
    )).scalar() or 0
    sends = (await db.execute(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.tenant_id == tenant,
            ActivityLog.action_type == "email_sent",
            ActivityLog.created_at >= period_start,
            ActivityLog.created_at < period_end,
        )
    )).scalar() or 0
    reply_rate = round(opens / sends, 4) if sends else 0.0

    return {
        "leads": {
            "new_leads_count": int(new_leads_count),
            "hot_count": int(hot_count),
            "median_score": median_score,
            "sources": sources,
            "history": history,
        },
        "automations": {
            "reply_rate": reply_rate,
            "runs_total": int(runs_total),
            "runs_failed": int(runs_failed),
        },
        "forecast": None,
    }


def _format_headline(stats: dict) -> str:
    leads = stats.get("leads") or {}
    autos = stats.get("automations") or {}
    new_count = leads.get("new_leads_count", 0)
    hot = leads.get("hot_count", 0)
    rate = autos.get("reply_rate") or 0.0
    return f"{new_count} new leads, {hot} hot — reply rate {rate * 100:.1f}%."


async def _narrate(stats: dict, period_start: datetime, period_end: datetime) -> str:
    """Best-effort LLM narrative — falls back to a deterministic summary."""
    fallback = (
        f"Period {period_start.date()} → {period_end.date()}: "
        f"{stats['leads']['new_leads_count']} new leads "
        f"({stats['leads']['hot_count']} hot). "
        f"Median lead score {stats['leads']['median_score']}. "
        f"Automation runs: {stats['automations']['runs_total']} total, "
        f"{stats['automations']['runs_failed']} failed. "
        f"Reply rate {stats['automations']['reply_rate'] * 100:.1f}%."
    )
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        return fallback
    try:
        from lara_smartbiz.utils.llm import complete_text
        prompt = (
            "You are a no-fluff revops analyst. Write a 2-paragraph weekly business "
            "summary using ONLY the JSON stats provided. Be specific, no filler.\n\n"
            f"Period: {period_start.date()} → {period_end.date()}\n"
            f"Stats JSON: {stats}"
        )
        text = await complete_text(prompt, temperature=0.4, max_output_tokens=350)
        return (text or fallback).strip()
    except Exception as e:
        log.warning("narrate fallback (%s)", e)
        return fallback


@router.post("/generate", status_code=201)
async def generate_report(body: dict, db: AsyncSession = Depends(get_db)):
    body = body or {}
    kind = body.get("kind", "weekly")
    if kind not in {"weekly", "daily", "monthly", "custom"}:
        raise HTTPException(status_code=422, detail={"code": "validation_failed",
                            "message": "Invalid kind"})

    sa = body.get("period_start_unix")
    eb = body.get("period_end_unix")
    if not sa or not eb or sa >= eb:
        raise HTTPException(status_code=422, detail={"code": "validation_failed",
                            "message": "period_start_unix and period_end_unix required (start < end)"})

    period_start = datetime.fromtimestamp(sa, tz=timezone.utc)
    period_end = datetime.fromtimestamp(eb, tz=timezone.utc)

    stats = await _aggregate_stats(db, period_start, period_end)
    narrative = await _narrate(stats, period_start, period_end)
    headline = _format_headline(stats)

    report = Report(
        tenant_id=_tenant(), kind=kind,
        period_start=period_start, period_end=period_end,
        headline=headline, narrative=narrative,
        stats=stats, prompt_version="v1",
        model=os.getenv("LARA_MODEL", "gemini/gemini-2.5-flash"),
        has_embedding=False,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return {
        "id": str(report.id),
        "report_id": str(report.id),
        "kind": kind,
        "status": "completed",
        "report": _shape_report(report),
    }

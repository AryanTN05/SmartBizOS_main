"""
routers/automations.py — M3 Automation Engine REST endpoints.

DB-backed: templates / runs / events all live in Postgres. Starting a run
synchronously inserts an automation_runs row, then fires an Inngest event
(`lead.nurture.start`) — the durable function in inngest_app/functions.py
appends to automation_events as each step completes.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin

from db.connection import get_db
from db.entities import (
    AutomationEvent,
    AutomationRun,
    AutomationTemplate,
    Lead,
)
from config import settings

router = APIRouter(
    prefix="/api/automations",
    tags=["Automations"],
    # All endpoints in this router require an admin session. Adding the dep
    # at router level (not per-handler) means new endpoints can't be added
    # without auth by accident.
    dependencies=[Depends(require_admin)],
)
log = logging.getLogger("smartbiz.automations")


def _ts(dt: Optional[datetime]) -> Optional[int]:
    return int(dt.timestamp()) if dt else None


def _tenant() -> uuid.UUID:
    return uuid.UUID(settings.default_tenant_id)


_CHANNELS = [
    {"name": "email",    "status": "active", "provider": "resend",
     "capabilities": ["send", "track_opens", "track_clicks", "webhook_inbound"], "note": None},
    {"name": "whatsapp", "status": "stub",   "provider": "stub",
     "capabilities": ["send_stub"],
     "note": "WhatsApp Business Cloud API adapter scoped; contact team to enable"},
    {"name": "linkedin", "status": "stub",   "provider": "stub",
     "capabilities": ["send_stub"],
     "note": "PhantomBuster / HeyReach integration pitched; manual onboarding required"},
    {"name": "sms",      "status": "stub",   "provider": "stub",
     "capabilities": ["send_stub"],
     "note": "Twilio adapter ready; plug in customer account SID to enable"},
]


def _template_summary(t: AutomationTemplate) -> dict:
    return {
        "id": str(t.id), "key": t.key, "name": t.name,
        "step_count": t.step_count, "channels_used": list(t.channels_used or []),
    }


def _template_full(t: AutomationTemplate) -> dict:
    return {
        "id": str(t.id), "key": t.key, "name": t.name,
        "description": t.description, "version": t.version, "status": t.status,
        "step_count": t.step_count, "channels_used": list(t.channels_used or []),
        "created_at_unix": _ts(t.created_at),
    }


def _run_dict(r: AutomationRun) -> dict:
    return {
        "id": str(r.id),
        "lead_id": str(r.lead_id) if r.lead_id else None,
        "template_id": str(r.template_id) if r.template_id else None,
        "template_key": r.template_key,
        "inngest_run_id": r.inngest_event_id,
        "status": r.status,
        "started_at_unix": _ts(r.started_at),
        "completed_at_unix": _ts(r.completed_at),
        "current_step_name": r.current_step_name,
        "next_fire_at_unix": _ts(r.next_fire_at),
        "created_by": r.created_by,
    }


def _event_dict(ev: AutomationEvent) -> dict:
    return {
        "id": str(ev.id),
        "run_id": str(ev.run_id),
        "step_name": ev.step_name,
        "channel": ev.channel,
        "outcome": ev.outcome,
        "occurred_at_unix": _ts(ev.occurred_at),
        "payload": ev.payload or {},
    }


def _lead_snapshot(lead: Optional[Lead], lead_id: Optional[uuid.UUID]) -> dict:
    if not lead:
        return {
            "id": str(lead_id) if lead_id else "",
            "first_name": "Unknown", "last_name": "", "email": "",
            "company": None, "segment": None,
        }
    parts = (lead.name or "").strip().split(maxsplit=1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return {
        "id": str(lead.id),
        "first_name": first, "last_name": last,
        "email": lead.email or "", "company": lead.company_name,
        "segment": "warm" if (lead.score or 0) >= 60 else "cold",
    }


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────

@router.get("/runs")
async def list_runs(
    cursor: Optional[str] = None,
    limit: int = Query(default=25, le=100),
    status: Optional[str] = None,
    template_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AutomationRun).where(AutomationRun.tenant_id == _tenant())
    if status:
        stmt = stmt.where(AutomationRun.status == status)
    if template_id:
        try:
            stmt = stmt.where(AutomationRun.template_id == uuid.UUID(template_id))
        except ValueError:
            pass
    if lead_id:
        try:
            stmt = stmt.where(AutomationRun.lead_id == uuid.UUID(lead_id))
        except ValueError:
            pass
    stmt = stmt.order_by(desc(AutomationRun.started_at)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    # Batch-resolve lead names so the list UI shows "Priya Krishnan · Rupee.co"
    # instead of raw UUIDs (avoids N+1 fetches from the frontend).
    lead_ids = {r.lead_id for r in rows if r.lead_id}
    leads_by_id: dict[uuid.UUID, Lead] = {}
    if lead_ids:
        lead_rows = (await db.execute(
            select(Lead).where(Lead.id.in_(lead_ids))
        )).scalars().all()
        leads_by_id = {l.id: l for l in lead_rows}

    items = []
    for r in rows:
        d = _run_dict(r)
        if r.lead_id and r.lead_id in leads_by_id:
            l = leads_by_id[r.lead_id]
            d["lead_name"] = l.name
            d["lead_company"] = l.company_name
            d["_lead_display"] = l.name or l.email or ""
        items.append(d)
    return {"items": items, "next_cursor": None}


@router.post("/runs", status_code=201)
async def start_run(body: dict, db: AsyncSession = Depends(get_db)):
    lead_id_str = body.get("lead_id")
    template_id_str = body.get("template_id")
    if not lead_id_str or not template_id_str:
        raise HTTPException(status_code=422, detail={"code": "validation_failed",
                            "message": "lead_id and template_id are required"})
    try:
        template_uuid = uuid.UUID(template_id_str)
    except ValueError:
        raise HTTPException(status_code=422, detail={"code": "validation_failed",
                            "message": "template_id must be a UUID"})

    template = (await db.execute(
        select(AutomationTemplate).where(AutomationTemplate.id == template_uuid)
    )).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail={"code": "not_found",
                            "message": "Template not found"})

    lead_uuid: Optional[uuid.UUID] = None
    try:
        lead_uuid = uuid.UUID(lead_id_str)
    except ValueError:
        pass

    # Send-time optimization: if the workspace has it enabled, snap the
    # initial fire to the prospect's likely 9-11 AM local window instead
    # of NOW. Default off — flag in workspace_settings.send_time_optimization.
    fire_at = datetime.now(timezone.utc)
    try:
        from db.entities import WorkspaceSettings, Lead as LeadEntity
        ws = (await db.execute(
            select(WorkspaceSettings).where(WorkspaceSettings.tenant_id == _tenant())
        )).scalar_one_or_none()
        if ws and ws.send_time_optimization and lead_uuid:
            lead_row = (await db.execute(
                select(LeadEntity).where(LeadEntity.id == lead_uuid)
            )).scalar_one_or_none()
            if lead_row:
                from automations.send_time import next_send_window
                fire_at = next_send_window(
                    email=lead_row.email,
                    company_domain=lead_row.company_domain,
                )
    except Exception:
        # Heuristic only — never block run creation on TZ math.
        fire_at = datetime.now(timezone.utc)

    # Insert with next_fire_at as computed (NOW or scheduled). All step
    # state lives in the DB — no in-process work to do here.
    run = AutomationRun(
        tenant_id=_tenant(),
        lead_id=lead_uuid,
        template_id=template.id,
        template_key=template.key,
        status="running",
        current_step_name=None,
        next_fire_at=fire_at,
        created_by=body.get("created_by") or "admin:demo",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return {"run": _run_dict(run)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Run not found"})

    run = (await db.execute(
        select(AutomationRun).where(AutomationRun.id == run_uuid,
                                    AutomationRun.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Run not found"})

    events = (await db.execute(
        select(AutomationEvent)
        .where(AutomationEvent.run_id == run.id)
        .order_by(AutomationEvent.occurred_at)
    )).scalars().all()

    template = None
    if run.template_id:
        template = (await db.execute(
            select(AutomationTemplate).where(AutomationTemplate.id == run.template_id)
        )).scalar_one_or_none()

    lead = None
    if run.lead_id:
        lead = (await db.execute(
            select(Lead).where(Lead.id == run.lead_id)
        )).scalar_one_or_none()

    return {
        "run": _run_dict(run),
        "events": [_event_dict(e) for e in events],
        "lead": _lead_snapshot(lead, run.lead_id),
        "template": _template_summary(template) if template else None,
    }


@router.post("/runs/{run_id}/pause")
async def pause_run(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Run not found"})
    run = (await db.execute(
        select(AutomationRun).where(AutomationRun.id == run_uuid,
                                    AutomationRun.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Run not found"})
    if run.status != "running":
        raise HTTPException(status_code=422, detail={"code": "validation_failed",
                            "message": "Run is not running",
                            "details": {"reason": "not_pausable"}})
    run.status = "paused"
    run.next_fire_at = None  # scheduler skips paused runs
    db.add(AutomationEvent(run_id=run.id, step_name="pause",
                           outcome="paused_by_user", payload={"by": "admin"}))
    await db.commit()
    await db.refresh(run)
    return _run_dict(run)


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Run not found"})
    run = (await db.execute(
        select(AutomationRun).where(AutomationRun.id == run_uuid,
                                    AutomationRun.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Run not found"})
    if run.status != "paused":
        raise HTTPException(status_code=422, detail={"code": "validation_failed",
                            "message": "Run is not paused"})
    run.status = "running"
    run.next_fire_at = datetime.now(timezone.utc)  # scheduler picks up on next tick
    db.add(AutomationEvent(run_id=run.id, step_name="resume",
                           outcome="resumed_by_user", payload={"by": "admin"}))
    await db.commit()
    await db.refresh(run)
    return _run_dict(run)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Run not found"})
    run = (await db.execute(
        select(AutomationRun).where(AutomationRun.id == run_uuid,
                                    AutomationRun.tenant_id == _tenant())
    )).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Run not found"})
    if run.status not in ("running", "paused"):
        raise HTTPException(status_code=422, detail={"code": "validation_failed",
                            "message": "Run is in a terminal state"})
    run.status = "cancelled"
    run.completed_at = datetime.now(timezone.utc)
    run.next_fire_at = None
    db.add(AutomationEvent(run_id=run.id, step_name="cancel",
                           outcome="cancelled_by_user", payload={"by": "admin"}))
    await db.commit()
    await db.refresh(run)
    return _run_dict(run)


@router.get("/templates")
async def list_templates(response: Response, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(AutomationTemplate).order_by(AutomationTemplate.created_at)
    )).scalars().all()
    response.headers["Cache-Control"] = "private, max-age=120"
    return {"items": [_template_full(t) for t in rows]}


@router.get("/templates/{template_id}")
async def get_template(template_id: str, db: AsyncSession = Depends(get_db)):
    try:
        tpl_uuid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Template not found"})
    template = (await db.execute(
        select(AutomationTemplate).where(AutomationTemplate.id == tpl_uuid)
    )).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Template not found"})
    return {
        "template": _template_full(template),
        "steps": template.steps or [],
        "placeholder_schema": list(template.placeholder_schema or []),
        "previews": template.previews or [],
    }


@router.get("/channels")
async def list_channels(response: Response):
    response.headers["Cache-Control"] = "private, max-age=300"
    return {"items": _CHANNELS}


# ─────────────────────────────────────────
# Run-counts summary used by the Home headline ("X failed runs · 24h")
# ─────────────────────────────────────────

@router.get("/runs/stats/summary")
async def runs_summary(db: AsyncSession = Depends(get_db)):
    cutoff = datetime.fromtimestamp(time.time() - 86400, tz=timezone.utc)
    rows = (await db.execute(
        select(AutomationRun.status)
        .where(AutomationRun.tenant_id == _tenant(),
               AutomationRun.started_at >= cutoff)
    )).scalars().all()
    counts: dict[str, int] = {}
    for s in rows:
        counts[s] = counts.get(s, 0) + 1
    return {"window_seconds": 86400, "by_status": counts, "total": len(rows)}

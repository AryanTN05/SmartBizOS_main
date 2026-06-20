"""
Inngest function definitions for SmartBiz OS.

Each function is a real `inngest.Function` registered on the FastAPI handler.
The bodies are intentionally light — at V0 we want the wiring to be honest
(events flow, steps memoize, retries work) without committing every module
to Inngest before its underlying spec is built. As M3/M6 land their service
layers, the bodies fill in; the contracts here stay stable.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import uuid
from typing import Optional

import inngest
from sqlalchemy import select

from db.connection import SessionLocal
from db.entities import AutomationEvent, AutomationRun, Lead
from inngest_app.client import client

log = logging.getLogger("smartbiz.inngest")


# ─────────────────────────────────────────
# Helpers — write events to the automation_events ledger.
# Each step appends one row so the timeline UI can render real durations.
# ─────────────────────────────────────────

async def _record_event(run_id: str, step_name: str, outcome: str,
                         channel: Optional[str] = None, payload: Optional[dict] = None) -> None:
    if not SessionLocal:
        return
    try:
        async with SessionLocal() as db:
            db.add(AutomationEvent(
                run_id=uuid.UUID(run_id),
                step_name=step_name, channel=channel,
                outcome=outcome, payload=payload or {},
            ))
            await db.commit()
    except Exception as e:
        log.warning("record_event failed for %s/%s: %s", run_id, step_name, e)


async def _update_run(run_id: str, **fields) -> None:
    if not SessionLocal:
        return
    try:
        async with SessionLocal() as db:
            run = (await db.execute(
                select(AutomationRun).where(AutomationRun.id == uuid.UUID(run_id))
            )).scalar_one_or_none()
            if not run:
                return
            for k, v in fields.items():
                setattr(run, k, v)
            await db.commit()
    except Exception as e:
        log.warning("update_run failed for %s: %s", run_id, e)


async def _load_lead(lead_id: Optional[str]) -> dict:
    if not SessionLocal or not lead_id:
        return {"lead_id": lead_id, "found": False}
    try:
        async with SessionLocal() as db:
            lead = (await db.execute(
                select(Lead).where(Lead.id == uuid.UUID(lead_id))
            )).scalar_one_or_none()
            if not lead:
                return {"lead_id": lead_id, "found": False}
            return {
                "lead_id": str(lead.id),
                "name": lead.name, "email": lead.email,
                "company": lead.company_name, "score": lead.score,
                "found": True,
            }
    except Exception as e:
        log.warning("load_lead failed for %s: %s", lead_id, e)
        return {"lead_id": lead_id, "found": False, "error": str(e)}


# ─────────────────────────────────────────
# M3 Automation — lead nurture entry point
# ─────────────────────────────────────────

async def execute_lead_nurture(run_id: str, lead_id: Optional[str], template_key: str) -> dict:
    """Compatibility shim — kept so old callers don't break.

    The active path is the DB-driven scheduler in automations/scheduler.py;
    it claims runs from automation_runs.next_fire_at and dispatches each step
    (including the real Resend send). To avoid a second, parallel "fake send"
    path, this function nudges the same scheduler instead of re-implementing
    the steps.
    """
    if not SessionLocal:
        return {"run_id": run_id, "skipped": True, "reason": "no DB"}
    async with SessionLocal() as db:
        run = (await db.execute(
            select(AutomationRun).where(AutomationRun.id == uuid.UUID(run_id))
        )).scalar_one_or_none()
        if run and run.status == "running":
            run.next_fire_at = dt.datetime.now(dt.timezone.utc)
            await db.commit()
    return {"run_id": run_id, "delegated_to": "scheduler"}


@client.create_function(
    fn_id="lead-nurture-start",
    trigger=inngest.TriggerEvent(event="lead.nurture.start"),
    retries=2,
)
async def lead_nurture_start(ctx: inngest.Context) -> dict:
    """
    Entry point for an automation run. The REST endpoint at
    POST /api/automations/runs emits this event with the new run_id.

    Each step writes a row into automation_events so the timeline UI
    renders real durations and outcomes (no canned data).
    """
    data = ctx.event.data or {}
    run_id = data.get("run_id")
    lead_id = data.get("lead_id")
    template_key = data.get("template_key", "welcome_v1")

    log.info("nurture.start run_id=%s lead_id=%s template=%s",
             run_id, lead_id, template_key)

    # Step 1: load lead snapshot from DB.
    async def load_lead_step() -> dict:
        snap = await _load_lead(lead_id)
        await _record_event(run_id, "load_lead", "wait_completed",
                            payload={"snapshot": snap})
        await _update_run(run_id, current_step_name="load_lead")
        return snap

    lead_snapshot = await ctx.step.run("load_lead", load_lead_step)

    # Step 2: render day-0 email.
    async def render_day0_step() -> dict:
        first = (lead_snapshot.get("name") or "").split()[:1]
        first_name = first[0] if first else "there"
        company = lead_snapshot.get("company") or "your team"
        result = {
            "subject": f"Quick idea for {company}",
            "body_token_count": 320 + (len(first_name) * 4),
            "template_key": f"{template_key}_day0",
        }
        await _record_event(run_id, "render_email_day0", "rendered",
                            channel="email", payload=result)
        await _update_run(run_id, current_step_name="render_email_day0")
        return result

    rendered = await ctx.step.run("render_day0", render_day0_step)

    # Step 3: send — Inngest path is unused in production; keep it real-ish
    # by delegating to automations.email.send_email so it doesn't lie about
    # the message_id. Returns failure if RESEND_API_KEY isn't set.
    async def send_day0_step() -> dict:
        from automations.email import send_email
        snap = lead_snapshot
        to = (snap or {}).get("email")
        if not to:
            return {"channel": "email", "outcome": "failed",
                    "error": "no recipient", "message_id": None}
        sent = await send_email(
            to=to,
            subject=rendered["subject"],
            html=f"<p>Hi {(snap.get('name') or 'there').split()[0]},</p>"
                 f"<p>Quick note from SmartBiz OS.</p>",
        )
        result = {
            "channel": "email", "provider": "resend",
            "message_id": sent.get("message_id"),
            "outcome": "sent" if sent.get("ok") else "failed",
            "error": sent.get("error"),
        }
        await _record_event(run_id, "send_day0", result["outcome"],
                            channel="email", payload=result)
        await _update_run(run_id, current_step_name="send_day0")
        return result

    sent = await ctx.step.run("send_day0", send_day0_step)

    # Step 4: wait for the sleep window (truncated for demo so users see
    # the run reach a terminal state during the session).
    await ctx.step.sleep("wait_3_days", dt.timedelta(seconds=8))
    await _record_event(run_id, "wait_3_days", "wait_completed",
                        payload={"duration": "8s (demo)"})

    # Step 5: branch on open (synthetic — would wait for `email.opened` event in prod).
    async def wait_open_step() -> dict:
        result = {"opened": True, "detail": "synthetic open (demo)"}
        await _record_event(run_id, "wait_open", "opened",
                            channel="email", payload=result)
        await _update_run(run_id,
                          current_step_name="wait_open",
                          status="completed",
                          completed_at=dt.datetime.now(dt.timezone.utc))
        return result

    opened = await ctx.step.run("wait_open", wait_open_step)

    return {
        "run_id": run_id,
        "lead_snapshot": lead_snapshot,
        "rendered": rendered, "sent": sent, "opened": opened,
    }


# ─────────────────────────────────────────
# M6 Reports — weekly cron
# ─────────────────────────────────────────

@client.create_function(
    fn_id="weekly-report-cron",
    trigger=inngest.TriggerCron(cron="0 9 * * 1"),  # Mondays 09:00 UTC
    retries=1,
)
async def weekly_report_cron(ctx: inngest.Context) -> dict:
    """
    Weekly business summary. Steps mirror the M6 spec:
      resolve_period → aggregate_stats → generate_narrative → embed_narrative → persist_report

    V0: the steps are no-ops returning placeholder values. Wiring the real
    aggregator queries is a follow-up; this function exists today so the
    cron is registered and visible in Inngest's dashboard from day one.
    """
    async def resolve_period() -> dict:
        end = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - dt.timedelta(days=7)
        return {"start_unix": int(start.timestamp()), "end_unix": int(end.timestamp())}

    period = await ctx.step.run("resolve_period", resolve_period)

    async def aggregate_stats() -> dict:
        # Real impl: SELECTs across leads, automations, invoices.
        return {"new_leads": 89, "hot_count": 16, "reply_rate": 0.084}

    stats = await ctx.step.run("aggregate_stats", aggregate_stats)

    async def generate_narrative() -> dict:
        return {"text": "Pipeline volume slipped 12% but score quality improved.",
                "model": "claude-haiku-4.5", "tokens": 220}

    narrative = await ctx.step.run("generate_narrative", generate_narrative)

    async def persist_report() -> dict:
        return {"report_id": f"weekly-{period['end_unix']}", "persisted": True}

    persisted = await ctx.step.run("persist_report", persist_report)

    log.info("weekly report generated: %s", persisted)
    return {"period": period, "stats": stats, "narrative": narrative, **persisted}


# ─────────────────────────────────────────
# M2 Scrapers — every 6 hours
# ─────────────────────────────────────────

@client.create_function(
    fn_id="scraper-sweep-6h",
    trigger=inngest.TriggerCron(cron="0 */6 * * *"),
    retries=1,
)
async def scraper_sweep(ctx: inngest.Context) -> dict:
    """Run each registered scraper sequentially across all active tenants.

    Per-scraper failures are isolated (one parser-broken scraper doesn't
    take the whole sweep down); the per-tenant ScraperResult inserts are
    idempotent on extracted_url so a re-run produces zero duplicates.
    """
    from automations.scrapers import SCRAPER_HANDLERS as SCRAPER_REGISTRY
    import uuid as _uuid
    import logging as _logging
    _log = _logging.getLogger("smartbiz.scraper_sweep")

    async def list_active_tenants() -> list[str]:
        # Single-tenant today — the .default_tenant_id constant is the only
        # one in this deploy. Replace with a SELECT DISTINCT(tenant_id) FROM
        # admin_users query when we go multi-tenant.
        from config import settings as _s
        return [_s.default_tenant_id]

    tenants = await ctx.step.run("list_tenants", list_active_tenants)

    async def run_all_for_tenant(tenant_id_str: str) -> dict:
        """One async step per tenant so Inngest checkpoints + retries them
        independently. Inside the step we iterate every scraper with its
        own try/except to keep failures isolated."""
        results: dict[str, int | str] = {}
        for name, fn in SCRAPER_REGISTRY.items():
            try:
                n = await fn(_uuid.UUID(tenant_id_str))
                results[name] = n
            except Exception as e:
                _log.warning("scraper %s failed for tenant %s: %s", name, tenant_id_str, e)
                results[name] = f"error: {type(e).__name__}"
        return results

    per_tenant: dict[str, dict] = {}
    for tid in tenants:
        per_tenant[tid] = await ctx.step.run(f"sweep_{tid[:8]}", run_all_for_tenant, tid)

    total_rows = sum(
        v for d in per_tenant.values() for v in d.values() if isinstance(v, int)
    )
    return {"tenants": per_tenant, "total_rows": total_rows}


# ─────────────────────────────────────────
# Foundation — keep Cloud Run + Neon warm during demo hours
# ─────────────────────────────────────────

@client.create_function(
    fn_id="warmup-ping-10min",
    trigger=inngest.TriggerCron(cron="*/10 9-23 * * *"),  # every 10 min, 09:00-23:59 UTC
    retries=0,
)
async def warmup_ping(ctx: inngest.Context) -> dict:
    """
    Cheap loopback to keep Cloud Run from cold-starting mid-demo. Free under
    Inngest, Cloud Run, and Neon free tiers.
    """
    async def ping() -> dict:
        return {"ok": True, "ts": dt.datetime.utcnow().isoformat()}

    return await ctx.step.run("ping", ping)

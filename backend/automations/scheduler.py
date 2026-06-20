"""
DB-driven automation scheduler.

A single asyncio task ticks every TICK_SECONDS, finds runs due to advance,
and runs one step per due run. All state lives in `automation_runs` and
`automation_events` so restarts don't lose anything; pause/cancel are just
status flips that the scheduler skips on the next tick.

State machine for the welcome / cold-outbound / re-engagement templates:

    (start) → load_lead → render_email_day0 → send_day0 → wait_3_days
            → wait_open → (completed)

Each step:
  1. writes one row to automation_events
  2. updates automation_runs.current_step_name
  3. sets automation_runs.next_fire_at to when the next step should run

The wait step is the only one that sets next_fire_at to a future time;
everything else fires "as soon as possible" (next_fire_at = now).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select

from automations.email import send_email
from db.connection import SessionLocal
from db.entities import AutomationEvent, AutomationRun, Lead

log = logging.getLogger("smartbiz.scheduler")


TICK_SECONDS = float(os.getenv("AUTOMATION_TICK_SECONDS", "3"))
# Default to 3 days (real outbound cadence). Dev environments override to a
# small value via AUTOMATION_WAIT_SECONDS=8 in .env so demo runs reach a
# terminal state during a session.
WAIT_SECONDS = int(os.getenv("AUTOMATION_WAIT_SECONDS", str(3 * 86400)))

# Step transitions: maps current_step_name → (next_step_name, advance_delay_s)
# `None` for current_step_name represents the entry point.
STEPS = [
    None,
    "load_lead",
    "render_email_day0",
    "send_day0",
    "wait_3_days",
    "wait_open",
]
# Steps after which we wait `WAIT_SECONDS` before firing the next step.
WAIT_AFTER = {"send_day0"}


def _next_step(current: Optional[str]) -> Optional[str]:
    try:
        idx = STEPS.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(STEPS):
        return None
    return STEPS[idx + 1]


async def _load_lead_snapshot(db, lead_id: Optional[uuid.UUID]) -> dict:
    if not lead_id:
        return {"found": False}
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if not lead:
        return {"found": False, "lead_id": str(lead_id)}

    # A/B variant pick — when the lead has multiple opener variants, the
    # scheduler rotates among them via epsilon-greedy until each has at
    # least 3 sends, then picks the highest-reply-rate. Without variants
    # we just use the singleton opening_line.
    from automations.variant_picker import pick_variant, record_send
    variants = list(lead.opening_line_variants or [])
    chosen_idx = pick_variant(variants) if variants else None
    chosen_opener = lead.opening_line
    if variants and chosen_idx is not None:
        chosen_opener = variants[chosen_idx].get("text") or lead.opening_line
        # Increment sent_count atomically with the snapshot read so that
        # rotation reflects this send. Rollback-safe: if the run fails
        # before commit, the send_count rolls back too.
        lead.opening_line_variants = record_send(variants, chosen_idx)

    return {
        "found": True,
        "lead_id": str(lead.id),
        "tenant_id": str(lead.tenant_id),
        "name": lead.name, "email": lead.email,
        "company": lead.company_name, "score": lead.score,
        "opening_line": chosen_opener,
    }


def _render_email(template_key: str, lead: dict) -> dict:
    """Build the day-0 email body for a given template + lead snapshot.

    When the lead has a saved opening_line we use it as the actual lead-in
    instead of the canned greeting, then keep the rest of the template as
    the value pitch. The canned version is the fallback for leads that
    don't have an opener yet (manual leads, untrigggered scrapers)."""
    first = (lead.get("name") or "").split()[:1]
    first_name = first[0] if first else "there"
    company = lead.get("company") or "your team"
    opener = (lead.get("opening_line") or "").strip()

    subjects = {
        "welcome_v1":      f"Welcome to SmartBiz, {first_name}",
        "cold_outbound_v1": f"Quick idea for {company}",
        "reengagement_v1": "Still on your radar?",
    }

    # Opener-aware bodies. When `opener` is non-empty we use it as the first
    # sentence after the greeting. Otherwise we fall back to a generic
    # template lead-in.
    def _greeting_block() -> str:
        return f"<p>Hi {first_name},</p>"

    def _opener_block() -> str:
        # Opener already includes punctuation/quotes-stripped text from the
        # generator; we render it as plain prose, not styled differently.
        if opener:
            return f"<p>{opener}</p>"
        return ""

    welcome_body = (
        _greeting_block()
        + (f"<p>{opener}</p>" if opener else "")
        + (
            f"<p>Glad you're in. Here's the two workflows most teams plug in first:</p>"
            f"<ul><li>Inbound lead capture from forms / webhooks</li>"
            f"<li>Automated nurture sequences with branching</li></ul>"
            f"<p>Reply if you want a 15-min walkthrough.</p>"
            f"<p>— SmartBiz OS</p>"
        )
    )

    cold_outbound_body = (
        _greeting_block()
        + (
            f"<p>{opener}</p>" if opener else
            f"<p>Noticed {company} is in our ICP — we help teams like yours "
            f"automate sales ops in week one.</p>"
        )
        + (
            f"<p>We help teams like yours automate sales ops in week one. "
            f"Worth a 15-min chat?</p>" if opener else
            f"<p>Worth a 15-min chat?</p>"
        )
        + f"<p>— SmartBiz OS</p>"
    )

    reengagement_body = (
        _greeting_block()
        + (
            f"<p>{opener}</p>" if opener else
            f"<p>It's been a while. Anything changed on your end at {company}?</p>"
        )
        + (
            f"<p>Curious whether anything's shifted on your end — happy to "
            f"reconnect if useful.</p>" if opener else ""
        )
        + f"<p>— SmartBiz OS</p>"
    )

    bodies = {
        "welcome_v1": welcome_body,
        "cold_outbound_v1": cold_outbound_body,
        "reengagement_v1": reengagement_body,
    }
    subject = subjects.get(template_key, f"Hi {first_name}")
    html = bodies.get(template_key, _greeting_block() + _opener_block() +
                      f"<p>Quick note from SmartBiz OS.</p>")

    # Append the unsubscribe footer + List-Unsubscribe headers — required
    # by Google's bulk-sender enforcement (RFC 8058 one-click). Without
    # this, sends route to spam regardless of how good the body is.
    lead_id = lead.get("lead_id")
    tenant_id = lead.get("tenant_id")
    unsub_headers: dict = {}
    if lead_id and tenant_id:
        from automations.suppression import (
            public_unsubscribe_url, list_unsubscribe_headers
        )
        try:
            import uuid as _uuid
            lid = _uuid.UUID(lead_id) if isinstance(lead_id, str) else lead_id
            tid = _uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
            unsub_url = public_unsubscribe_url(lid, tid)
            html = html + (
                f'<p style="font-size:11px;color:#999;margin-top:24px;">'
                f'Don\'t want these? <a href="{unsub_url}" '
                f'style="color:#999;text-decoration:underline;">Unsubscribe</a>.</p>'
            )
            unsub_headers = list_unsubscribe_headers(lid, tid)
        except Exception:
            pass

    return {
        "subject": subject, "html": html,
        "template_key": f"{template_key}_day0",
        "headers": unsub_headers,
        "opener_used": bool(opener),
    }


async def _execute_step(db, run: AutomationRun, step: str) -> tuple[str, dict]:
    """Run one step's side effects. Returns (outcome, payload)."""
    if step == "load_lead":
        snap = await _load_lead_snapshot(db, run.lead_id)
        return "wait_completed", {"snapshot": snap}

    if step == "render_email_day0":
        snap = await _load_lead_snapshot(db, run.lead_id)
        rendered = _render_email(run.template_key, snap)
        return "rendered", {**rendered, "to": snap.get("email")}

    if step == "send_day0":
        # Pull the most recent render event for this run so we send what was
        # rendered (no double-substitution).
        prev = (await db.execute(
            select(AutomationEvent)
            .where(AutomationEvent.run_id == run.id,
                   AutomationEvent.step_name == "render_email_day0")
            .order_by(AutomationEvent.occurred_at.desc()).limit(1)
        )).scalar_one_or_none()
        if not prev or not (prev.payload or {}).get("to"):
            return "failed", {"error": "no rendered email or recipient"}
        p = prev.payload

        # Suppression gate. A bounce / unsubscribe / complaint that landed
        # between render and send must not result in another send. Returns
        # an early-completion outcome so the run lands in a terminal state
        # without firing the email.
        from automations.suppression import is_suppressed
        if await is_suppressed(run.tenant_id, p["to"]):
            return "skipped_suppressed", {
                "to": p["to"],
                "reason": "recipient is on the workspace suppression list",
            }

        headers = (p.get("headers") or {}) if isinstance(p, dict) else {}

        # Multi-mailbox routing: try a tenant SMTP mailbox first (round-robin
        # with daily caps). Fall back to Resend when no mailbox is configured
        # or all are capped — single-domain users keep working unchanged.
        from automations.smtp_email import send_via_mailbox
        smtp_result = await send_via_mailbox(
            tenant_id=run.tenant_id,
            to=p["to"], subject=p["subject"], html=p["html"],
            headers=headers,
        )
        if smtp_result.get("ok"):
            return "sent", {
                "channel": "email", "provider": "smtp",
                "message_id": smtp_result.get("message_id"),
                "mailbox_email": smtp_result.get("mailbox_email"),
                "to": p["to"], "subject": p["subject"],
            }
        # SMTP path returned an actual send failure (not "no mailbox") — do
        # NOT silently fall back to Resend, because that masks the inbox
        # health issue from the SDR.
        if smtp_result.get("code") == "send_failed":
            return "failed", {"channel": "email", "provider": "smtp",
                              "mailbox_email": smtp_result.get("mailbox_email"),
                              "error": smtp_result.get("error"), "to": p["to"]}

        # No mailbox configured / all capped / no Fernet → fall through to Resend.
        result = await send_email(
            to=p["to"], subject=p["subject"], html=p["html"],
            headers=headers,
        )
        if result.get("ok"):
            return "sent", {
                "channel": "email", "provider": "resend",
                "message_id": result.get("message_id"),
                "to": p["to"], "subject": p["subject"],
                "smtp_skip_reason": smtp_result.get("code"),
            }
        return "failed", {"channel": "email", "provider": "resend",
                          "error": result.get("error"), "to": p["to"]}

    if step == "wait_3_days":
        return "wait_completed", {"duration_seconds": WAIT_SECONDS}

    if step == "wait_open":
        # We don't have an open-tracking signal yet (Resend webhook not wired).
        # Emitting a phantom "opened" event would lie to the SDR — they'd see
        # an open in the timeline that no human ever produced. Until the
        # webhook lands, advance past this step with a neutral outcome.
        return "skipped_no_tracking", {
            "detail": "open tracking not wired (Resend webhook pending)",
        }

    return "noop", {}


def _channel_for(step: str) -> Optional[str]:
    if step in {"render_email_day0", "send_day0", "wait_open"}:
        return "email"
    return None


# Steps with real-world side effects (an email send, a webhook call). For
# these we double-check the events ledger to avoid re-firing on crash+retry.
_SIDE_EFFECT_STEPS = {"send_day0"}


async def _has_completed_step(db, run_id: uuid.UUID, step_name: str) -> bool:
    """True if an event with outcome != 'failed' already exists for this step.
    Lets us short-circuit re-runs of side-effect steps when a crash interrupted
    the prior commit (so the recipient doesn't get a duplicate email)."""
    existing = (await db.execute(
        select(AutomationEvent).where(
            AutomationEvent.run_id == run_id,
            AutomationEvent.step_name == step_name,
            AutomationEvent.outcome != "failed",
        ).limit(1)
    )).scalar_one_or_none()
    return existing is not None


async def _advance_one(run_id: uuid.UUID) -> None:
    """Atomically claim a row, advance one step, commit.

    Multi-worker safety: SELECT ... FOR UPDATE SKIP LOCKED. If two workers
    pick the same row in their tick, only one acquires the lock; the other
    sees nothing and bails. The lock auto-releases at commit/rollback.

    Crash safety: each side-effect step (Resend send, etc.) checks the events
    ledger BEFORE running. If a previous attempt already wrote a non-failed
    event for that step, we treat it as already done and just advance state."""
    async with SessionLocal() as db:
        # Atomic claim. Async asyncpg honours skip_locked.
        run = (await db.execute(
            select(AutomationRun)
            .where(AutomationRun.id == run_id)
            .with_for_update(skip_locked=True)
        )).scalar_one_or_none()
        if not run:
            # Either the row vanished, or another worker has the lock — skip.
            return
        if run.status != "running":
            return  # paused/cancelled in the gap, skip

        next_step = _next_step(run.current_step_name)
        if next_step is None:
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.next_fire_at = None
            await db.commit()
            return

        # Reply-pause guard: if the lead's sequence_state is paused_replied
        # (manual or IMAP-detected), skip every send_* step. The wait_*
        # steps are allowed through so the run cleanly advances to completion
        # without firing emails. Without this, a prospect who said "yes"
        # gets follow-up emails for the rest of the sequence — the #1 trust
        # failure that kills outbound automation.
        if next_step in _SIDE_EFFECT_STEPS and run.lead_id:
            paused = (await db.execute(
                select(Lead.sequence_state).where(Lead.id == run.lead_id)
            )).scalar()
            if paused == "paused_replied":
                log.info("run %s: lead in paused_replied state, skipping %s",
                         run_id, next_step)
                outcome, payload = "skipped_replied", {
                    "reason": "lead.sequence_state == paused_replied",
                }
                # Persist the skip event then mark the run completed early —
                # there's nothing more to do for this prospect, ever.
                db.add(AutomationEvent(
                    run_id=run.id, step_name=next_step,
                    channel=_channel_for(next_step),
                    outcome=outcome, payload=payload,
                ))
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                run.next_fire_at = None
                await db.commit()
                return

        # Idempotency for side-effect steps: if we already sent the email on
        # a prior attempt that crashed before commit, don't send it again.
        if next_step in _SIDE_EFFECT_STEPS and await _has_completed_step(db, run.id, next_step):
            log.info("run %s: %s already completed (crash recovery), skipping side effect",
                     run_id, next_step)
            outcome, payload = "skipped_idempotent", {"reason": "prior attempt already wrote a non-failed event"}
        else:
            try:
                outcome, payload = await _execute_step(db, run, next_step)
            except Exception as e:
                log.exception("step %s failed for run %s", next_step, run_id)
                db.add(AutomationEvent(
                    run_id=run.id, step_name=next_step, channel=_channel_for(next_step),
                    outcome="failed", payload={"error": str(e)[:200]},
                ))
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                run.next_fire_at = None
                # Pull lead email + template before commit so we can fire
                # the Slack alert without a second roundtrip.
                _lead_email = None
                if run.lead_id:
                    _le = (await db.execute(
                        select(Lead.email).where(Lead.id == run.lead_id)
                    )).scalar()
                    _lead_email = _le
                _tpl_key = run.template_key
                _tenant = run.tenant_id
                _run_id = run.id
                await db.commit()
                # Fire-and-forget alert. Wrapped in try so a Slack outage
                # doesn't crash the scheduler tick.
                try:
                    from routers.settings import maybe_alert_slack_run_failed
                    await maybe_alert_slack_run_failed(
                        _tenant, run_id=_run_id, step=next_step,
                        error=str(e)[:300], lead_email=_lead_email,
                        template_key=_tpl_key,
                    )
                except Exception:
                    log.exception("run-failure slack alert raised")
                return

        db.add(AutomationEvent(
            run_id=run.id, step_name=next_step, channel=_channel_for(next_step),
            outcome=outcome, payload=payload,
        ))
        run.current_step_name = next_step

        # Hard fail on Resend rejection — don't silently complete a run
        # whose primary action (the email) was never delivered.
        if outcome == "failed" and next_step in _SIDE_EFFECT_STEPS:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.next_fire_at = None
            _lead_email = None
            if run.lead_id:
                _le = (await db.execute(
                    select(Lead.email).where(Lead.id == run.lead_id)
                )).scalar()
                _lead_email = _le
            _err_msg = (payload or {}).get("error") if isinstance(payload, dict) else None
            _tpl_key = run.template_key
            _tenant = run.tenant_id
            _run_id = run.id
            await db.commit()
            try:
                from routers.settings import maybe_alert_slack_run_failed
                await maybe_alert_slack_run_failed(
                    _tenant, run_id=_run_id, step=next_step,
                    error=_err_msg or "send failed", lead_email=_lead_email,
                    template_key=_tpl_key,
                )
            except Exception:
                log.exception("run-failure slack alert raised")
            return

        # Decide when the next tick should fire.
        if _next_step(next_step) is None:
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.next_fire_at = None
        elif next_step in WAIT_AFTER:
            run.next_fire_at = datetime.now(timezone.utc) + timedelta(seconds=WAIT_SECONDS)
        else:
            run.next_fire_at = datetime.now(timezone.utc)

        await db.commit()


async def _tick() -> int:
    """Find every run that's due to advance, fire them in parallel. Returns
    the count of runs touched."""
    async with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        rows = (await db.execute(
            select(AutomationRun.id).where(and_(
                AutomationRun.status == "running",
                AutomationRun.next_fire_at != None,  # noqa: E711
                AutomationRun.next_fire_at <= now,
            )).limit(20)
        )).scalars().all()

    if not rows:
        return 0
    await asyncio.gather(*[_advance_one(rid) for rid in rows], return_exceptions=True)
    return len(rows)


# ─────────────────────────────────────────────────────────────────────────
# Daily digest auto-cron — fires once per UTC day at DIGEST_HOUR_UTC (default
# 9). Idempotent on (date, tenant) via an in-process set so multiple ticks
# inside the trigger hour don't double-send. The bookkeeping resets every
# UTC midnight; restart of the process resets it too (a duplicate digest the
# day after a restart is benign — better than missing one).
# ─────────────────────────────────────────────────────────────────────────

DIGEST_HOUR_UTC = int(os.getenv("DIGEST_HOUR_UTC", "9"))
DIGEST_ENABLED = os.getenv("DIGEST_ENABLED", "true").lower() not in ("0", "false", "no")
_digest_sent_today: set[tuple[str, str]] = set()
_last_digest_date: Optional[str] = None


async def _maybe_run_digest_cron() -> None:
    """Called from the main loop. Fires the digest for every active tenant
    once per UTC day inside the configured hour. No-op the rest of the time.
    """
    global _last_digest_date
    if not DIGEST_ENABLED:
        return
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    if _last_digest_date != today:
        _digest_sent_today.clear()
        _last_digest_date = today
    if now.hour != DIGEST_HOUR_UTC:
        return

    # Discover the active tenants. Single-tenant today, but the loop
    # below is multi-tenant ready.
    tenants: list[str] = []
    try:
        async with SessionLocal() as db:
            from db.entities import WorkspaceSettings
            rows = (await db.execute(select(WorkspaceSettings.tenant_id))).all()
            tenants = [str(r[0]) for r in rows]
    except Exception:
        log.exception("digest cron: tenant discovery failed")
        return

    if not tenants:
        # No workspace_settings row yet — fall back to the env default tenant.
        try:
            from config import settings as app_settings
            tenants = [app_settings.default_tenant_id]
        except Exception:
            return

    from automations.digest import send_digest_for_tenant
    import uuid as _uuid
    for tid in tenants:
        key = (today, tid)
        if key in _digest_sent_today:
            continue
        try:
            result = await send_digest_for_tenant(_uuid.UUID(tid))
            if result.get("ok"):
                log.info("digest sent for tenant=%s to=%s", tid, result.get("sent_to"))
            elif result.get("code") == "no_activity":
                log.debug("digest skipped tenant=%s (no activity)", tid)
        except Exception:
            log.exception("digest cron: send failed for tenant=%s", tid)
        # Mark it tried regardless — we don't want to re-fire failures all
        # hour and bombard admins with retries on transient SMTP issues.
        _digest_sent_today.add(key)


async def run_forever() -> None:
    """Top-level loop. Cancellable via task.cancel() (lifespan shutdown)."""
    log.info("automation scheduler started (tick=%ss, wait=%ss)", TICK_SECONDS, WAIT_SECONDS)
    while True:
        try:
            n = await _tick()
            if n:
                log.debug("scheduler advanced %d run(s)", n)
            await _maybe_run_digest_cron()
        except asyncio.CancelledError:
            log.info("scheduler shutting down")
            raise
        except Exception:
            log.exception("scheduler tick crashed")
        await asyncio.sleep(TICK_SECONDS)

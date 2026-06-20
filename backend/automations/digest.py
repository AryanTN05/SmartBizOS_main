"""Daily digest email — re-engages users that haven't checked the dashboard.

Aggregates the day's signals into one HTML email per admin:
  - new replies (with intent + snippet)
  - new hot leads (>= 80)
  - sequence health (sends, fails, suppressions)
  - top trigger-stacked leads

Sent via the existing send_email (Resend) path. The user can manually
trigger via POST /api/digest/send-now, or schedule it in the existing
scheduler (cron-like daily) — currently we expose only the manual button
so the user controls when their inbox sees it.

The trend scan flagged Day-2 retention as the killer for this category:
users who don't see feedback the day after their first send disengage.
The Home dashboard now has live reply-rate, but a daily push email
closes the loop for users who don't open the dashboard every morning.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_, desc, func

from automations.email import send_email
from db.connection import SessionLocal
from db.entities import (
    ActivityLog, AdminUser, AutomationEvent, AutomationRun, Lead,
    WorkspaceSettings, WorkspaceSuppression,
)

log = logging.getLogger("smartbiz.digest")


def _intent_chip(intent: Optional[str]) -> str:
    color = {
        "positive": "#1c7c2c",  "negative": "#b03030",
        "neutral":  "#666",     "wrong_person": "#a06600",
        "unsubscribe": "#b03030", "auto_reply": "#999",
    }.get(intent or "", "#666")
    label = (intent or "—").replace("_", " ")
    return (
        f'<span style="display:inline-block;padding:1px 8px;font-size:10px;'
        f'color:{color};background:{color}1a;border:1px solid {color}55;'
        f'border-radius:8px;font-family:monospace;">{label}</span>'
    )


def _renderer_helpers():
    """Returns small (subject, body_html) helpers for testability."""
    return {}


async def _build_for_tenant(tenant_id) -> Optional[dict]:
    """Build the digest payload for a single tenant. Returns None when
    nothing happened in the last 24h (don't send empty digests)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    async with SessionLocal() as db:
        # New replies in last 24h
        replies = (await db.execute(
            select(ActivityLog, Lead)
            .join(Lead, Lead.id == ActivityLog.lead_id)
            .where(
                ActivityLog.tenant_id == tenant_id,
                ActivityLog.action_type == "reply_received",
                ActivityLog.created_at >= cutoff,
                Lead.deleted_at == None,  # noqa: E711
            )
            .order_by(desc(ActivityLog.created_at))
            .limit(10)
        )).all()

        # New hot leads (created in last 24h with score >= 80)
        hot_leads = (await db.execute(
            select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.deleted_at == None,  # noqa: E711
                Lead.created_at >= cutoff,
                Lead.score >= 80,
            ).order_by(desc(Lead.score), desc(Lead.created_at)).limit(10)
        )).scalars().all()

        # Sequence health
        sends = (await db.execute(
            select(func.count()).select_from(
                select(AutomationEvent.id)
                .join(AutomationRun, AutomationEvent.run_id == AutomationRun.id)
                .where(
                    AutomationRun.tenant_id == tenant_id,
                    AutomationEvent.step_name == "send_day0",
                    AutomationEvent.outcome == "sent",
                    AutomationEvent.occurred_at >= cutoff,
                ).subquery()
            )
        )).scalar() or 0
        failed = (await db.execute(
            select(func.count()).select_from(
                select(AutomationEvent.id)
                .join(AutomationRun, AutomationEvent.run_id == AutomationRun.id)
                .where(
                    AutomationRun.tenant_id == tenant_id,
                    AutomationEvent.step_name == "send_day0",
                    AutomationEvent.outcome == "failed",
                    AutomationEvent.occurred_at >= cutoff,
                ).subquery()
            )
        )).scalar() or 0
        new_suppressions = (await db.execute(
            select(func.count()).select_from(
                select(WorkspaceSuppression.id).where(
                    WorkspaceSuppression.tenant_id == tenant_id,
                    WorkspaceSuppression.created_at >= cutoff,
                ).subquery()
            )
        )).scalar() or 0

        if not (replies or hot_leads or sends or failed):
            return None

        # Workspace name for the subject line.
        ws = (await db.execute(
            select(WorkspaceSettings).where(WorkspaceSettings.tenant_id == tenant_id)
        )).scalar_one_or_none()
        ws_name = (ws.workspace_name if ws and ws.workspace_name else "Your workspace")

        # Build HTML.
        rows: list[str] = []
        rows.append(
            f'<h1 style="font-size:20px;margin:0 0 4px;">{ws_name} · daily digest</h1>'
            f'<p style="color:#666;font-size:13px;margin:0 0 24px;">'
            f'{datetime.now(timezone.utc).strftime("%A, %b %d %Y")} · last 24 hours.</p>'
        )

        # Stats row
        rows.append(
            f'<table style="width:100%;border-collapse:collapse;margin-bottom:24px;">'
            f'<tr>'
            f'  <td style="text-align:center;padding:10px;border:1px solid #eee;">'
            f'    <div style="font-size:22px;font-weight:600;">{len(replies)}</div>'
            f'    <div style="font-size:10px;text-transform:uppercase;color:#888;letter-spacing:.06em;">replies</div>'
            f'  </td>'
            f'  <td style="text-align:center;padding:10px;border:1px solid #eee;">'
            f'    <div style="font-size:22px;font-weight:600;color:#1c7c2c;">{len(hot_leads)}</div>'
            f'    <div style="font-size:10px;text-transform:uppercase;color:#888;letter-spacing:.06em;">new hot</div>'
            f'  </td>'
            f'  <td style="text-align:center;padding:10px;border:1px solid #eee;">'
            f'    <div style="font-size:22px;font-weight:600;">{sends}</div>'
            f'    <div style="font-size:10px;text-transform:uppercase;color:#888;letter-spacing:.06em;">sends</div>'
            f'  </td>'
            f'  <td style="text-align:center;padding:10px;border:1px solid #eee;">'
            f'    <div style="font-size:22px;font-weight:600;color:{"#b03030" if failed else "#888"};">{failed}</div>'
            f'    <div style="font-size:10px;text-transform:uppercase;color:#888;letter-spacing:.06em;">failed</div>'
            f'  </td>'
            f'</tr>'
            f'</table>'
        )

        if replies:
            rows.append('<h2 style="font-size:14px;margin:24px 0 8px;">Replies</h2>')
            rows.append('<table style="width:100%;border-collapse:collapse;font-size:13px;">')
            for activity, lead in replies:
                meta = activity.metadata_ or {}
                snippet = (meta.get("snippet") or "")[:160]
                intent = meta.get("intent") or lead.last_reply_intent
                rows.append(
                    f'<tr><td style="padding:8px;border-top:1px solid #eee;">'
                    f'  <div style="display:flex;justify-content:space-between;align-items:baseline;">'
                    f'    <strong>{lead.name or lead.email}</strong> '
                    f'    <span style="color:#888;font-size:11px;">{lead.company_name or ""}</span>'
                    f'  </div>'
                    f'  <div style="margin-top:4px;color:#444;">{snippet}{"…" if snippet and len(snippet) >= 160 else ""}</div>'
                    f'  <div style="margin-top:4px;">{_intent_chip(intent)}</div>'
                    f'</td></tr>'
                )
            rows.append('</table>')

        if hot_leads:
            rows.append('<h2 style="font-size:14px;margin:24px 0 8px;">Top hot leads</h2>')
            rows.append('<table style="width:100%;border-collapse:collapse;font-size:13px;">')
            for lead in hot_leads:
                triggers = ", ".join(lead.triggers or [])
                trigger_html = f'<span style="color:#888;font-size:11px;"> · {triggers}</span>' if triggers else ""
                rows.append(
                    f'<tr><td style="padding:8px;border-top:1px solid #eee;">'
                    f'  <strong>{lead.name or "(unnamed)"}</strong> · '
                    f'  <span style="color:#888">{lead.company_name or ""}</span> · '
                    f'  <span style="color:#1c7c2c;font-family:monospace;">{lead.score or 0}</span>'
                    f'  {trigger_html}'
                    f'</td></tr>'
                )
            rows.append('</table>')

        if new_suppressions:
            rows.append(
                f'<p style="margin-top:24px;font-size:12px;color:#888;">'
                f'<em>{new_suppressions}</em> recipient(s) added to suppression list '
                f'today (bounces, complaints, or unsubscribes).</p>'
            )

        body = "".join(rows)
        return {
            "subject": f"{ws_name} · {len(replies)} replies, {len(hot_leads)} hot",
            "html": body,
            "stats": {
                "replies": len(replies), "hot": len(hot_leads),
                "sends": sends, "failed": failed,
                "new_suppressions": new_suppressions,
            },
        }


async def send_digest_for_tenant(tenant_id) -> dict:
    """Build + send digest to every admin user for this tenant. Returns
    a summary the route handler can return to the caller."""
    payload = await _build_for_tenant(tenant_id)
    if not payload:
        return {"ok": False, "code": "no_activity",
                "message": "No replies / new hot leads / sends in the last 24h."}

    async with SessionLocal() as db:
        # AdminUser is a global table currently (multi-tenant refactor is
        # a separate task). Send digest to every active admin — when real
        # multi-tenancy lands, scope this to tenant_id.
        admins = (await db.execute(
            select(AdminUser).where(AdminUser.status == "active")
        )).scalars().all()

    sent_to: list[str] = []
    errors: list[str] = []
    for a in admins:
        if not a.email:
            continue
        result = await send_email(
            to=a.email, subject=payload["subject"], html=payload["html"],
        )
        if result.get("ok"):
            sent_to.append(a.email)
        else:
            errors.append(f"{a.email}: {result.get('error')}")

    return {
        "ok": True, "sent_to": sent_to, "errors": errors,
        "stats": payload["stats"],
    }

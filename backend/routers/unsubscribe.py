"""Public unsubscribe endpoint — RFC 8058 one-click compliant.

Two routes share the path /api/u/{token}:

  GET  — renders a tiny HTML confirmation page so a recipient who
         clicks the link in an email lands somewhere visible.
  POST — the actual unsubscribe action. Required by RFC 8058 for
         "Gmail/Outlook one-click unsubscribe" — receivers POST to
         List-Unsubscribe with body `List-Unsubscribe=One-Click`.

Both paths verify an HMAC token (signed against UNSUBSCRIBE_SECRET or
JWT_SECRET) so anyone with a valid token can opt out without auth.
The token encodes the lead UUID; we look up tenant_id off the lead row
so the URL stays clean.

On success we:
  - mark the lead unsubscribed_at
  - add (tenant_id, email) to the suppression list
  - write an activity log entry
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from db.connection import SessionLocal
from db.entities import ActivityLog, Lead

log = logging.getLogger("smartbiz.unsubscribe")

router = APIRouter(prefix="/api/u", tags=["Public · Unsubscribe"])


_HTML_OK = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Unsubscribed</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif;
         max-width: 480px; margin: 80px auto; padding: 0 24px;
         color: #222; }}
  h1   {{ font-size: 22px; margin: 0 0 12px; }}
  p    {{ font-size: 14px; line-height: 1.55; color: #555; }}
  .ok  {{ display: inline-block; padding: 4px 10px; background: #e6f7e9;
         color: #1c7c2c; font-size: 12px; border-radius: 999px; }}
</style>
</head><body>
<span class="ok">unsubscribed</span>
<h1>You're off the list.</h1>
<p>{email} won't receive further emails from this sender.</p>
<p style="font-size:12px;color:#999;margin-top:32px;">
  If this was a mistake, contact the sender directly to be re-added.
</p>
</body></html>"""

_HTML_BAD = """<!doctype html>
<html><head>
<meta charset="utf-8"><title>Invalid link</title>
<style>body{{font-family:-apple-system,system-ui,sans-serif;max-width:480px;
margin:80px auto;padding:0 24px;color:#222}}</style>
</head><body>
<h1 style="font-size:20px">Invalid or expired link</h1>
<p>This unsubscribe link couldn't be verified. If you keep receiving
emails, reply to one and ask the sender to remove you.</p>
</body></html>"""


async def _do_unsubscribe(token: str) -> tuple[bool, str | None]:
    """Returns (ok, email_or_none). Idempotent — calling twice is safe."""
    from automations.suppression import (
        parse_lead_id_from_token, verify_unsubscribe_token, add_suppression,
    )
    lead_id = parse_lead_id_from_token(token)
    if not lead_id:
        return False, None

    async with SessionLocal() as db:
        lead = (await db.execute(
            select(Lead).where(Lead.id == lead_id, Lead.deleted_at == None)  # noqa: E711
        )).scalar_one_or_none()
        if not lead:
            return False, None
        if not verify_unsubscribe_token(token, lead.id, lead.tenant_id):
            return False, None

        now = datetime.now(timezone.utc)
        if not lead.unsubscribed_at:
            lead.unsubscribed_at = now
        # Pause any active sequence so the user gets immediate state.
        if lead.sequence_state == "active":
            lead.sequence_state = "paused_manual"
        # Activity log row so the SDR sees the click on the timeline.
        db.add(ActivityLog(
            tenant_id=lead.tenant_id,
            lead_id=lead.id,
            action_type="unsubscribed",
            description="Recipient hit the 1-click unsubscribe link",
            metadata_={"source": "list_unsubscribe"},
            triggered_by="recipient",
        ))
        await db.commit()

    if lead.email:
        await add_suppression(lead.tenant_id, lead.email,
                               reason="user_unsub",
                               notes="1-click unsubscribe via email link")

    return True, lead.email


@router.get("/{token}")
async def unsubscribe_get(token: str):
    """Recipient clicked the link in their email client — render the
    confirmation page. Some inbox UIs show the page; others (Gmail) do
    the POST directly. Either way the user lands here on a click."""
    ok, email = await _do_unsubscribe(token)
    if not ok:
        return HTMLResponse(_HTML_BAD, status_code=400)
    return HTMLResponse(_HTML_OK.format(email=email or "you"))


@router.post("/{token}")
async def unsubscribe_post(token: str):
    """RFC 8058 one-click — receivers POST here directly with body
    `List-Unsubscribe=One-Click`. Returns 200 on success, 400 on bad token."""
    ok, _ = await _do_unsubscribe(token)
    if not ok:
        raise HTTPException(status_code=400, detail="invalid token")
    return {"ok": True}

"""Inbound webhook endpoints for third-party CRMs / form providers /
deliverability events.

Tenant is always derived from server config, never trusted from the
request. Each endpoint requires a provider-specific signature; without
the matching secret in env, the endpoint returns 501 so we never
silently accept unsigned input.

  /api/webhooks/incoming   generic   X-Webhook-Token header     env: WEBHOOK_TOKEN
  /api/webhooks/tally      Tally     tally-signature (HMAC)     env: TALLY_WEBHOOK_SECRET
  /api/webhooks/hubspot    HubSpot   X-HubSpot-Signature-v3     env: HUBSPOT_CLIENT_SECRET
  /api/webhooks/resend     Resend    Svix-Signature             env: RESEND_WEBHOOK_SECRET

The Resend endpoint handles delivery events (bounce / complaint /
delivered / opened / clicked) and auto-suppresses bouncers + complainers
so domain reputation stays inside Google's enforcement bands.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.connection import get_db
from db.entities import Lead

log = logging.getLogger("smartbiz.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks & Integrations"])


def _tenant() -> uuid.UUID:
    return uuid.UUID(settings.default_tenant_id)


def _require_secret(env_var: str, provider: str) -> str:
    """Return the secret or raise 501 — better than silently accepting."""
    secret = os.getenv(env_var)
    if not secret:
        raise HTTPException(status_code=501, detail={
            "code": "webhook_unconfigured",
            "message": f"{provider} webhook is not configured (set {env_var})",
        })
    return secret


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


async def _create_lead(db: AsyncSession, *, name: Optional[str], email: Optional[str],
                        phone: Optional[str], company_name: Optional[str],
                        title: Optional[str], source: str,
                        source_ref_id: Optional[str] = None,
                        notes: Optional[str] = None) -> Lead:
    """Shared insert path. Caller has already verified the signature."""
    lead = Lead(
        tenant_id=_tenant(),
        name=name, email=(email or "").lower() or None,
        phone=phone, company_name=company_name, title=title,
        source=source, source_ref_id=source_ref_id,
        notes=notes,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    log.info("webhook lead created from %s id=%s email=%s", source, lead.id, lead.email)
    return lead


def _shape_lead(lead: Lead) -> dict:
    return {
        "id": str(lead.id),
        "email": lead.email,
        "name": lead.name,
        "company_name": lead.company_name,
        "source": lead.source,
        "created_at_unix": int(lead.created_at.timestamp()) if lead.created_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Generic /incoming — token-gated catch-all for Zapier / Make / curl scripts.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/incoming")
async def process_incoming_webhook(
    body: dict,
    x_webhook_token: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Generic CRM-agnostic webhook. Token gate via X-Webhook-Token.

    Body schema (all optional except email):
      { "email": "...", "name": "...", "phone": "...",
        "company_name": "...", "title": "...", "notes": "..." }
    """
    secret = _require_secret("WEBHOOK_TOKEN", "Generic /incoming")
    if not x_webhook_token or not _constant_time_eq(x_webhook_token, secret):
        raise HTTPException(status_code=401, detail={
            "code": "invalid_token", "message": "X-Webhook-Token is missing or invalid",
        })

    email = (body.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed", "message": "email is required",
        })

    lead = await _create_lead(
        db,
        name=body.get("name"), email=email,
        phone=body.get("phone"),
        company_name=body.get("company_name") or body.get("company"),
        title=body.get("title"),
        source=body.get("source") or "webhook",
        notes=body.get("notes"),
    )
    return {"lead": _shape_lead(lead)}


# ─────────────────────────────────────────────────────────────────────────────
# Tally — https://tally.so/help/webhooks
#   Signature: HMAC-SHA256(secret, raw_body) base64
#   Header:    tally-signature
# ─────────────────────────────────────────────────────────────────────────────

def _verify_tally(secret: str, raw_body: bytes, signature: Optional[str]) -> bool:
    if not signature:
        return False
    import base64
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return _constant_time_eq(expected, signature)


def _tally_field(fields: list[dict], label_substring: str) -> Optional[str]:
    """Find the first field whose label contains the substring (case-insensitive)
    and return its value as a string. Tally form payloads ship as a list of
    typed fields, so we map by label rather than position."""
    target = label_substring.lower()
    for f in fields or []:
        label = (f.get("label") or "").lower()
        if target in label:
            v = f.get("value")
            if isinstance(v, list):
                return ", ".join(str(x) for x in v) if v else None
            return str(v) if v is not None else None
    return None


@router.post("/tally")
async def process_tally_webhook(
    request: Request,
    tally_signature: Optional[str] = Header(default=None, alias="tally-signature"),
    db: AsyncSession = Depends(get_db),
):
    """Tally form submission → lead row.

    Maps fields by label substring ("email", "name", "company", "phone").
    Forms with non-English labels need their secrets re-mapped — open an
    issue with the form ID and we'll add provider-specific overrides.
    """
    secret = _require_secret("TALLY_WEBHOOK_SECRET", "Tally")
    raw = await request.body()
    if not _verify_tally(secret, raw, tally_signature):
        raise HTTPException(status_code=401, detail={
            "code": "invalid_signature", "message": "Tally signature mismatch",
        })

    import json
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed", "message": "body is not valid JSON",
        })

    data = payload.get("data") or {}
    fields = data.get("fields") or []
    submission_id = data.get("submissionId") or payload.get("eventId")

    email = _tally_field(fields, "email")
    if not email:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed", "message": "no email field in submission",
        })

    lead = await _create_lead(
        db,
        name=_tally_field(fields, "name"),
        email=email,
        phone=_tally_field(fields, "phone"),
        company_name=_tally_field(fields, "company"),
        title=_tally_field(fields, "title"),
        source="tally",
        source_ref_id=submission_id,
    )
    return {"lead": _shape_lead(lead)}


# ─────────────────────────────────────────────────────────────────────────────
# HubSpot — https://developers.hubspot.com/docs/api/webhooks/validating-requests
#   Signature v3: HMAC-SHA256(client_secret,
#                              method + uri + body + timestamp) → base64
#   Headers:  X-HubSpot-Signature-v3, X-HubSpot-Request-Timestamp
#   Anti-replay: reject if timestamp older than 5 minutes
# ─────────────────────────────────────────────────────────────────────────────

_HUBSPOT_REPLAY_WINDOW_S = 5 * 60


def _verify_hubspot(secret: str, method: str, uri: str, raw_body: bytes,
                     timestamp: Optional[str], signature: Optional[str]) -> tuple[bool, str]:
    if not signature or not timestamp:
        return False, "missing signature or timestamp"
    try:
        ts = int(timestamp) / 1000.0  # HubSpot ships ms
    except ValueError:
        return False, "timestamp not numeric"
    if abs(time.time() - ts) > _HUBSPOT_REPLAY_WINDOW_S:
        return False, "timestamp outside replay window"
    import base64
    msg = (method.upper() + uri + raw_body.decode("utf-8", errors="replace") + timestamp).encode()
    digest = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return _constant_time_eq(expected, signature), "ok" if _constant_time_eq(expected, signature) else "signature mismatch"


@router.post("/hubspot")
async def process_hubspot_webhook(
    request: Request,
    x_hubspot_signature_v3: Optional[str] = Header(default=None, alias="x-hubspot-signature-v3"),
    x_hubspot_request_timestamp: Optional[str] = Header(default=None, alias="x-hubspot-request-timestamp"),
    db: AsyncSession = Depends(get_db),
):
    """HubSpot Contact / Deal events. Currently maps `contact.creation` and
    `contact.propertyChange` events to a lead create or no-op."""
    secret = _require_secret("HUBSPOT_CLIENT_SECRET", "HubSpot")
    raw = await request.body()
    # HubSpot signs the full request URI including any query string.
    uri = str(request.url)
    ok, _ = _verify_hubspot(
        secret, request.method, uri, raw,
        x_hubspot_request_timestamp, x_hubspot_signature_v3,
    )
    if not ok:
        raise HTTPException(status_code=401, detail={
            "code": "invalid_signature", "message": "HubSpot signature mismatch",
        })

    import json
    try:
        events = json.loads(raw.decode("utf-8") or "[]")
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed", "message": "body is not valid JSON",
        })
    if not isinstance(events, list):
        events = [events]

    created = []
    for ev in events:
        if ev.get("subscriptionType") != "contact.creation":
            continue
        # HubSpot doesn't include contact properties in the webhook by default
        # — just IDs. A real adapter would call /crm/v3/objects/contacts/{id}
        # to pull email + name. For now we record the creation event so the
        # signal is captured and the operator can pull details out-of-band.
        contact_id = ev.get("objectId")
        if not contact_id:
            continue
        lead = await _create_lead(
            db,
            name=None, email=f"hubspot-{contact_id}@pending.local",
            phone=None, company_name=None, title=None,
            source="hubspot", source_ref_id=str(contact_id),
            notes="Created from HubSpot webhook — fetch contact details "
                  "via /crm/v3 once OAuth ships.",
        )
        created.append(_shape_lead(lead))

    return {"created": created, "count": len(created)}


# ─────────────────────────────────────────────────────────────────────────────
# Resend — delivery events (bounce / complaint / opened / etc).
#   Signed with Svix: svix-id + svix-timestamp + svix-signature
#   Verification: HMAC-SHA256(secret_bytes, "<svix-id>.<svix-timestamp>.<body>")
#                 base64-encoded; signature header carries one or more
#                 versions, e.g. "v1,abc=" — we accept any matching v1.
# ─────────────────────────────────────────────────────────────────────────────

_SVIX_REPLAY_WINDOW_S = 5 * 60


def _verify_svix(secret: str, raw_body: bytes,
                 svix_id: Optional[str], svix_ts: Optional[str],
                 svix_sig: Optional[str]) -> tuple[bool, str]:
    if not (svix_id and svix_ts and svix_sig):
        return False, "missing svix-id / svix-timestamp / svix-signature"
    try:
        ts = int(svix_ts)
    except ValueError:
        return False, "timestamp not numeric"
    if abs(time.time() - ts) > _SVIX_REPLAY_WINDOW_S:
        return False, "timestamp outside replay window"
    # Resend's secret is a "whsec_..." string. The HMAC key is the base64
    # decoding of everything after "whsec_".
    import base64
    if secret.startswith("whsec_"):
        try:
            key = base64.b64decode(secret[len("whsec_"):])
        except Exception:
            return False, "secret base64 decode failed"
    else:
        key = secret.encode()
    msg = f"{svix_id}.{svix_ts}.{raw_body.decode('utf-8', errors='replace')}".encode()
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    # Header may carry multiple signatures: "v1,sigA v1,sigB"
    candidates = [s.split(",", 1)[1] for s in svix_sig.split(" ")
                   if "," in s and s.startswith("v1,")]
    for c in candidates:
        if hmac.compare_digest(expected, c):
            return True, "ok"
    return False, "no signature matched"


@router.post("/resend")
async def process_resend_webhook(
    request: Request,
    svix_id: Optional[str] = Header(default=None, alias="svix-id"),
    svix_timestamp: Optional[str] = Header(default=None, alias="svix-timestamp"),
    svix_signature: Optional[str] = Header(default=None, alias="svix-signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Resend delivery events. Bounces + complaints add the recipient
    to the suppression list automatically (with reason `bounce_hard`,
    `bounce_soft`, or `complained`) so the next sequence skips them at
    the suppression gate in the scheduler."""
    secret = _require_secret("RESEND_WEBHOOK_SECRET", "Resend")
    raw = await request.body()
    ok, reason = _verify_svix(secret, raw, svix_id, svix_timestamp, svix_signature)
    if not ok:
        log.info("resend webhook signature reject: %s", reason)
        raise HTTPException(status_code=401, detail={
            "code": "invalid_signature", "message": reason,
        })

    import json
    try:
        event = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed", "message": "body is not valid JSON",
        })

    event_type = event.get("type") or ""
    data = event.get("data") or {}
    # Resend event payloads place the recipient list at data.to (array).
    recipients = data.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]

    from automations.suppression import add_suppression

    suppressed: list[str] = []
    handled = False

    for to in recipients:
        if not isinstance(to, str) or "@" not in to:
            continue
        if event_type in ("email.bounced", "email.bounce"):
            # Resend reports `bounce.type` ∈ {"hard", "soft", ...}
            btype = (data.get("bounce") or {}).get("type", "hard").lower()
            reason_code = "bounce_hard" if btype == "hard" else "bounce_soft"
            await add_suppression(_tenant(), to, reason=reason_code,
                                   notes=f"resend webhook · {event_type} · type={btype}")
            suppressed.append(to)
            handled = True
        elif event_type in ("email.complained", "email.complaint"):
            await add_suppression(_tenant(), to, reason="complained",
                                   notes=f"resend webhook · {event_type}")
            suppressed.append(to)
            handled = True
        # email.delivered / email.opened / email.clicked don't suppress;
        # they're informational and could feed analytics in a future pass.

    return {"ok": True, "type": event_type, "handled": handled,
            "suppressed": suppressed}

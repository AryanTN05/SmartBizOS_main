"""
routers/settings.py — workspace-scoped settings.

The single most important field is `icp_description`: the LLM ICP scorer
interpolates it into its system prompt, so each workspace tunes scoring
to their actual product without code changes.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from config import settings as app_settings
from db.connection import get_db
from db.entities import WorkspaceSettings

router = APIRouter(
    prefix="/api/workspace/settings",
    tags=["Workspace settings"],
    dependencies=[Depends(require_admin)],
)

log = logging.getLogger("smartbiz.settings")


def _tenant() -> uuid.UUID:
    return uuid.UUID(app_settings.default_tenant_id)


class SettingsBody(BaseModel):
    icp_description: Optional[str] = Field(default=None, max_length=4000)
    workspace_name: Optional[str] = Field(default=None, max_length=200)
    sender_name: Optional[str] = Field(default=None, max_length=200)
    slack_webhook_url: Optional[str] = Field(default=None, max_length=500)
    slack_alert_min_score: Optional[int] = Field(default=None, ge=0, le=100)
    send_time_optimization: Optional[bool] = None
    calendar_link: Optional[str] = Field(default=None, max_length=400)
    apollo_icp: Optional[dict] = None


def _shape(s: WorkspaceSettings) -> dict:
    return {
        "tenant_id": str(s.tenant_id),
        "icp_description": s.icp_description,
        "workspace_name": s.workspace_name,
        "sender_name": s.sender_name,
        "slack_webhook_url": s.slack_webhook_url,
        "slack_alert_min_score": s.slack_alert_min_score,
        "send_time_optimization": bool(s.send_time_optimization),
        "calendar_link": s.calendar_link,
        "apollo_icp": s.apollo_icp,
        "updated_at_unix": int(s.updated_at.timestamp()) if s.updated_at else None,
    }


async def _get_or_create(db: AsyncSession) -> WorkspaceSettings:
    tenant = _tenant()
    row = (await db.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.tenant_id == tenant)
    )).scalar_one_or_none()
    if row:
        return row
    row = WorkspaceSettings(tenant_id=tenant)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)):
    row = await _get_or_create(db)
    return _shape(row)


@router.patch("")
async def update_settings(body: SettingsBody, db: AsyncSession = Depends(get_db)):
    row = await _get_or_create(db)
    if body.icp_description is not None:
        # Empty string means "use the in-code default" — store as NULL.
        row.icp_description = body.icp_description.strip() or None
    if body.workspace_name is not None:
        row.workspace_name = body.workspace_name.strip() or None
    if body.sender_name is not None:
        row.sender_name = body.sender_name.strip() or None
    if body.slack_webhook_url is not None:
        url = body.slack_webhook_url.strip()
        # Cheap validation — Slack webhooks always start with this prefix.
        if url and not url.startswith("https://hooks.slack.com/"):
            raise HTTPException(status_code=422, detail={
                "code": "bad_slack_url",
                "message": "Slack webhook URLs start with https://hooks.slack.com/",
            })
        row.slack_webhook_url = url or None
    if body.slack_alert_min_score is not None:
        row.slack_alert_min_score = body.slack_alert_min_score
    if body.send_time_optimization is not None:
        row.send_time_optimization = bool(body.send_time_optimization)
    if body.apollo_icp is not None:
        # Cheap shape validation — must be a dict with optional list-typed
        # keys. Empty dict clears the override.
        if not isinstance(body.apollo_icp, dict):
            raise HTTPException(status_code=422, detail={
                "code": "bad_apollo_icp", "message": "apollo_icp must be an object",
            })
        for k in ("titles", "seniorities", "headcount_ranges"):
            v = body.apollo_icp.get(k)
            if v is not None and not isinstance(v, list):
                raise HTTPException(status_code=422, detail={
                    "code": "bad_apollo_icp",
                    "message": f"apollo_icp.{k} must be a list of strings",
                })
        row.apollo_icp = body.apollo_icp or None
    if body.calendar_link is not None:
        url = (body.calendar_link or "").strip()
        if url and not (url.startswith("https://cal.com/")
                        or url.startswith("https://calendly.com/")
                        or url.startswith("https://meetings.hubspot.com/")
                        or url.startswith("https://savvycal.com/")):
            raise HTTPException(status_code=422, detail={
                "code": "bad_calendar_link",
                "message": "Calendar link must be a Cal.com, Calendly, "
                           "HubSpot Meetings, or SavvyCal URL.",
            })
        row.calendar_link = url or None
    await db.commit()
    await db.refresh(row)
    return _shape(row)


# Internal helper for other routers / scheduler. Reads (uncached) — the
# table only gets read during enrichment runs which already amortise cost.
async def get_icp_description(tenant_id: uuid.UUID) -> Optional[str]:
    from db.connection import SessionLocal
    async with SessionLocal() as db:
        row = (await db.execute(
            select(WorkspaceSettings.icp_description)
            .where(WorkspaceSettings.tenant_id == tenant_id)
        )).scalar_one_or_none()
        return row


# ─────────────────────────────────────────────────────────────────────────
# IMAP CRUD — reply detection settings.
#
# Stored encrypted via Fernet (IMAP_ENCRYPTION_KEY env var). Password is
# never returned by GET; the FE only ever sees `configured: bool` + status.
# ─────────────────────────────────────────────────────────────────────────

class ImapBody(BaseModel):
    host: str = Field(..., max_length=200)
    port: int = Field(default=993, ge=1, le=65535)
    email: str = Field(..., max_length=320)
    password: str = Field(..., max_length=400)
    use_ssl: bool = True


class ImapTestBody(BaseModel):
    # All fields explicit so the user can test before saving.
    host: str
    port: int = 993
    email: str
    password: str
    use_ssl: bool = True


def _shape_imap(row) -> dict:
    return {
        "configured": True,
        "host": row.host,
        "port": row.port,
        "email": row.email,
        "use_ssl": row.use_ssl,
        "last_poll_at_unix": int(row.last_poll_at.timestamp()) if row.last_poll_at else None,
        "last_error": row.last_error,
    }


@router.get("/imap")
async def get_imap_settings(db: AsyncSession = Depends(get_db)):
    from db.entities import WorkspaceImapSettings
    tenant = _tenant()
    row = (await db.execute(
        select(WorkspaceImapSettings).where(WorkspaceImapSettings.tenant_id == tenant)
    )).scalar_one_or_none()
    if not row:
        return {"configured": False}
    return _shape_imap(row)


@router.put("/imap")
async def upsert_imap_settings(body: ImapBody, db: AsyncSession = Depends(get_db)):
    from db.entities import WorkspaceImapSettings
    from automations.imap_poller import encrypt_password
    try:
        ciphertext = encrypt_password(body.password)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail={
            "code": "no_encryption_key",
            "message": str(e),
        })
    tenant = _tenant()
    row = (await db.execute(
        select(WorkspaceImapSettings).where(WorkspaceImapSettings.tenant_id == tenant)
    )).scalar_one_or_none()
    if row:
        row.host = body.host.strip()
        row.port = body.port
        row.email = body.email.strip()
        row.password_ciphertext = ciphertext
        row.use_ssl = body.use_ssl
        row.last_error = None  # fresh creds — clear any stale error
    else:
        row = WorkspaceImapSettings(
            tenant_id=tenant,
            host=body.host.strip(),
            port=body.port,
            email=body.email.strip(),
            password_ciphertext=ciphertext,
            use_ssl=body.use_ssl,
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return _shape_imap(row)


@router.post("/imap/test")
async def test_imap_settings(body: ImapTestBody):
    """Try the credentials WITHOUT saving them. Run in a thread so we don't
    block the event loop. Returns {ok, unread?} or {ok:false, error}."""
    import asyncio
    from automations.imap_poller import test_imap_connection
    return await asyncio.to_thread(
        test_imap_connection, body.host, body.port, body.email, body.password, body.use_ssl,
    )


@router.delete("/imap", status_code=204)
async def delete_imap_settings(db: AsyncSession = Depends(get_db)):
    from db.entities import WorkspaceImapSettings
    tenant = _tenant()
    row = (await db.execute(
        select(WorkspaceImapSettings).where(WorkspaceImapSettings.tenant_id == tenant)
    )).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()


@router.post("/imap/poll-now")
async def poll_imap_now(
    confirm: bool = False,
    request: Request = None,
):
    """Manual trigger so the user can verify poll behavior without waiting
    for the 10-min cycle. Runs the same path as the background loop.

    Confirmation guard: requires either ?confirm=true or the
    X-Confirm-Outbound: yes header. Without it returns 412 so a stray
    double-click doesn't fire a real IMAP scan twice in a row."""
    header_confirm = (request.headers.get("x-confirm-outbound", "").lower() == "yes") if request else False
    if not (confirm or header_confirm):
        raise HTTPException(status_code=412, detail={
            "code": "confirmation_required",
            "message": "This action triggers a live IMAP poll. Pass ?confirm=true "
                       "or X-Confirm-Outbound: yes to proceed.",
        })
    from automations.imap_poller import poll_all_tenants_once
    results = await poll_all_tenants_once()
    return {"ran": True, "results": results}


# ─────────────────────────────────────────────────────────────────────────
# DNS health check — Google + Microsoft tightened bulk-sender enforcement
# in late 2025; SPF + DKIM + DMARC are now enforcement lines, not nice-to-
# haves. Most SDRs don't know if their setup is correct. This endpoint runs
# a live DNS check and reports per-record status with a suggested fix when
# something is missing or weak.
# ─────────────────────────────────────────────────────────────────────────

class DnsCheckBody(BaseModel):
    domain: str = Field(..., min_length=3, max_length=253)
    dkim_selectors: list[str] = Field(
        default_factory=lambda: ["default", "google", "k1", "selector1",
                                  "selector2", "smtpapi", "resend", "s1", "s2"],
        max_length=12,
    )


def _resolve_txt(name: str, timeout: float = 4.0) -> tuple[list[str], Optional[str]]:
    """Return (records, error) tuple. Joined per record (TXT can split into
    multiple quoted strings). Errors are stringified for the FE."""
    import dns.resolver
    import dns.exception
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        answer = resolver.resolve(name, "TXT")
        records = []
        for r in answer:
            # Each record is a sequence of byte strings; concatenate.
            parts = [s.decode("utf-8", errors="replace") for s in r.strings]
            records.append("".join(parts))
        return records, None
    except dns.resolver.NXDOMAIN:
        return [], "nxdomain"
    except dns.resolver.NoAnswer:
        return [], "no_record"
    except dns.exception.Timeout:
        return [], "timeout"
    except Exception as e:
        return [], f"error: {str(e)[:120]}"


def _resolve_mx(domain: str, timeout: float = 4.0) -> tuple[list[dict], Optional[str]]:
    import dns.resolver
    import dns.exception
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        answer = resolver.resolve(domain, "MX")
        return sorted(
            [{"priority": int(r.preference), "host": str(r.exchange).rstrip(".")} for r in answer],
            key=lambda x: x["priority"],
        ), None
    except dns.resolver.NXDOMAIN:
        return [], "nxdomain"
    except dns.resolver.NoAnswer:
        return [], "no_record"
    except dns.exception.Timeout:
        return [], "timeout"
    except Exception as e:
        return [], f"error: {str(e)[:120]}"


def _check_spf(domain: str) -> dict:
    records, err = _resolve_txt(domain)
    if err == "timeout":
        return {"status": "unknown", "detail": "DNS timeout — try again."}
    spf_records = [r for r in records if r.lower().startswith("v=spf1")]
    if not spf_records:
        return {"status": "fail", "detail": "No SPF record (v=spf1).",
                "fix": f"Add a TXT record at {domain}: v=spf1 include:_spf.example -all "
                       "(swap example for your sender, e.g. _spf.google.com)."}
    if len(spf_records) > 1:
        return {"status": "fail", "record": spf_records,
                "detail": "Multiple SPF records — receivers will reject.",
                "fix": "Merge into a single record."}
    rec = spf_records[0]
    if " -all" in rec:
        return {"status": "pass", "record": rec, "detail": "Hard-fail policy (-all)."}
    if " ~all" in rec:
        return {"status": "warn", "record": rec,
                "detail": "Soft-fail (~all) — accepted but spammy.",
                "fix": "Tighten to -all once you've audited senders."}
    if " ?all" in rec or " +all" in rec:
        return {"status": "fail", "record": rec,
                "detail": "Permissive policy (?all/+all) — anyone can spoof.",
                "fix": "Replace with ~all or -all."}
    return {"status": "warn", "record": rec, "detail": "No explicit all qualifier."}


def _check_dmarc(domain: str) -> dict:
    records, err = _resolve_txt(f"_dmarc.{domain}")
    if err in ("nxdomain", "no_record"):
        return {"status": "fail", "detail": "No DMARC record at _dmarc.<domain>.",
                "fix": f"Add a TXT record at _dmarc.{domain}: "
                       "v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com; "
                       "(start with p=none to monitor, then tighten)."}
    if err == "timeout":
        return {"status": "unknown", "detail": "DNS timeout — try again."}
    dmarc = next((r for r in records if r.lower().startswith("v=dmarc1")), None)
    if not dmarc:
        return {"status": "fail", "detail": "TXT exists but no v=DMARC1 record."}
    parts = {kv.split("=", 1)[0].strip(): kv.split("=", 1)[1].strip()
             for kv in dmarc.split(";") if "=" in kv}
    p = (parts.get("p") or "").lower()
    if p == "reject":
        return {"status": "pass", "record": dmarc, "detail": "Strict policy (p=reject)."}
    if p == "quarantine":
        return {"status": "warn", "record": dmarc,
                "detail": "Quarantine policy — spam-folder treatment.",
                "fix": "Tighten to p=reject once you've validated alignment."}
    if p == "none":
        return {"status": "warn", "record": dmarc,
                "detail": "Monitor-only (p=none) — no enforcement.",
                "fix": "Move to p=quarantine after a 2-4 week monitor window."}
    return {"status": "warn", "record": dmarc, "detail": f"Unknown policy p={p!r}."}


def _check_dkim(domain: str, selectors: list[str]) -> dict:
    """Tries each selector in order; returns the first one that resolves."""
    tried = []
    for sel in selectors:
        records, err = _resolve_txt(f"{sel}._domainkey.{domain}")
        if err == "timeout":
            tried.append({"selector": sel, "status": "timeout"})
            continue
        if err in ("nxdomain", "no_record"):
            tried.append({"selector": sel, "status": "missing"})
            continue
        dkim = next((r for r in records if "v=dkim1" in r.lower() or "p=" in r.lower()), None)
        if dkim:
            return {"status": "pass", "selector": sel, "record": dkim[:200],
                    "detail": f"DKIM key found at {sel}._domainkey.{domain}.",
                    "tried": tried + [{"selector": sel, "status": "pass"}]}
    return {"status": "fail", "tried": tried,
            "detail": "No DKIM key at any common selector.",
            "fix": "Configure DKIM with your sender (Resend, Google Workspace, etc.) "
                   "and publish the TXT record they give you. Re-run the check with "
                   "the actual selector your sender uses."}


def _check_mx(domain: str) -> dict:
    records, err = _resolve_mx(domain)
    if err == "nxdomain":
        return {"status": "fail", "detail": "Domain has no DNS records (NXDOMAIN)."}
    if err == "no_record":
        return {"status": "warn", "detail": "No MX records — can't receive replies "
                                              "if you send from this domain."}
    if err == "timeout":
        return {"status": "unknown", "detail": "DNS timeout — try again."}
    if not records:
        return {"status": "warn", "detail": "No MX records found."}
    return {"status": "pass", "records": records,
            "detail": f"{len(records)} MX record(s) — receiving is wired."}


# ─────────────────────────────────────────────────────────────────────────
# Multi-mailbox SMTP routing — list / add / test / disable / delete.
# Each mailbox row is one outbound inbox the user has connected; the
# scheduler picks among them at send time with daily volume caps.
#
# Password is encrypted with the same Fernet key as IMAP. GET endpoints
# never return the ciphertext.
# ─────────────────────────────────────────────────────────────────────────

class MailboxBody(BaseModel):
    email: str = Field(..., min_length=4, max_length=200)
    from_name: Optional[str] = Field(default=None, max_length=200)
    host: str = Field(..., min_length=2, max_length=200)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=400)
    use_tls: bool = True
    daily_send_cap: int = Field(default=50, ge=1, le=2000)


class MailboxTestBody(BaseModel):
    host: str = Field(..., min_length=2, max_length=200)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=400)
    use_tls: bool = True


def _shape_mailbox(m) -> dict:
    """Public shape — never includes password ciphertext."""
    return {
        "id": str(m.id),
        "email": m.email,
        "from_name": m.from_name,
        "host": m.host,
        "port": m.port,
        "username": m.username,
        "use_tls": m.use_tls,
        "enabled": m.enabled,
        "daily_send_cap": m.daily_send_cap,
        "sent_today": m.sent_today or 0,
        "headroom": max(0, (m.daily_send_cap or 0) - (m.sent_today or 0)),
        "last_send_at_unix": int(m.last_send_at.timestamp()) if m.last_send_at else None,
        "last_error": m.last_error,
        "reset_at_unix": int(m.reset_at.timestamp()) if m.reset_at else None,
    }


@router.get("/mailboxes")
async def list_mailboxes(db: AsyncSession = Depends(get_db)):
    from db.entities import WorkspaceMailbox
    rows = (await db.execute(
        select(WorkspaceMailbox)
        .where(WorkspaceMailbox.tenant_id == _tenant())
        .order_by(WorkspaceMailbox.created_at.asc())
    )).scalars().all()
    return {"items": [_shape_mailbox(m) for m in rows]}


@router.post("/mailboxes/test")
async def test_mailbox(body: MailboxTestBody):
    """Live SMTP login attempt with the supplied creds. Doesn't write to DB.
    Wrap blocking smtplib in a thread so we don't stall the event loop."""
    import asyncio
    from automations.smtp_email import test_smtp_connection
    return await asyncio.to_thread(
        test_smtp_connection,
        body.host, body.port, body.username, body.password, body.use_tls,
    )


@router.post("/mailboxes")
async def create_mailbox(body: MailboxBody, db: AsyncSession = Depends(get_db)):
    from automations.imap_poller import _fernet, encrypt_password
    from db.entities import WorkspaceMailbox
    if not _fernet():
        raise HTTPException(status_code=503, detail={
            "code": "no_fernet",
            "message": "IMAP_ENCRYPTION_KEY not set — can't encrypt SMTP creds at rest.",
        })
    ciphertext = encrypt_password(body.password)
    mailbox = WorkspaceMailbox(
        tenant_id=_tenant(),
        email=body.email.strip().lower(),
        from_name=(body.from_name or None),
        host=body.host.strip(),
        port=body.port,
        username=body.username.strip(),
        password_ciphertext=ciphertext,
        use_tls=body.use_tls,
        daily_send_cap=body.daily_send_cap,
    )
    try:
        db.add(mailbox)
        await db.commit()
        await db.refresh(mailbox)
    except Exception as e:
        # Most likely the unique (tenant_id, email) constraint.
        await db.rollback()
        raise HTTPException(status_code=409, detail={
            "code": "mailbox_exists",
            "message": f"A mailbox with email {body.email!r} already exists for this workspace.",
            "details": str(e)[:160],
        })
    return _shape_mailbox(mailbox)


@router.patch("/mailboxes/{mailbox_id}")
async def update_mailbox(mailbox_id: str, body: dict,
                          db: AsyncSession = Depends(get_db)):
    """Partial update — supports daily_send_cap, enabled, from_name. Don't
    accept password edits here; require deletion + recreation so the user
    consciously re-tests the new creds."""
    from db.entities import WorkspaceMailbox
    try:
        mid = uuid.UUID(mailbox_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="not found")
    mb = (await db.execute(
        select(WorkspaceMailbox).where(
            WorkspaceMailbox.id == mid,
            WorkspaceMailbox.tenant_id == _tenant(),
        )
    )).scalar_one_or_none()
    if not mb:
        raise HTTPException(status_code=404, detail="not found")
    if "enabled" in body:
        mb.enabled = bool(body["enabled"])
    if "from_name" in body:
        mb.from_name = (body["from_name"] or None)
    if "daily_send_cap" in body:
        cap = int(body["daily_send_cap"])
        if not (1 <= cap <= 2000):
            raise HTTPException(status_code=422, detail="daily_send_cap must be 1..2000")
        mb.daily_send_cap = cap
    await db.commit()
    await db.refresh(mb)
    return _shape_mailbox(mb)


@router.delete("/mailboxes/{mailbox_id}", status_code=204)
async def delete_mailbox(mailbox_id: str, db: AsyncSession = Depends(get_db)):
    from db.entities import WorkspaceMailbox
    try:
        mid = uuid.UUID(mailbox_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="not found")
    mb = (await db.execute(
        select(WorkspaceMailbox).where(
            WorkspaceMailbox.id == mid,
            WorkspaceMailbox.tenant_id == _tenant(),
        )
    )).scalar_one_or_none()
    if not mb:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(mb)
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────
# Suppression list management. Public unsubscribe endpoint lives in
# routers/public.py — this router is admin-scoped.
# ─────────────────────────────────────────────────────────────────────────

class SuppressionAddBody(BaseModel):
    email: str = Field(..., min_length=4, max_length=200)
    reason: Optional[str] = "manual"
    notes: Optional[str] = Field(default=None, max_length=500)


@router.get("/suppressions")
async def list_suppressions(db: AsyncSession = Depends(get_db)):
    from db.entities import WorkspaceSuppression
    rows = (await db.execute(
        select(WorkspaceSuppression)
        .where(WorkspaceSuppression.tenant_id == _tenant())
        .order_by(WorkspaceSuppression.created_at.desc())
        .limit(500)
    )).scalars().all()
    return {
        "items": [
            {"id": str(r.id), "email": r.email, "reason": r.reason,
             "notes": r.notes,
             "created_at_unix": int(r.created_at.timestamp()) if r.created_at else None}
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/suppressions")
async def add_suppression_endpoint(body: SuppressionAddBody):
    from automations.suppression import add_suppression
    added = await add_suppression(_tenant(), body.email,
                                   reason=body.reason or "manual",
                                   notes=body.notes)
    return {"email": body.email.strip().lower(), "added": added}


@router.delete("/suppressions", status_code=204)
async def remove_suppression_endpoint(email: str):
    from automations.suppression import remove_suppression
    ok = await remove_suppression(_tenant(), email)
    if not ok:
        raise HTTPException(status_code=404, detail="not on suppression list")


# ─────────────────────────────────────────────────────────────────────────
# Daily digest — manual trigger now; auto-cron lands when we wire it into
# the scheduler tick (currently the user clicks Send digest in the UI).
# ─────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────
# Demo data — one-click "fill with sample leads" so a new user can play
# with the product before connecting any real source. Source is set to
# "demo" so deletion is one DELETE statement; reversible.
# ─────────────────────────────────────────────────────────────────────────

_DEMO_LEADS = [
    {"name": "Avani Patel",     "email": "avani@plurio.io",
     "company": "Plurio",       "title": "Co-founder",
     "score": 88, "tags": ["hot"],  "trigger": "funding"},
    {"name": "Marcus Chen",     "email": "marcus@stitch.dev",
     "company": "Stitch",       "title": "Head of Sales",
     "score": 82, "tags": ["hot"],  "trigger": "hiring"},
    {"name": "Léa Bertrand",    "email": "lea@mosaicflow.fr",
     "company": "MosaicFlow",   "title": "VP Marketing",
     "score": 76, "tags": ["warm"], "trigger": "launch"},
    {"name": "Dan O'Reilly",    "email": "dan@wavelength.app",
     "company": "Wavelength",   "title": "Founder",
     "score": 71, "tags": [],      "trigger": None},
    {"name": "Aisha Raman",     "email": "aisha@craftbase.in",
     "company": "Craftbase",    "title": "Growth Lead",
     "score": 84, "tags": ["hot"],  "trigger": "funding"},
    {"name": "Tom Wessel",      "email": "tom@northvale.de",
     "company": "Northvale",    "title": "CTO",
     "score": 68, "tags": [],      "trigger": "tech_stack_change"},
    {"name": "Priya Iyer",      "email": "priya@halocrm.io",
     "company": "HaloCRM",      "title": "Product Lead",
     "score": 79, "tags": ["warm"], "trigger": None},
    {"name": "Kenji Sato",      "email": "kenji@shipstack.jp",
     "company": "Shipstack",    "title": "BizOps",
     "score": 73, "tags": [],      "trigger": "launch"},
    {"name": "Sofia Almeida",   "email": "sofia@pampa.io",
     "company": "Pampa",        "title": "Co-founder",
     "score": 86, "tags": ["hot"],  "trigger": "funding"},
    {"name": "Ravi Murthy",     "email": "ravi@apexline.io",
     "company": "Apexline",     "title": "Head of RevOps",
     "score": 65, "tags": [],      "trigger": None},
    {"name": "Maria Costa",     "email": "maria@ledgerly.co",
     "company": "Ledgerly",     "title": "Founder",
     "score": 90, "tags": ["hot"],  "trigger": "hiring"},
    {"name": "Eli Brooks",      "email": "eli@sparkrun.dev",
     "company": "SparkRun",     "title": "CEO",
     "score": 70, "tags": ["warm"], "trigger": None},
]


@router.post("/demo-data/load")
async def load_demo_data(db: AsyncSession = Depends(get_db)):
    """Insert (or upsert) the 12 sample leads. source='demo' so the user
    can wipe them with one click. Idempotent on (tenant_id, email)."""
    from db.entities import Lead
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    tenant = _tenant()
    inserted = 0
    skipped = 0
    for entry in _DEMO_LEADS:
        existing = (await db.execute(
            select(Lead.id).where(
                Lead.tenant_id == tenant,
                Lead.email == entry["email"],
                Lead.deleted_at == None,  # noqa: E711
            ).limit(1)
        )).scalar_one_or_none()
        if existing:
            skipped += 1
            continue
        triggers = [entry["trigger"]] if entry.get("trigger") else None
        lead = Lead(
            tenant_id=tenant,
            name=entry["name"], email=entry["email"],
            company_name=entry["company"], title=entry["title"],
            source="demo", source_ref_id=None,
            status="new", score=entry["score"],
            score_reason="Demo lead — one-click sample data",
            tags=entry.get("tags") or [],
            triggers=triggers,
        )
        db.add(lead)
        inserted += 1
    await db.commit()
    return {"inserted": inserted, "skipped": skipped, "total": len(_DEMO_LEADS)}


@router.delete("/demo-data", status_code=204)
async def clear_demo_data(db: AsyncSession = Depends(get_db)):
    """Soft-delete every lead with source='demo' for this tenant. Quick
    reset for users who loaded sample data and now want a clean slate."""
    from db.entities import Lead
    rows = (await db.execute(
        select(Lead).where(
            Lead.tenant_id == _tenant(),
            Lead.source == "demo",
            Lead.deleted_at == None,  # noqa: E711
        )
    )).scalars().all()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for r in rows:
        r.deleted_at = now
    await db.commit()


# Per-tenant cooldown for the digest. Confirmation alone doesn't stop two
# *intentional* clicks 5 seconds apart from shipping duplicates to real
# prospects; this in-process map adds a 60-second floor.
_DIGEST_LAST_SENT_AT: dict[str, float] = {}
_DIGEST_COOLDOWN_SEC = 60


@router.post("/digest/send-now")
async def digest_send_now(confirm: bool = False, request: Request = None):
    """Send the weekly digest email immediately. Two guards: (a) require an
    explicit confirm flag, (b) refuse a second send within _DIGEST_COOLDOWN_SEC
    so a rapid double-confirm still can't ship duplicate digests."""
    header_confirm = (request.headers.get("x-confirm-outbound", "").lower() == "yes") if request else False
    if not (confirm or header_confirm):
        raise HTTPException(status_code=412, detail={
            "code": "confirmation_required",
            "message": "This action sends a real digest email. Pass ?confirm=true "
                       "or X-Confirm-Outbound: yes to proceed.",
        })
    import time as _time
    tenant_key = str(_tenant())
    last = _DIGEST_LAST_SENT_AT.get(tenant_key, 0.0)
    now = _time.monotonic()
    elapsed = now - last
    if elapsed < _DIGEST_COOLDOWN_SEC:
        raise HTTPException(status_code=429, detail={
            "code": "cooldown_active",
            "message": f"A digest was sent {int(elapsed)}s ago. Wait "
                       f"{_DIGEST_COOLDOWN_SEC - int(elapsed)}s before re-sending.",
        })
    _DIGEST_LAST_SENT_AT[tenant_key] = now
    from automations.digest import send_digest_for_tenant
    result = await send_digest_for_tenant(_tenant())
    return result


@router.post("/dns-check")
async def dns_check(body: DnsCheckBody):
    """Run a live SPF / DKIM / DMARC / MX lookup for a sending domain.

    Pure DNS reads, no auth into the user's domain — anyone could run the
    same `dig` query. Wrapped in asyncio.to_thread so the resolver doesn't
    block the event loop.
    """
    import asyncio
    domain = body.domain.strip().lower().lstrip("@")
    if not domain or "." not in domain:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": "domain must look like 'example.com'",
        })
    spf, dmarc, dkim, mx = await asyncio.gather(
        asyncio.to_thread(_check_spf, domain),
        asyncio.to_thread(_check_dmarc, domain),
        asyncio.to_thread(_check_dkim, domain, body.dkim_selectors),
        asyncio.to_thread(_check_mx, domain),
    )

    statuses = [c["status"] for c in (spf, dmarc, dkim, mx)]
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses or "unknown" in statuses:
        overall = "warn"
    else:
        overall = "pass"

    return {
        "domain": domain,
        "overall": overall,
        "checks": {"spf": spf, "dmarc": dmarc, "dkim": dkim, "mx": mx},
    }


# ─────────────────────────────────────────────────────────────────────────


async def get_slack_alert_config(tenant_id: uuid.UUID) -> tuple[Optional[str], int]:
    """Return (webhook_url, min_score). When webhook_url is None, alerts off."""
    from db.connection import SessionLocal
    async with SessionLocal() as db:
        row = (await db.execute(
            select(WorkspaceSettings.slack_webhook_url,
                   WorkspaceSettings.slack_alert_min_score)
            .where(WorkspaceSettings.tenant_id == tenant_id)
        )).first()
        if not row:
            return (None, 80)
        return (row[0], row[1] or 80)


async def maybe_alert_slack_hot_lead(
    tenant_id: uuid.UUID,
    *,
    name: str,
    company: Optional[str],
    score: int,
    source: str,
    reason: Optional[str] = None,
    url: Optional[str] = None,
) -> None:
    """Best-effort POST to the workspace's Slack webhook when score crosses
    the threshold. Never raises — alerts are a nice-to-have, not a hard
    dependency of the enrichment path."""
    try:
        webhook, min_score = await get_slack_alert_config(tenant_id)
        if not webhook or score < min_score:
            return
        import httpx
        # Slack blocks payload — renders as a tidy section + context.
        title = f"{name}"
        if company:
            title += f" · {company}"
        ctx_lines = [f"score *{score}*", f"source `{source}`"]
        if reason:
            ctx_lines.append(reason[:200])
        text = f"🔥 New hot lead: {title} (score {score})"
        blocks = [
            {"type": "section", "text": {
                "type": "mrkdwn",
                "text": f"*🔥 {title}*\n{reason or 'New high-fit lead from SmartBiz OS.'}"
            }},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": " · ".join(ctx_lines)}
            ]},
        ]
        if url:
            blocks.append({"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"<{url}|view source>"}
            ]})
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(webhook, json={"text": text, "blocks": blocks})
    except Exception as e:
        log.warning("slack alert failed: %s", e)


async def maybe_alert_slack_run_failed(
    tenant_id: uuid.UUID,
    *,
    run_id: uuid.UUID,
    step: str,
    error: Optional[str],
    lead_email: Optional[str] = None,
    template_key: Optional[str] = None,
) -> None:
    """Best-effort POST when a sequence step fails. Different from the
    hot-lead alert in two ways: ignores the score threshold (any failure
    is worth flagging) and uses a warning-style icon. Never raises."""
    try:
        webhook, _ = await get_slack_alert_config(tenant_id)
        if not webhook:
            return
        import httpx
        text = f"⚠️ Automation step failed: {step}"
        ctx_lines = [f"run `{str(run_id)[:8]}`", f"step `{step}`"]
        if template_key:
            ctx_lines.append(f"template `{template_key}`")
        if lead_email:
            ctx_lines.append(f"to `{lead_email}`")
        body_md = f"*⚠️ {step} failed*\n```{(error or 'no error message')[:400]}```"
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": body_md}},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": " · ".join(ctx_lines)}
            ]},
        ]
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(webhook, json={"text": text, "blocks": blocks})
    except Exception as e:
        log.warning("slack run-failure alert failed: %s", e)

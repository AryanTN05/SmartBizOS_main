"""Suppression list + 1-click unsubscribe helpers.

Three responsibilities, all keyed on (tenant_id, email):

  1. is_suppressed(tenant_id, email)  — fast lookup before the scheduler
     spends an LLM render or an SMTP send.
  2. add_suppression(...)              — write the row idempotently.
  3. unsubscribe tokens                 — opaque, HMAC-signed so the public
     unsubscribe endpoint can verify a click without a separate per-email
     row in the DB. Token format: base64url(lead_id) + "." + hex(hmac_sha256).

The scheduler calls is_suppressed before render and again before send so
late-arriving suppressions (a bounce that landed mid-sequence) are
honored without restarting the run.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import uuid as _uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.connection import SessionLocal
from db.entities import Lead, WorkspaceSuppression

log = logging.getLogger("smartbiz.suppression")


def _unsub_secret() -> str:
    """Reuse JWT_SECRET if no dedicated unsubscribe secret is set; this
    is fine because the unsubscribe token is per-(lead_id) and not a
    privilege-elevation surface — worst case an attacker who compromises
    the secret can unsubscribe other peoples' leads (annoying, not
    catastrophic). In production, set UNSUBSCRIBE_SECRET separately."""
    return (os.getenv("UNSUBSCRIBE_SECRET") or os.getenv("JWT_SECRET")
            or "dev-secret-change-me")


def make_unsubscribe_token(lead_id: _uuid.UUID, tenant_id: _uuid.UUID) -> str:
    """Returns 'leadid.signature'. Verifiable without a DB roundtrip."""
    payload = f"{lead_id}:{tenant_id}".encode()
    sig = hmac.new(_unsub_secret().encode(), payload, hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(str(lead_id).encode()).rstrip(b"=").decode()
    return f"{encoded}.{sig[:32]}"


def verify_unsubscribe_token(token: str, lead_id: _uuid.UUID,
                              tenant_id: _uuid.UUID) -> bool:
    if not token or "." not in token:
        return False
    expected = make_unsubscribe_token(lead_id, tenant_id)
    return hmac.compare_digest(token, expected)


def parse_lead_id_from_token(token: str) -> Optional[_uuid.UUID]:
    """Pull the lead_id out of a token without verifying. Caller must
    verify_unsubscribe_token() before trusting it."""
    if not token or "." not in token:
        return None
    encoded = token.split(".", 1)[0]
    try:
        # add padding back
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        return _uuid.UUID(decoded)
    except Exception:
        return None


def public_unsubscribe_url(lead_id: _uuid.UUID, tenant_id: _uuid.UUID,
                            base: Optional[str] = None) -> str:
    """The href that goes into the email's footer + List-Unsubscribe header.
    `base` should be the public origin of the API (e.g. https://api.example.com)."""
    base = base or os.getenv("PUBLIC_API_ORIGIN") or os.getenv("APP_BASE_URL", "")
    base = base.rstrip("/")
    token = make_unsubscribe_token(lead_id, tenant_id)
    return f"{base}/api/u/{token}"


def list_unsubscribe_headers(lead_id: _uuid.UUID, tenant_id: _uuid.UUID) -> dict:
    """RFC 2369 + RFC 8058 headers. List-Unsubscribe-Post is what makes
    the Gmail/Outlook one-click button work without leaving the inbox."""
    url = public_unsubscribe_url(lead_id, tenant_id)
    return {
        "List-Unsubscribe": f"<{url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


# ─────────────────────────────────────────────────────────────────────────
# DB lookups + writes — all (tenant_id, email) keyed.
# ─────────────────────────────────────────────────────────────────────────


async def is_suppressed(tenant_id: _uuid.UUID, email: str) -> bool:
    """Fast pre-send check. Returns True if either the suppression list
    has the (tenant, email) pair OR the matching lead is unsubscribed."""
    if not email:
        return False
    e = email.strip().lower()
    async with SessionLocal() as db:
        hit = (await db.execute(
            select(WorkspaceSuppression.id).where(
                WorkspaceSuppression.tenant_id == tenant_id,
                WorkspaceSuppression.email == e,
            ).limit(1)
        )).scalar_one_or_none()
        if hit:
            return True
        # Cheap secondary check — the lead row itself may carry an
        # unsubscribed_at if a click came in but the row hasn't been
        # written to the suppressions table for some reason.
        lead_unsub = (await db.execute(
            select(Lead.id).where(
                Lead.tenant_id == tenant_id,
                Lead.email == e,
                Lead.unsubscribed_at != None,  # noqa: E711
                Lead.deleted_at == None,  # noqa: E711
            ).limit(1)
        )).scalar_one_or_none()
        return lead_unsub is not None


async def add_suppression(tenant_id: _uuid.UUID, email: str,
                           *, reason: str, notes: Optional[str] = None) -> bool:
    """Idempotent insert. Returns True if a new row was created, False if
    already present."""
    if not email:
        return False
    e = email.strip().lower()
    if reason not in ("manual", "user_unsub", "bounce_hard",
                      "bounce_soft", "complained"):
        log.warning("add_suppression: unknown reason %r — coercing to 'manual'", reason)
        reason = "manual"
    async with SessionLocal() as db:
        # ON CONFLICT DO NOTHING — Postgres returns the row count we can use
        # to tell whether we actually added something.
        stmt = pg_insert(WorkspaceSuppression).values(
            tenant_id=tenant_id, email=e, reason=reason, notes=notes,
        ).on_conflict_do_nothing(index_elements=["tenant_id", "email"])
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0


async def remove_suppression(tenant_id: _uuid.UUID, email: str) -> bool:
    """Manual user-initiated removal (re-engaging an old lead). Returns
    True if a row was deleted."""
    if not email:
        return False
    e = email.strip().lower()
    async with SessionLocal() as db:
        row = (await db.execute(
            select(WorkspaceSuppression).where(
                WorkspaceSuppression.tenant_id == tenant_id,
                WorkspaceSuppression.email == e,
            )
        )).scalar_one_or_none()
        if not row:
            return False
        await db.delete(row)
        await db.commit()
        return True

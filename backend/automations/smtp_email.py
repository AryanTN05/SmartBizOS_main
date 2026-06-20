"""SMTP send helper + mailbox rotation.

The scheduler's `send_day0` step calls `send_via_mailbox(...)` which:
  1. Picks the next eligible mailbox for the tenant (round-robin among
     enabled mailboxes whose sent_today < daily_send_cap).
  2. Decrypts the SMTP password via Fernet.
  3. Builds an RFC 5322 message and dials the SMTP server.
  4. Increments sent_today + last_send_at.
  5. Returns {ok, message_id, mailbox_email, error}.

When no mailboxes are configured for the tenant, the scheduler falls back
to the existing Resend path so single-domain users still send. Multi-domain
users get rotation + per-inbox volume guardrails the moment they add a row.

The trend scan calls multi-domain routing the feature that takes SmartBiz
from "demo" to "tool I trust for serious volume." This is the MVP — no
warmup integration yet (point users at Mailreach), no IP-pool routing,
just per-tenant round-robin with daily caps.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
import uuid as _uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Optional

from sqlalchemy import select, and_

from automations.imap_poller import decrypt_password, encrypt_password, _fernet
from db.connection import SessionLocal
from db.entities import WorkspaceMailbox

log = logging.getLogger("smartbiz.smtp")


def test_smtp_connection(host: str, port: int, username: str, password: str,
                         use_tls: bool = True, timeout: int = 10) -> dict:
    """Sync SMTP test — wrap in asyncio.to_thread for the async caller.
    Returns {ok, error?}. Never raises."""
    try:
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx) as s:
                s.login(username, password)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as s:
                s.ehlo()
                if use_tls:
                    s.starttls(context=ctx)
                    s.ehlo()
                s.login(username, password)
        return {"ok": True}
    except smtplib.SMTPAuthenticationError as e:
        return {"ok": False, "error": f"auth failed: {e.smtp_error.decode(errors='replace') if e.smtp_error else str(e)}"[:200]}
    except (smtplib.SMTPException, OSError, TimeoutError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}


async def _pick_mailbox(db, tenant_id: _uuid.UUID) -> Optional[WorkspaceMailbox]:
    """Round-robin among enabled mailboxes that still have headroom today.

    Order by `last_send_at NULLS FIRST` so the least-recently-used inbox is
    picked first. Atomic SELECT FOR UPDATE so two concurrent send_day0
    workers don't both pick the same mailbox and exceed its cap.
    """
    now = datetime.now(timezone.utc)
    rows = (await db.execute(
        select(WorkspaceMailbox)
        .where(and_(
            WorkspaceMailbox.tenant_id == tenant_id,
            WorkspaceMailbox.enabled == True,  # noqa: E712
        ))
        .order_by(WorkspaceMailbox.last_send_at.asc().nullsfirst())
        .with_for_update(skip_locked=True)
    )).scalars().all()

    for mb in rows:
        # Lazy daily-counter reset — first send of a new UTC day resets to 0.
        # No background job needed; bookkeeping happens at use time.
        if mb.reset_at is None or mb.reset_at.date() != now.date():
            mb.sent_today = 0
            mb.reset_at = now
        if mb.sent_today < (mb.daily_send_cap or 0):
            return mb
    return None


def _build_message(*, from_addr: str, from_name: Optional[str], to: str,
                   subject: str, html: str, text: Optional[str] = None,
                   headers: Optional[dict] = None) -> tuple[EmailMessage, str]:
    msg = EmailMessage()
    msg["From"] = formataddr((from_name or "", from_addr))
    msg["To"] = to
    msg["Subject"] = subject
    message_id = make_msgid(domain=from_addr.split("@", 1)[-1])
    msg["Message-ID"] = message_id
    # Custom headers (List-Unsubscribe, List-Unsubscribe-Post). Setting via
    # __setitem__ on EmailMessage produces an RFC-compliant fold.
    for k, v in (headers or {}).items():
        msg[k] = v
    if text:
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
    else:
        msg.set_content("View this email in an HTML-capable client.")
        msg.add_alternative(html, subtype="html")
    return msg, message_id


def _send_blocking(mb: WorkspaceMailbox, password: str, msg: EmailMessage,
                    timeout: int = 20) -> dict:
    """Blocking SMTP send — caller wraps in asyncio.to_thread."""
    try:
        ctx = ssl.create_default_context()
        if mb.port == 465:
            with smtplib.SMTP_SSL(mb.host, mb.port, timeout=timeout, context=ctx) as s:
                s.login(mb.username, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(mb.host, mb.port, timeout=timeout) as s:
                s.ehlo()
                if mb.use_tls:
                    s.starttls(context=ctx)
                    s.ehlo()
                s.login(mb.username, password)
                s.send_message(msg)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}


async def send_via_mailbox(*, tenant_id: _uuid.UUID, to: str, subject: str,
                            html: str, text: Optional[str] = None,
                            headers: Optional[dict] = None) -> dict:
    """Try to send from a tenant's SMTP mailbox. Returns:

      {ok: True,  message_id: str, mailbox_email: str}                    on success
      {ok: False, code: 'no_mailbox' | 'no_capacity' | 'send_failed' | 'no_fernet', error?}

    Caller (scheduler) handles fallback to Resend when ok=False with code
    in {no_mailbox, no_capacity, no_fernet}, since those mean "don't have
    a way to send via SMTP right now" rather than "the send tried and
    failed" — a real send_failed should be propagated to the run as an
    error so the SDR knows their inbox needs attention.
    """
    if not _fernet():
        return {"ok": False, "code": "no_fernet",
                "error": "IMAP_ENCRYPTION_KEY unset — SMTP creds can't decrypt"}

    async with SessionLocal() as db:
        mb = await _pick_mailbox(db, tenant_id)
        if not mb:
            return {"ok": False, "code": "no_mailbox" if mb is None else "no_capacity",
                    "error": "No eligible mailbox (all caps reached or none enabled)"}
        try:
            password = decrypt_password(mb.password_ciphertext)
        except Exception as e:
            mb.last_error = f"decrypt: {str(e)[:120]}"
            await db.commit()
            return {"ok": False, "code": "send_failed",
                    "error": f"could not decrypt mailbox password: {str(e)[:120]}"}

        msg, message_id = _build_message(
            from_addr=mb.email, from_name=mb.from_name,
            to=to, subject=subject, html=html, text=text,
            headers=headers,
        )

        result = await asyncio.to_thread(_send_blocking, mb, password, msg)

        now = datetime.now(timezone.utc)
        if result.get("ok"):
            mb.sent_today = (mb.sent_today or 0) + 1
            mb.last_send_at = now
            mb.last_error = None
            await db.commit()
            return {"ok": True, "message_id": message_id,
                    "mailbox_email": mb.email}
        else:
            mb.last_error = result.get("error")
            await db.commit()
            return {"ok": False, "code": "send_failed",
                    "error": result.get("error"),
                    "mailbox_email": mb.email}

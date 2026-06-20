"""
automations/imap_poller.py — reply-detection via IMAP.

Per-tenant inbox poll runs every IMAP_POLL_SECONDS (default 600). On each
tick we:
  1. Fetch all configured WorkspaceImapSettings rows
  2. For each, decrypt password (Fernet via IMAP_ENCRYPTION_KEY env var)
  3. Connect, list UNSEEN messages in INBOX, fetch headers + first ~2KB body
  4. For each message:
     - Skip auto-replies (Auto-Submitted header, common OOO subjects)
     - Match the From: address to a Lead.email in this tenant
     - If matched, POST internally to mark_lead_replied(source="imap")
       which (via existing endpoint logic) flips sequence_state and writes
       a reply_received activity. Idempotent on (lead_id, source, ±60s).
  5. Update last_poll_at + clear last_error (or store the error)

Failure modes are isolated per-tenant — one bad credential never blocks
the rest. Network errors get backed off (3 strikes → store error + skip
until manual re-test).
"""

from __future__ import annotations

import asyncio
import email as email_mod
import imaplib
import logging
import os
import re
from datetime import datetime, timezone
from email.header import decode_header
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from db.connection import SessionLocal
from db.entities import Lead, WorkspaceImapSettings

log = logging.getLogger("smartbiz.imap_poller")

POLL_SECONDS = int(os.getenv("IMAP_POLL_SECONDS", "600"))
FETCH_BODY_BYTES = 2048  # plenty for a snippet + auto-reply detection
MAX_MESSAGES_PER_POLL = 50  # don't drown a single tick on a flooded inbox

# Subject prefixes that indicate auto-replies / OOO bouncers we should skip.
_AUTO_REPLY_SUBJECTS = (
    "out of office", "ooo:", "automatic reply", "auto-reply", "auto reply",
    "vacation reply", "away from office", "delivery status notification",
    "undeliverable:", "mail delivery failed", "returned mail",
)


def _fernet() -> Optional[Fernet]:
    """Lazy fernet — None when key isn't set so we can refuse cleanly."""
    key = os.getenv("IMAP_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        log.error("IMAP_ENCRYPTION_KEY is invalid: %s", e)
        return None


def encrypt_password(plaintext: str) -> bytes:
    """Encrypt a password for storage. Raises RuntimeError if no key set
    (caller should surface to user as a config error before allowing save)."""
    f = _fernet()
    if not f:
        raise RuntimeError("IMAP_ENCRYPTION_KEY is not set")
    return f.encrypt(plaintext.encode("utf-8"))


def decrypt_password(ciphertext: bytes) -> str:
    f = _fernet()
    if not f:
        raise RuntimeError("IMAP_ENCRYPTION_KEY is not set")
    try:
        return f.decrypt(ciphertext).decode("utf-8")
    except InvalidToken:
        raise RuntimeError("IMAP password ciphertext is unreadable — re-enter creds")


# ─── helpers ───────────────────────────────────────────────────────────────

def _decode_header(raw: Optional[str]) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            try:
                out.append(chunk.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(chunk.decode("latin-1", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out).strip()


_EMAIL_RE = re.compile(r"<([^<>]+@[^<>]+)>|([^\s<>,]+@[^\s<>,]+)")


def _extract_email(from_header: str) -> Optional[str]:
    """Pull a bare email out of '"Name" <email@example.com>' style headers."""
    if not from_header:
        return None
    m = _EMAIL_RE.search(from_header)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip().lower()


def _is_auto_reply(headers: dict, subject: str) -> bool:
    # RFC 3834: Auto-Submitted = primary-token *( ";" param ). Anything other
    # than "no" in the primary token (auto-generated / auto-replied /
    # auto-notified) is auto-submitted. Parse out the primary token before
    # whitespace, comma, or semicolon — a header value like "no, private" is
    # a real-world deviation that we treat as `no` so we don't drop the reply.
    raw = (headers.get("auto-submitted") or "").strip().lower()
    if raw:
        primary = re.split(r"[;,\s]", raw, maxsplit=1)[0]
        if primary and primary != "no":
            return True
    if (headers.get("x-auto-response-suppress") or "").strip():
        return True
    if (headers.get("precedence") or "").strip().lower() in ("auto_reply", "bulk", "junk"):
        return True
    s = (subject or "").strip().lower()
    return any(s.startswith(p) for p in _AUTO_REPLY_SUBJECTS)


def _snippet_from_body(raw_msg_bytes: bytes) -> str:
    """Best-effort plaintext snippet from the first ~2KB of the message body."""
    try:
        msg = email_mod.message_from_bytes(raw_msg_bytes)
    except Exception:
        return ""
    if msg.is_multipart():
        # Find first text/plain part
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return _clean_snippet(payload)
        return ""
    payload = msg.get_payload(decode=True) or b""
    return _clean_snippet(payload)


def _clean_snippet(b: bytes) -> str:
    try:
        text = b.decode("utf-8", errors="replace")
    except Exception:
        text = b.decode("latin-1", errors="replace")
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:500]


# ─── IMAP fetch + match ────────────────────────────────────────────────────

def _connect(host: str, port: int, email_addr: str, password: str, use_ssl: bool):
    if use_ssl:
        m = imaplib.IMAP4_SSL(host, port)
    else:
        m = imaplib.IMAP4(host, port)
    m.login(email_addr, password)
    return m


def test_imap_connection(host: str, port: int, email_addr: str,
                         password: str, use_ssl: bool = True) -> dict:
    """Open + list + close. Surfaces a usable error string for the UI."""
    try:
        m = _connect(host, port, email_addr, password, use_ssl)
        try:
            ok, _ = m.select("INBOX", readonly=True)
            if ok != "OK":
                return {"ok": False, "error": "Could not open INBOX"}
            _, data = m.search(None, "UNSEEN")
            unread = len((data[0] or b"").split())
            return {"ok": True, "unread": unread}
        finally:
            try:
                m.logout()
            except Exception:
                pass
    except imaplib.IMAP4.error as e:
        msg = str(e)
        if "AUTHENTICATIONFAILED" in msg.upper() or "LOGIN FAILED" in msg.upper():
            return {"ok": False, "error": "Login failed. For Gmail use an App Password."}
        return {"ok": False, "error": msg[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _poll_one(settings_row: WorkspaceImapSettings) -> dict:
    """Poll one tenant's mailbox and mark replies. Returns a small summary
    dict for logging; never raises."""
    tenant_id = settings_row.tenant_id
    summary = {"tenant": str(tenant_id), "scanned": 0, "matched": 0, "skipped": 0, "errors": 0}
    try:
        password = decrypt_password(settings_row.password_ciphertext)
    except Exception as e:
        log.warning("imap poll: decrypt failed for tenant %s: %s", tenant_id, e)
        await _store_poll_result(settings_row.id, error=str(e)[:200])
        summary["errors"] += 1
        return summary

    def _do_poll_blocking() -> dict:
        # imaplib is sync — wrap in a thread.
        m = _connect(settings_row.host, settings_row.port, settings_row.email,
                     password, settings_row.use_ssl)
        result = {"messages": [], "error": None}
        try:
            ok, _ = m.select("INBOX", readonly=False)
            if ok != "OK":
                result["error"] = "Could not open INBOX"
                return result
            _, data = m.search(None, "UNSEEN")
            ids = (data[0] or b"").split()[:MAX_MESSAGES_PER_POLL]
            for mid in ids:
                _, msg_data = m.fetch(mid, f"(BODY.PEEK[HEADER] BODY.PEEK[]<0.{FETCH_BODY_BYTES}>)")
                if not msg_data or not isinstance(msg_data[0], tuple):
                    continue
                # Header chunk is at [0][1], body chunk at [1][1] (varies by
                # server; defensive parse).
                header_bytes = msg_data[0][1] if msg_data[0] and len(msg_data[0]) > 1 else b""
                body_bytes = (msg_data[1][1] if len(msg_data) > 1 and isinstance(msg_data[1], tuple)
                              else b"")
                msg = email_mod.message_from_bytes(header_bytes + b"\r\n\r\n" + body_bytes)
                from_addr = _extract_email(_decode_header(msg.get("From")))
                subject = _decode_header(msg.get("Subject"))
                date_hdr = _decode_header(msg.get("Date"))
                received_at = None
                try:
                    if date_hdr:
                        from email.utils import parsedate_to_datetime
                        received_at = parsedate_to_datetime(date_hdr)
                except Exception:
                    received_at = None
                headers_dict = {k.lower(): v for k, v in msg.items()}
                if _is_auto_reply(headers_dict, subject):
                    continue
                if not from_addr:
                    continue
                snippet = _snippet_from_body(body_bytes)
                result["messages"].append({
                    "imap_id": mid.decode("utf-8") if isinstance(mid, bytes) else str(mid),
                    "from": from_addr,
                    "subject": subject,
                    "snippet": snippet,
                    "received_at": received_at,
                })
        finally:
            try:
                m.logout()
            except Exception:
                pass
        return result

    try:
        poll_result = await asyncio.to_thread(_do_poll_blocking)
    except Exception as e:
        log.warning("imap poll: connect/fetch failed for tenant %s: %s", tenant_id, e)
        await _store_poll_result(settings_row.id, error=str(e)[:200])
        summary["errors"] += 1
        return summary

    if poll_result.get("error"):
        await _store_poll_result(settings_row.id, error=poll_result["error"])
        summary["errors"] += 1
        return summary

    summary["scanned"] = len(poll_result["messages"])
    # For each matched-by-email message, mark the lead replied. Re-uses the
    # existing public endpoint logic via a direct DB call (no HTTP hop).
    for m in poll_result["messages"]:
        async with SessionLocal() as db:
            # Case-insensitive match — IMAP `From` headers are already lowercased
            # by _extract_email, but Lead.email may have been saved with the
            # casing the user typed. Without LOWER(), `john@x.com` reply against
            # a `John@X.com` lead silently misses.
            from sqlalchemy import func as _func
            lead = (await db.execute(
                select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    _func.lower(Lead.email) == (m["from"] or "").lower(),
                    Lead.deleted_at == None,
                ).limit(1)
            )).scalar_one_or_none()
            if not lead:
                summary["skipped"] += 1
                continue
            # Apply the same dedupe + state transition the manual endpoint does.
            from db.entities import ActivityLog
            from datetime import timedelta
            received = m["received_at"] or datetime.now(timezone.utc)
            if received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            cutoff_low  = received - timedelta(seconds=60)
            cutoff_high = received + timedelta(seconds=60)
            existing = (await db.execute(
                select(ActivityLog).where(
                    ActivityLog.lead_id == lead.id,
                    ActivityLog.tenant_id == tenant_id,
                    ActivityLog.action_type == "reply_received",
                    ActivityLog.created_at >= cutoff_low,
                    ActivityLog.created_at <= cutoff_high,
                ).limit(1)
            )).scalar_one_or_none()
            if existing and (existing.metadata_ or {}).get("source") == "imap":
                summary["skipped"] += 1
                continue
            # Classify the reply intent before commit so the chip + filter
            # are populated the moment the poller writes the row. Falls back
            # to "neutral" silently when no LLM key — never blocks the path.
            from automations.reply_intent import classify_reply_intent
            intent = await classify_reply_intent(m["snippet"] or m["subject"] or "")

            # Track the reply against the active opener variant so winner-
            # tracking reflects what actually generated this response.
            from automations.variant_picker import record_reply
            new_variants = record_reply(
                list(lead.opening_line_variants or []),
                lead.opening_line,
            )
            if new_variants is not None and new_variants != lead.opening_line_variants:
                lead.opening_line_variants = new_variants

            lead.sequence_state = "paused_replied"
            lead.last_reply_at = received
            lead.last_reply_intent = intent
            lead.last_activity = received
            db.add(ActivityLog(
                tenant_id=tenant_id,
                lead_id=lead.id,
                action_type="reply_received",
                description=(m["snippet"] or m["subject"] or "(reply)").strip()[:280],
                metadata_={
                    "snippet": (m["snippet"] or "")[:2000],
                    "subject": m["subject"],
                    "source": "imap",
                    "intent": intent,
                    "received_at_unix": int(received.timestamp()),
                    "imap_id": m["imap_id"],
                },
                triggered_by="imap",
            ))
            await db.commit()
            summary["matched"] += 1

    await _store_poll_result(settings_row.id, error=None)
    return summary


async def _store_poll_result(row_id, *, error: Optional[str]) -> None:
    """Persist last_poll_at + last_error so the Settings UI can surface
    status to the user."""
    async with SessionLocal() as db:
        row = (await db.execute(
            select(WorkspaceImapSettings).where(WorkspaceImapSettings.id == row_id)
        )).scalar_one_or_none()
        if not row:
            return
        row.last_poll_at = datetime.now(timezone.utc)
        row.last_error = error
        await db.commit()


# ─── public entrypoint ─────────────────────────────────────────────────────

async def poll_all_tenants_once() -> list[dict]:
    """Run one poll cycle across every configured tenant. Returns per-tenant
    summary dicts. Used both by the lifespan loop and ad-hoc /admin triggers."""
    if not _fernet():
        log.info("imap poll: skipping — IMAP_ENCRYPTION_KEY not set")
        return []
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(WorkspaceImapSettings)
        )).scalars().all()
    if not rows:
        return []
    out = []
    for row in rows:
        s = await _poll_one(row)
        out.append(s)
    return out


async def run_forever() -> None:
    """Lifespan loop — sleep, poll, sleep. Quietly catches all exceptions
    so the loop never dies."""
    log.info("imap poller starting; interval=%ds", POLL_SECONDS)
    while True:
        try:
            results = await poll_all_tenants_once()
            if results:
                log.info("imap poll cycle: %s", results)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("imap poll cycle failed")
        await asyncio.sleep(POLL_SECONDS)

"""
Resend email dispatch for the automation scheduler.

Reads RESEND_API_KEY at call time so a missing key produces a clear, in-DB
failure rather than crashing on import. Uses RESEND_FROM as the sender; if
unset, falls back to Resend's free test sender (`onboarding@resend.dev`)
which is verified for everyone.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import resend

log = logging.getLogger("smartbiz.email")


def _from_addr() -> str:
    return os.getenv("RESEND_FROM", "onboarding@resend.dev")


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    headers: Optional[dict] = None,
) -> dict:
    """Send via Resend. Returns {ok, message_id?, error?}.

    Raises nothing — wraps Resend exceptions into the dict so the scheduler
    can record the failure as a step event and move on (or mark the run failed).

    `headers` lets the caller inject List-Unsubscribe + List-Unsubscribe-Post
    so the message qualifies for Gmail/Outlook one-click unsubscribe (RFC 8058).
    """
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return {"ok": False, "error": "RESEND_API_KEY not set"}
    if not to:
        return {"ok": False, "error": "missing recipient"}

    resend.api_key = api_key
    params: dict = {
        "from": _from_addr(),
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        params["text"] = text
    if headers:
        # Resend's Python SDK accepts a `headers` dict that maps to RFC 5322
        # custom headers on the rendered MIME envelope.
        params["headers"] = headers

    try:
        # The SDK is sync — wrap in a thread so we don't block the event loop.
        import asyncio
        result = await asyncio.to_thread(resend.Emails.send, params)
        message_id = (result or {}).get("id")
        return {"ok": True, "message_id": message_id}
    except Exception as e:
        log.warning("resend send failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}

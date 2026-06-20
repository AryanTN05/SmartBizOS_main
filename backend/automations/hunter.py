"""
Hunter.io wrapper for B2B email discovery + verification.

Three operations exposed to the enrichment pipeline:
  - domain_search(domain): pulls likely emails + roles for a company domain
  - email_finder(domain, first, last): builds + verifies a specific person's email
  - email_verifier(email): standalone deliverability check

All three return plain dicts (never raise) so the enrichment pipeline can
treat missing keys / 429s / network failures as "no result" without crashing.

Free tier: 25 searches + 50 verifications per month. We bias usage toward
verification (cheaper) and only domain-search when no email is known yet.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

log = logging.getLogger("smartbiz.hunter")

_BASE = "https://api.hunter.io/v2"


def _key() -> Optional[str]:
    return os.getenv("HUNTER_API_KEY")


async def domain_search(domain: str, limit: int = 5) -> dict:
    """Pull the top-N most-likely emails + their roles for a company domain.
    Returns {emails: [{value, type, confidence, position, ...}], pattern, ...}
    or {} on failure / no key."""
    api_key = _key()
    if not api_key or not domain:
        return {}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(f"{_BASE}/domain-search", params={
                "domain": domain, "api_key": api_key, "limit": limit,
                "type": "personal",
            })
        if resp.status_code in (402, 429, 451):
            log.info("hunter domain_search: rate-limited / out of credits (%s)", resp.status_code)
            return {}
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        emails = []
        for e in (data.get("emails") or [])[:limit]:
            emails.append({
                "value": e.get("value"),
                "confidence": e.get("confidence"),
                "type": e.get("type"),
                "position": e.get("position"),
                "first_name": e.get("first_name"),
                "last_name": e.get("last_name"),
                "linkedin": e.get("linkedin"),
            })
        return {
            "domain": data.get("domain"),
            "organization": data.get("organization"),
            "industry": data.get("industry"),
            "country": data.get("country"),
            "headcount": data.get("headcount"),
            "pattern": data.get("pattern"),
            "emails": emails,
        }
    except Exception as e:
        log.warning("hunter domain_search failed for %s: %s", domain, e)
        return {}


async def email_verifier(email: str) -> dict:
    """Standalone deliverability check. Returns {result, score, status, ...}.
    `result` is one of: deliverable / undeliverable / risky / unknown."""
    api_key = _key()
    if not api_key or not email or "@" not in email:
        return {}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(f"{_BASE}/email-verifier", params={
                "email": email, "api_key": api_key,
            })
        if resp.status_code in (402, 429, 451):
            log.info("hunter verifier: rate-limited / out of credits (%s)", resp.status_code)
            return {}
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        return {
            "email": data.get("email"),
            "result": data.get("result"),  # deliverable / undeliverable / risky / unknown
            "score": data.get("score"),
            "status": data.get("status"),
            "regexp": data.get("regexp"),
            "gibberish": data.get("gibberish"),
            "disposable": data.get("disposable"),
            "webmail": data.get("webmail"),
            "mx_records": data.get("mx_records"),
            "smtp_check": data.get("smtp_check"),
            "accept_all": data.get("accept_all"),
            "block": data.get("block"),
        }
    except Exception as e:
        log.warning("hunter verifier failed for %s: %s", email, e)
        return {}

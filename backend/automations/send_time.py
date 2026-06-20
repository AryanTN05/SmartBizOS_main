"""Send-time optimization — pick the next "good" local hour for a recipient.

The scheduler used to fire `next_fire_at = NOW` for every queued run. That
sends emails at random local times, which kills open + reply rates: an
email landing at 4am UTC for a prospect in San Francisco hits the inbox
when they're asleep and gets buried by morning's first triage pass.

This helper estimates a prospect's timezone from cheap signals:
  1. Email TLD (`.de`, `.jp`, `.in`, `.uk`, `.au`, etc) → fixed offset
  2. Company domain TLD if email is generic (.com gmail.com etc)
  3. Default fallback: America/Los_Angeles (most B2B SaaS targets)

Then snaps to the next 9-11 AM window in that timezone. Callers (the
`/runs` endpoint and the manual-send paths) use this when the workspace
has `send_time_optimization=true` in settings.

Heuristic, not GPS — false positives just shift a few hours, never break
anything. The right way is to ask the user, but most users don't know
their prospect's TZ either.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

# TLD → IANA-ish UTC offset in hours. Daylight savings is intentionally
# ignored — close enough for "send during business hours" and infinitely
# simpler than carrying pytz+zoneinfo through the scheduler.
_TLD_OFFSETS_H: dict[str, float] = {
    "us": -8.0, "ca": -8.0,                 # NA west default; not perfect for east coast .ca
    "uk": 0.0, "ie": 0.0, "pt": 0.0,
    "de": 1.0, "fr": 1.0, "nl": 1.0, "es": 1.0, "it": 1.0,
    "ch": 1.0, "at": 1.0, "be": 1.0, "se": 1.0, "no": 1.0, "dk": 1.0,
    "pl": 1.0, "cz": 1.0,
    "fi": 2.0, "gr": 2.0, "ro": 2.0, "ee": 2.0, "lt": 2.0, "lv": 2.0,
    "ua": 2.0, "ru": 3.0, "tr": 3.0, "sa": 3.0, "ae": 4.0, "il": 2.0,
    "in": 5.5, "pk": 5.0, "lk": 5.5, "bd": 6.0,
    "th": 7.0, "vn": 7.0, "id": 7.0, "my": 8.0, "sg": 8.0, "ph": 8.0,
    "cn": 8.0, "hk": 8.0, "tw": 8.0,
    "jp": 9.0, "kr": 9.0,
    "au": 10.0, "nz": 12.0,
    "br": -3.0, "ar": -3.0, "cl": -4.0, "co": -5.0, "mx": -6.0, "pe": -5.0,
    "za": 2.0, "ng": 1.0, "ke": 3.0, "eg": 2.0,
}

# Common email providers — when domain is generic, fall back to default.
_GENERIC_PROVIDERS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com",
    "hotmail.com", "icloud.com", "me.com", "live.com", "aol.com",
    "protonmail.com", "pm.me", "zoho.com", "fastmail.com",
}


def _domain_for(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].strip().lower()


def offset_hours_for(*, email: Optional[str] = None,
                     company_domain: Optional[str] = None) -> float:
    """Pick a UTC offset in hours. Tries email TLD first, then company
    domain, then defaults to PT (-8) — the most common B2B SaaS center."""
    candidates = []
    for d in (_domain_for(email), (company_domain or "").strip().lower()):
        if d and d not in _GENERIC_PROVIDERS:
            candidates.append(d)

    for d in candidates:
        # Match the rightmost label after the last dot; for ccTLDs like
        # `.co.uk` we look at "uk" (last label) which our table covers.
        parts = d.split(".")
        if len(parts) >= 2:
            tld = parts[-1]
            if tld in _TLD_OFFSETS_H:
                return _TLD_OFFSETS_H[tld]
    return -8.0  # PT default


def next_send_window(now_utc: Optional[datetime] = None,
                      *, email: Optional[str] = None,
                      company_domain: Optional[str] = None,
                      morning_hour_local: int = 9,
                      latest_hour_local: int = 16) -> datetime:
    """Return a UTC datetime that lands in the prospect's next
    [morning_hour_local, latest_hour_local] window.

    Within-window: send within ~5 minutes (don't park urgent sends).
    Before window: snap to morning_hour_local today.
    After window: snap to morning_hour_local tomorrow.

    Weekends: bump Saturday/Sunday to Monday morning (B2B reply rates
    crater on weekends; not worth the deliverability hit).
    """
    now = now_utc or datetime.now(timezone.utc)
    offset = offset_hours_for(email=email, company_domain=company_domain)
    local = now + timedelta(hours=offset)
    target = local

    # Snap into window.
    if local.hour < morning_hour_local:
        target = local.replace(hour=morning_hour_local, minute=0, second=0, microsecond=0)
    elif local.hour >= latest_hour_local:
        target = (local + timedelta(days=1)).replace(
            hour=morning_hour_local, minute=0, second=0, microsecond=0,
        )
    # Inside window — leave as-is (send roughly now).

    # Bump weekends to Monday morning.
    while target.weekday() >= 5:  # 5=Sat, 6=Sun
        target = (target + timedelta(days=1)).replace(
            hour=morning_hour_local, minute=0, second=0, microsecond=0,
        )

    return target - timedelta(hours=offset)

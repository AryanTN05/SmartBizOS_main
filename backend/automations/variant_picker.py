"""Pick the next opener variant to use for a send.

Strategy: epsilon-greedy with an explore floor. Until every variant has
at least N=3 sends, pick the under-explored one (round-robin among
zero/lowest-sent). After that, pick the variant with the highest
empirical reply rate. Ties broken in declaration order (the first
variant generated is the default).

The math doesn't need to be Thompson — at the small per-lead sample
sizes this product targets (most leads receive 1-2 variants in their
lifecycle anyway), epsilon-greedy is honest and explainable.

The send_day0 step calls `pick_variant(variants)` to choose, and
`record_send(variants, idx)` after the send commits. Reply tracking
happens in the IMAP poller / manual reply endpoint when they flip
sequence_state — both call `record_reply(variants, active_text)`.
"""
from __future__ import annotations

from typing import Optional


_EXPLORE_FLOOR = 3


def pick_variant(variants: Optional[list[dict]]) -> Optional[int]:
    """Return the index of the variant the scheduler should use, or None
    when the lead has no variants (caller falls back to opening_line)."""
    if not variants:
        return None
    # Explore floor — give every variant a fair shake before optimizing.
    under = [(i, v.get("sent_count") or 0) for i, v in enumerate(variants)]
    min_sent = min(s for _, s in under)
    if min_sent < _EXPLORE_FLOOR:
        # Round-robin among the under-sampled variants. Earliest-defined
        # wins ties so the default variant goes first.
        for i, s in under:
            if s == min_sent:
                return i
    # All variants past the floor — pick the highest reply rate.
    best_idx = 0
    best_rate = -1.0
    for i, v in enumerate(variants):
        sent = (v.get("sent_count") or 0) or 1
        rate = (v.get("replied_count") or 0) / sent
        if rate > best_rate:
            best_rate = rate
            best_idx = i
    return best_idx


def record_send(variants: list[dict], idx: int) -> list[dict]:
    """Increment sent_count for the given variant. Returns the modified
    list; caller must reassign the JSONB column for SQLAlchemy to detect
    the change."""
    out = [dict(v) for v in variants]
    if 0 <= idx < len(out):
        out[idx]["sent_count"] = (out[idx].get("sent_count") or 0) + 1
    return out


def record_reply(variants: Optional[list[dict]], active_text: Optional[str]) -> Optional[list[dict]]:
    """Bump replied_count for the variant matching `active_text`. Returns
    a new list (or None when no variants). Matching by text is fine —
    variants for a given lead are unique by construction (dedupe in the
    generator)."""
    if not variants or not active_text:
        return variants
    out = [dict(v) for v in variants]
    for v in out:
        if v.get("text") == active_text:
            v["replied_count"] = (v.get("replied_count") or 0) + 1
            break
    return out

"""Trigger-signal detector.

Pulls buying-intent signals out of whatever data we already have on a lead:
  - scraper raw_data (PH launch, YC batch, HN post, GitHub trending)
  - enrichment fields (description, tech, funding, news)
  - lead.notes + lead.title

Returns a list of canonical trigger strings the FE can render as badges
and the scoring layer can use as multipliers. Pure heuristic — regex +
field presence — so it's free to run and never blocks a write path.

Trigger taxonomy (matches `triggerMeta` on the FE):
  - hiring             — actively recruiting (job postings, "we're hiring")
  - funding            — recent funding event (any stage)
  - launch             — recently shipped (Product Hunt, "just launched")
  - tech_stack_change  — visible stack shift (mentions "migrated to/from")

Scoring: each trigger adds +5 to the lead's stored score, capped at +15
total so a single hot-lead doesn't pile up to 100. The boost is applied
in the convert + enrich paths.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# Regex patterns are deliberately broad — false-positive triggers are
# self-correcting (the SDR sees the badge, eyeballs the lead, and dismisses
# if wrong). False-negatives cost actual revenue.
_HIRING = re.compile(
    r"\b(hiring|we'?re hiring|job (?:opening|posting)|join (?:our|the) team|"
    r"we are hiring|now hiring|open roles?|careers? page)\b",
    re.IGNORECASE,
)
_FUNDING = re.compile(
    r"\b(raised|funded|funding|series\s+[a-d]|seed round|pre[-\s]?seed|"
    r"closed (?:a|our|the)\s+\$?\d+|announces? funding|backed by|"
    r"led by\s+[a-z])\b",
    re.IGNORECASE,
)
_LAUNCH = re.compile(
    r"\b(just launched|now live|introducing|launch(?:ing|ed) today|"
    r"shipping|just shipped|product hunt|new product)\b",
    re.IGNORECASE,
)
_TECH_SHIFT = re.compile(
    r"\b("
    # migrate / migrating / migrated / migration
    r"migrat(?:e[ds]?|ing|ion)\s+(?:to|from|away)"
    r"|"
    # switch / switching / switched
    r"switch(?:ed|ing)?\s+(?:to|from|away)"
    r"|"
    # move / moving / moved (require a known tech keyword to avoid noise)
    r"mov(?:e[ds]?|ing)\s+(?:to|from)\s+"
    r"(?:rust|go(?:lang)?|kubernetes|k8s|kafka|postgres(?:ql)?|"
    r"mongodb|mysql|aws|gcp|azure|terraform|kubernetes|snowflake|"
    r"redis|elasticsearch|nextjs|react|vue|svelte)"
    r")\b",
    re.IGNORECASE,
)

TRIGGER_VALUES = ("hiring", "funding", "launch", "tech_stack_change")
PER_TRIGGER_BOOST = 5
MAX_BOOST = 15


def _haystack(*sources: Optional[str | dict | list]) -> str:
    """Flatten heterogeneous sources into a single search string. Dicts and
    lists are stringified naively — exact rendering doesn't matter, only
    keyword presence."""
    out: list[str] = []
    for src in sources:
        if not src:
            continue
        if isinstance(src, str):
            out.append(src)
        elif isinstance(src, dict):
            out.append(" ".join(str(v) for v in src.values() if v))
        elif isinstance(src, (list, tuple)):
            out.append(" ".join(str(v) for v in src if v))
    return " ".join(out)


def detect_triggers(
    *,
    notes: Optional[str] = None,
    title: Optional[str] = None,
    company_name: Optional[str] = None,
    scraper_raw: Optional[dict] = None,
    enrichment: Optional[dict] = None,
) -> list[str]:
    """Inspect every text-bearing field for trigger-pattern matches.

    Returns a deduped list in canonical order (hiring, funding, launch,
    tech_stack_change) so the FE renders badges consistently per lead.
    """
    enrich = enrichment or {}
    raw = scraper_raw or {}
    text = _haystack(
        notes, title, company_name,
        enrich.get("description"),
        enrich.get("summary"),
        enrich.get("highlights"),
        enrich.get("news"),
        enrich.get("tech"),
        raw.get("description"),
        raw.get("tagline"),
        raw.get("text"),
        raw.get("title"),
    )

    found: list[str] = []
    if _HIRING.search(text):
        found.append("hiring")
    if _FUNDING.search(text) or (enrich.get("funding") or {}).get("stage"):
        found.append("funding")
    if _LAUNCH.search(text) or raw.get("source") == "product_hunt":
        found.append("launch")
    if _TECH_SHIFT.search(text):
        found.append("tech_stack_change")

    # Canonical order, preserving uniqueness
    return [t for t in TRIGGER_VALUES if t in found]


def score_boost_for(triggers: Iterable[str]) -> int:
    """Sum the per-trigger boost, capped. Caller adds to lead.score."""
    if not triggers:
        return 0
    total = 0
    for t in triggers:
        if t in TRIGGER_VALUES:
            total += PER_TRIGGER_BOOST
    return min(total, MAX_BOOST)

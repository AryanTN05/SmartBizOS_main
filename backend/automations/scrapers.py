"""
Real scraper implementations called from POST /api/scrapers/{id}/run.

Each function returns the count of new ScraperResult rows it inserted, so
the API can update the source's leads_last_run + leads_total counters.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select

from db.connection import SessionLocal
from db.entities import ScraperResult

log = logging.getLogger("smartbiz.scrapers")


PRODUCT_HUNT_RSS  = "https://www.producthunt.com/feed"
HN_SHOW_HN_API    = "https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&hitsPerPage=30"
HN_WHO_HIRING_RSS = "https://hnrss.org/whoishiring/jobs"
TECHCRUNCH_RSS    = "https://techcrunch.com/category/startups/feed/"
# GitHub trending repos, filtered to SaaS-adjacent topics. Public, no auth needed.
# GitHub's search API does NOT support `OR` between `topic:` qualifiers
# (it only ORs free-text terms). The earlier `topic:saas OR topic:b2b ...`
# returned 422. We now run one query per topic and union the results
# client-side in run_github_trending(). Window widened to 60d so the
# topic+stars+pushed combo isn't empty most days.
GITHUB_SEARCH_TOPICS = ("saas", "b2b", "crm")
GITHUB_SEARCH_API = "https://api.github.com/search/repositories?q=topic:{topic}+pushed:>{cutoff}+stars:>5&sort=updated&order=desc&per_page=15"
# Y Combinator's full company directory — community-maintained JSON mirror,
# updated daily from yc-oss. ~5.7k companies; we filter to recent batches.
YC_COMPANIES_API  = "https://yc-oss.github.io/api/companies/all.json"
# Apollo.io — real B2B contact database (the legal LinkedIn alternative).
# Free tier: 100 search credits/month. Search endpoint returns people +
# their org; we shape each into a captured row.
APOLLO_SEARCH_API = "https://api.apollo.io/v1/mixed_people/search"

LINKEDIN_SEED_FIXTURES = [
    {"name": "Aanya Patel", "company": "Notewise", "url": "https://www.linkedin.com/in/aanya-patel"},
    {"name": "Karthik Iyer", "company": "Beacon Sales",
     "url": "https://www.linkedin.com/in/karthik-iyer-bcn"},
    {"name": "Tara Mukherjee", "company": "Stitchpoint",
     "url": "https://www.linkedin.com/in/tara-mukherjee"},
    {"name": "Owen Reilly", "company": "Driftloop",
     "url": "https://www.linkedin.com/in/owen-reilly"},
    {"name": "Mei-Ling Zhao", "company": "Trellisly",
     "url": "https://www.linkedin.com/in/mei-zhao"},
]


# ─── helpers ────────────────────────────────────────────────────────────────

# User-agent rotation. Most public feeds we hit are happy to serve any UA,
# but some (Cloudflare-fronted RSS) reject UA strings that look like bots.
# We rotate among 3 realistic strings to look like a normal client.
_USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36",
    "SmartBizOS/0.1 (+https://github.com/zerotoprod-5/SmartBiz-OS)",
)


async def _fetch_with_retry(url: str, *, source: str,
                             headers: Optional[dict] = None,
                             max_attempts: int = 3,
                             timeout: float = 15.0) -> Optional[str]:
    """Fetch a URL with exponential backoff. Returns text on 2xx,
    None on giving-up. Detects Cloudflare interstitials and rotates UA
    on each retry. Public feed scrapers should call this instead of
    raw httpx.get so transient flakes don't blank an entire scraper run.
    """
    backoffs = (1.0, 3.0, 8.0)
    last_err: Optional[str] = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for i in range(max_attempts):
            try:
                hdrs = {"User-Agent": _USER_AGENTS[i % len(_USER_AGENTS)],
                        "Accept": "*/*"}
                if headers:
                    hdrs.update(headers)
                resp = await client.get(url, headers=hdrs)
                if resp.status_code >= 500:
                    last_err = f"HTTP {resp.status_code}"
                elif resp.status_code in (403, 429):
                    last_err = f"HTTP {resp.status_code} (rate-limited / Cloudflare)"
                else:
                    body = resp.text
                    # Crude Cloudflare/JS-challenge detection.
                    low = body[:2000].lower()
                    if "cf-error" in low or "just a moment" in low or "<title>just a moment" in low:
                        last_err = "Cloudflare challenge interstitial"
                    else:
                        if i > 0:
                            log.info("%s: succeeded on attempt %d", source, i + 1)
                        return body
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:120]}"

            if i < max_attempts - 1:
                await asyncio.sleep(backoffs[i])
    log.warning("%s: gave up after %d attempts (%s)", source, max_attempts, last_err)
    return None


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _HTML_TAG_RE.sub("", s or "").strip()


def _safe_parse_feed(text: str, source_label: str):
    """Wrap ET.fromstring so a malformed/HTML-interstitial response from a
    third-party feed (Cloudflare wall, maintenance page, format change)
    doesn't bubble up as a 500. Returns None on parse error."""
    if not text or not text.strip().startswith(("<?xml", "<rss", "<feed", "<")):
        log.warning("%s: response doesn't look like XML (%d chars)", source_label, len(text or ""))
        return None
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        log.warning("%s: XML parse failed: %s", source_label, e)
        return None


def _domain_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"^https?://([^/]+)/?", url)
    return m.group(1) if m else None


_NORMALIZE_DOMAIN_RE = re.compile(r"^(?:https?://)?(?:www\.)?([^/?#]+)", re.IGNORECASE)


def _normalize_domain(url_or_domain: str) -> Optional[str]:
    """Strip protocol + www, lowercase. Used to match the same company
    across sources. Returns None when no plausible domain."""
    if not url_or_domain:
        return None
    m = _NORMALIZE_DOMAIN_RE.match(url_or_domain.strip())
    if not m:
        return None
    host = m.group(1).lower().split(":")[0]  # drop port
    # Drop sub-paths if the regex already captured them (defense-in-depth).
    host = host.split("/", 1)[0]
    if "." not in host:
        return None
    # Reduce to the registrable domain — drops sub-domains like
    # blog.acme.com → acme.com so cross-source matching works.
    parts = host.split(".")
    if len(parts) > 2:
        # Naive 2-label rule. Doesn't handle ccTLDs like co.uk perfectly
        # (would treat blog.acme.co.uk → co.uk). For our use case this is
        # close enough; cross-source still matches when both URLs use the
        # same full host.
        return ".".join(parts[-2:])
    return host


async def _insert_results(tenant_id: uuid.UUID, source_type: str,
                           rows: list[dict]) -> int:
    """Insert rows that we haven't already captured.

    Dedupes by:
      1. extracted_url (exact match)
      2. normalized root domain (cross-source match) — when a hit on
         the same domain already exists from a DIFFERENT source, we
         don't insert a duplicate row but DO bump the existing row's
         relevance_score and append a `cross_source_signals` array to
         its raw_data so the SDR sees "this lead also appears in YC + GH".

    Each cross-source hit adds +5 to the score, capped at 95.
    """
    if not rows:
        return 0

    # Pre-compute per-row domains.
    for r in rows:
        r["_domain"] = _normalize_domain(r.get("extracted_url") or "")

    inserted = 0
    cross_source_boosted = 0
    async with SessionLocal() as db:
        # Stage 1 — URL-level dedupe within this batch.
        urls = [r["extracted_url"] for r in rows if r.get("extracted_url")]
        existing_urls: set[str] = set()
        if urls:
            existing_rows = (await db.execute(
                select(ScraperResult.extracted_url).where(
                    ScraperResult.tenant_id == tenant_id,
                    ScraperResult.extracted_url.in_(urls),
                )
            )).all()
            existing_urls = {r[0] for r in existing_rows if r[0]}

        # Stage 2 — domain-level lookup for cross-source signals.
        # Pull the existing rows whose domain matches anything in this batch
        # but came from a different source — they're the cross-source merge
        # candidates.
        domains = {r["_domain"] for r in rows if r["_domain"]}
        existing_by_domain: dict[str, list[ScraperResult]] = {}
        if domains:
            # We can't index by normalized domain in SQL without a stored
            # column, so pull a window and filter in Python. At small-team
            # scale this is fine; if a tenant ever exceeds ~20k captures we
            # can add a generated column.
            recent_window = datetime.now(timezone.utc) - timedelta(days=45)
            candidates = (await db.execute(
                select(ScraperResult).where(
                    ScraperResult.tenant_id == tenant_id,
                    ScraperResult.scraped_at >= recent_window,
                )
            )).scalars().all()
            for cand in candidates:
                cd = _normalize_domain(cand.extracted_url or "")
                if cd in domains:
                    existing_by_domain.setdefault(cd, []).append(cand)

        for r in rows:
            url = r.get("extracted_url")
            if url and url in existing_urls:
                continue

            # Cross-source check — if any prior row from a DIFFERENT source
            # exists for the same domain, boost it instead of inserting.
            cross_hit = None
            if r["_domain"] and r["_domain"] in existing_by_domain:
                for cand in existing_by_domain[r["_domain"]]:
                    if cand.source_type != source_type:
                        cross_hit = cand
                        break

            if cross_hit is not None:
                # Merge: append this source's signal to the existing row.
                raw = dict(cross_hit.raw_data or {})
                seen = list(raw.get("cross_source_signals") or [])
                if source_type not in seen:
                    seen.append(source_type)
                    raw["cross_source_signals"] = seen
                    cross_hit.raw_data = raw
                    cross_hit.relevance_score = min(
                        (cross_hit.relevance_score or 0) + 5, 95,
                    )
                    cross_source_boosted += 1
                # Don't insert a fresh row — the cross-source signal IS the
                # value-add. Otherwise the inbox would carry duplicates.
                continue

            new_row = ScraperResult(
                tenant_id=tenant_id,
                source_type=source_type,
                raw_data=r.get("raw") or {},
                extracted_name=r.get("extracted_name"),
                extracted_company=r.get("extracted_company"),
                extracted_url=url,
                extracted_email=r.get("extracted_email"),
                relevance_score=r.get("relevance_score"),
                status="pending",
            )
            db.add(new_row)
            inserted += 1
        await db.commit()

        # Capture the IDs that just got inserted (rows that are now in this
        # session and aren't pre-existing). We pull them out before the
        # session closes so the background enrichment can act on them.
        # _force_load to satisfy the autoflush check first.
        await db.flush()
        new_ids = [
            row.id for row in db.identity_map.values()
            if isinstance(row, ScraperResult) and row.tenant_id == tenant_id
            and row.source_type == source_type
        ]

    if cross_source_boosted:
        log.info("%s: %d insert, %d cross-source boost", source_type, inserted, cross_source_boosted)

    # Fire-and-forget ICP scoring on the just-inserted rows. Without this,
    # every fresh capture sits at the static fallback relevance_score (50/55
    # depending on source) and the Inbox triage tiers are meaningless until
    # someone clicks "Bulk enrich". enrich_batch caps concurrency at 5 and
    # is idempotent on already-scored rows.
    if inserted and new_ids:
        try:
            from automations.lead_enrichment import enrich_batch
            task = asyncio.create_task(enrich_batch(new_ids, None, 5, force=False))
            def _on_done(t: asyncio.Task) -> None:
                if t.cancelled():
                    return
                exc = t.exception()
                if exc is not None:
                    log.warning("auto-enrich after %s scrape failed: %s", source_type, exc)
            task.add_done_callback(_on_done)
        except Exception as e:
            log.warning("auto-enrich scheduling failed for %s: %s", source_type, e)

    return inserted


# ─── source handlers ────────────────────────────────────────────────────────

async def run_product_hunt(tenant_id: uuid.UUID) -> int:
    """Pull the latest Product Hunt launches via their public Atom feed.

    Atom feed shape (as of 2026): each entry has <title>, <link>, <author>,
    <summary>, <published>. Title splits as 'Product — Tagline' so we
    capture the tagline as a separate signal field for the opener
    generator. Also extracts the maker handle from <author> when present.
    """
    text = await _fetch_with_retry(PRODUCT_HUNT_RSS, source="producthunt")
    if not text:
        return 0
    feed = _safe_parse_feed(text, "producthunt")
    if feed is None:
        return 0

    # Product Hunt serves Atom (not RSS) — entries live under {atom}entry.
    NS = {"a": "http://www.w3.org/2005/Atom"}
    entries = feed.findall("a:entry", NS)
    if not entries:
        log.warning("producthunt: feed parsed but 0 entries — possible format change")
    rows: list[dict] = []
    for entry in entries:
        title = (entry.findtext("a:title", default="", namespaces=NS) or "").strip()
        link_el = entry.find("a:link", NS)
        link = (link_el.get("href") if link_el is not None else "") or ""
        summary = _strip_html(entry.findtext("a:summary", default="", namespaces=NS) or "")
        author_el = entry.find("a:author/a:name", NS)
        author_name = (author_el.text or "").strip() if author_el is not None else ""
        published = (entry.findtext("a:published", default="", namespaces=NS) or "").strip()
        if not title or not link:
            continue

        # Pull product name + tagline. PH's canonical separator is em-dash.
        if " — " in title:
            company, tagline = title.split(" — ", 1)
        else:
            company, tagline = title, ""
        company = company.strip()[:120]
        tagline = tagline.strip()[:240]

        rows.append({
            "extracted_company": company,
            "extracted_name": author_name or None,
            "extracted_url": link,
            "raw": {
                "title": title, "link": link, "summary": summary[:500],
                "tagline": tagline, "maker": author_name or None,
                "published": published, "signal": "ph_launch",
            },
            # Recent launches are a stronger signal than older ones — but we
            # don't currently parse the date for scoring weight; LLM handles
            # recency from the published field in the raw payload.
            "relevance_score": 55,
        })
    return await _insert_results(tenant_id, "producthunt", rows[:25])


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_COMPANY_FROM_TITLE_RE = re.compile(r"^Show HN:\s*([^—\-–—\|,]+?)(?:\s*[—\-–—\|,].*)?$", re.I)


async def run_hn_show_hn(tenant_id: uuid.UUID) -> int:
    """Hacker News 'Show HN' posts via Algolia (free, no auth)."""
    text = await _fetch_with_retry(HN_SHOW_HN_API, source="hn_show_hn")
    if not text:
        return 0
    import json
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("hn_show_hn: response is not JSON")
        return 0

    rows: list[dict] = []
    for hit in (data.get("hits") or [])[:30]:
        title = (hit.get("title") or "").strip()
        url = (hit.get("url") or "").strip()
        author = (hit.get("author") or "").strip()
        story_id = hit.get("objectID")
        if not title:
            continue
        # Prefer the external URL — that's the actual product. Fall back to
        # the HN thread (still a valid signal since the post may include
        # contact info in the body).
        target_url = url or (f"https://news.ycombinator.com/item?id={story_id}" if story_id else None)
        if not target_url:
            continue
        m = _COMPANY_FROM_TITLE_RE.match(title)
        company = (m.group(1).strip() if m else title)[:120]
        rows.append({
            "extracted_company": company,
            "extracted_name": author,  # HN handle — replace later via enrichment
            "extracted_url": target_url,
            "raw": {
                "title": title, "author": author, "story_id": story_id,
                "summary": (hit.get("story_text") or "")[:500],
            },
            "relevance_score": 50,
        })
    return await _insert_results(tenant_id, "hn_show_hn", rows)


async def run_hn_who_hiring(tenant_id: uuid.UUID) -> int:
    """HN 'Who is hiring' posts. Strong intent signal — companies actively
    spending on hiring are also spending on tooling. We pull the latest
    monthly thread's job comments via hnrss."""
    text = await _fetch_with_retry(HN_WHO_HIRING_RSS, source="hn_hiring")
    if not text:
        return 0
    feed = _safe_parse_feed(text, "hn_hiring")
    if feed is None:
        return 0

    rows: list[dict] = []
    for item in feed.findall(".//item"):
        title = _strip_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        desc_html = item.findtext("description") or ""
        desc = _strip_html(desc_html)
        if not title or not link:
            continue
        # Title shape varies wildly; common: "Company Name (location) — role"
        company = re.split(r"\s[\|–—\-]\s|\(", title)[0].strip()[:120]
        emails = list(set(_EMAIL_RE.findall(desc_html)))[:3]
        rows.append({
            "extracted_company": company,
            "extracted_email": emails[0] if emails else None,
            "extracted_url": link,
            "raw": {
                "title": title, "summary": desc[:500],
                "found_emails": emails,
                "signal": "hiring_intent",
            },
            "relevance_score": 60,  # hiring intent > generic launch
        })
    return await _insert_results(tenant_id, "hn_hiring", rows[:25])


# Funding amount + round patterns. Order matters — prefer the more specific
# "Series X" before falling back to "$N million".
_FUNDING_AMOUNT_RE = re.compile(
    r"\$\s?(\d+(?:[.,]\d+)?)\s*(million|m\b|billion|b\b|k\b)",
    re.IGNORECASE,
)
_FUNDING_ROUND_RE = re.compile(
    r"\b(pre[\s\-]?seed|seed|series\s+([a-f]))\b",
    re.IGNORECASE,
)
# Skip TC posts that clearly aren't funding announcements: long-form opinion,
# event coverage, conference roundups. Captures the most common false-positive
# patterns surfaced in the captured-set audit.
_TC_NONFUNDING_PREFIXES = re.compile(
    r"^(opinion|video|live|tc disrupt|techcrunch live|crunchroll|here's)\b",
    re.IGNORECASE,
)


def _parse_funding(text: str) -> dict:
    """Pull amount + round from a TC headline/summary. Returns
    {amount?: '$12M', round?: 'series-a', detected: bool}."""
    out = {"detected": False}
    m_amount = _FUNDING_AMOUNT_RE.search(text)
    if m_amount:
        out["amount_raw"] = m_amount.group(0).strip()
        out["detected"] = True
    m_round = _FUNDING_ROUND_RE.search(text)
    if m_round:
        full = m_round.group(0).lower().strip()
        if "pre" in full:
            out["round"] = "pre-seed"
        elif full.startswith("seed"):
            out["round"] = "seed"
        elif full.startswith("series"):
            out["round"] = f"series-{m_round.group(2)}".lower()
        out["detected"] = True
    return out


async def run_techcrunch_funding(tenant_id: uuid.UUID) -> int:
    """TechCrunch's startup feed — funding announcements are tier-1 buying
    intent. Now extracts amount + round from the headline/summary so the
    captured row carries structured signal for the LLM scorer + opener."""
    text = await _fetch_with_retry(TECHCRUNCH_RSS, source="techcrunch")
    if not text:
        return 0
    feed = _safe_parse_feed(text, "techcrunch")
    if feed is None:
        return 0

    rows: list[dict] = []
    for item in feed.findall(".//item"):
        title = _strip_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        desc_html = item.findtext("description") or ""
        desc = _strip_html(desc_html)
        if not title or not link:
            continue
        if _TC_NONFUNDING_PREFIXES.search(title):
            continue

        funding = _parse_funding(title + " " + desc)
        is_funding = funding.get("detected", False)

        # Better company extraction: TC headlines mostly look like
        # "Acme raises $12M Series A from VCs" or "Acme launches…".
        company = title
        if " raises " in title.lower():
            company = re.split(r"\sraises\s", title, flags=re.IGNORECASE)[0]
        elif " announces " in title.lower():
            company = re.split(r"\sannounces\s", title, flags=re.IGNORECASE)[0]
        elif " launches " in title.lower():
            company = re.split(r"\slaunches\s", title, flags=re.IGNORECASE)[0]
        company = company.strip().strip(",.").strip()[:120]

        rows.append({
            "extracted_company": company,
            "extracted_url": link,
            "raw": {
                "title": title, "summary": desc[:500],
                "signal": "funding" if is_funding else "tc_general",
                "funding": funding if is_funding else None,
            },
            # Round + amount detected → 75; only round → 70; only amount → 65;
            # nothing → 40 (general TC noise).
            "relevance_score": (
                75 if (funding.get("round") and funding.get("amount_raw"))
                else 70 if funding.get("round")
                else 65 if funding.get("amount_raw")
                else 40
            ),
        })
    return await _insert_results(tenant_id, "techcrunch", rows[:20])


# GitHub repo languages we care about — open-source SaaS companies tend
# to be in these. Filtering by language at scoring time (not search time)
# lets us still capture rare-language signals while elevating the typical
# stack matches.
_HIGH_SIGNAL_LANGS = {"TypeScript", "Python", "Go", "Rust", "Ruby", "Kotlin", "Swift", "Elixir"}
# Repos under these names are usually company-org repos, not personal projects.
_ORG_KEYWORDS = ("inc", "labs", "tech", "ai", "io", "hq")


async def run_github_trending(tenant_id: uuid.UUID) -> int:
    """GitHub recently-pushed repos tagged saas / b2b / crm — founders
    actively building in our space, often with a website + contact in the
    repo's homepage URL.

    Scoring is now signal-aware:
      - +5 if owner login looks like a company org (contains inc/ai/labs)
      - +5 if language is in the high-signal stack list
      - +stars/50 (capped) for traction
      - +5 if `homepage` is a real domain (not github.io)
    """
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GITHUB_ACCESS_TOKEN"):
        headers["Authorization"] = f"Bearer {os.getenv('GITHUB_ACCESS_TOKEN')}"

    # One query per topic; union by repo id so the same repo doesn't get
    # double-counted if it carries multiple of our topic tags.
    import json
    by_id: dict[int, dict] = {}
    for topic in GITHUB_SEARCH_TOPICS:
        text = await _fetch_with_retry(
            GITHUB_SEARCH_API.format(topic=topic, cutoff=cutoff),
            source="github_trending", headers=headers,
        )
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        for repo in (data.get("items") or [])[:15]:
            rid = repo.get("id")
            if rid is not None and rid not in by_id:
                by_id[rid] = repo
    items = list(by_id.values())[:30]

    rows: list[dict] = []
    for repo in items:
        homepage = (repo.get("homepage") or "").strip()
        repo_url = repo.get("html_url") or ""
        target = homepage if homepage.startswith("http") else repo_url
        if not target:
            continue
        owner = (repo.get("owner") or {}).get("login") or ""
        owner_type = (repo.get("owner") or {}).get("type") or ""
        stars = repo.get("stargazers_count") or 0
        language = repo.get("language")

        # Score-shaping
        score = 50
        score += min(stars // 50, 25)
        if language in _HIGH_SIGNAL_LANGS:
            score += 5
        # Owner org signal — repos under e.g. "acme-inc" or "acmehq" are far
        # more likely to be company repos than personal hobby projects.
        if owner_type == "Organization" or any(k in owner.lower() for k in _ORG_KEYWORDS):
            score += 5
        # Real domain in homepage = the repo is the public face of a real
        # product, not just a code dump.
        if homepage.startswith("http") and "github.io" not in homepage:
            score += 5
        score = min(score, 90)

        rows.append({
            "extracted_company": (repo.get("name") or "").replace("-", " ").title()[:120],
            "extracted_name": owner,
            "extracted_url": target,
            "raw": {
                "title": repo.get("full_name"),
                "summary": (repo.get("description") or "")[:500],
                "stars": stars,
                "language": language,
                "topics": (repo.get("topics") or [])[:8],
                "repo_url": repo_url,
                "homepage": homepage or None,
                "owner_type": owner_type,
                "pushed_at": repo.get("pushed_at"),
                "signal": "active_open_source",
            },
            "relevance_score": score,
        })
    return await _insert_results(tenant_id, "github_trending", rows)


# YC batch values are full season+year strings like "Winter 2026" / "Summer
# 2025" / "Fall 2024" / "Spring 2025". We default to the last ~2 years so
# the captured set is currently-fundable rather than 2015 graduates that
# long since exited or pivoted.
_RECENT_YC_YEARS = {"2024", "2025", "2026"}


def _is_recent_yc_batch(batch: str) -> bool:
    if not batch:
        return False
    # Last token is the year — covers "Winter 2026", "Summer 2025", "Fall 2024", etc.
    parts = batch.strip().split()
    return bool(parts) and parts[-1] in _RECENT_YC_YEARS


async def run_yc_directory(tenant_id: uuid.UUID) -> int:
    """Pull recent-batch Y Combinator companies from the yc-oss public mirror.

    Now extracts founder names + Twitter/LinkedIn handles when YC's payload
    carries them. The opener generator stacks "YC <batch> + <founder name>"
    + recent product mention into a much higher-signal first line.
    """
    text = await _fetch_with_retry(YC_COMPANIES_API, source="yc", timeout=30)
    if not text:
        return 0
    import json
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("yc directory: response is not JSON")
        return 0

    if not isinstance(data, list):
        log.warning("yc directory: unexpected response shape (%s)", type(data).__name__)
        return 0

    rows: list[dict] = []
    for c in data:
        batch = (c.get("batch") or "").strip()
        if not _is_recent_yc_batch(batch):
            continue
        website = (c.get("website") or "").strip()
        if not website or not website.startswith("http"):
            continue
        # Skip dead companies — YC marks them inactive.
        if c.get("status") == "Inactive":
            continue
        name = (c.get("name") or "")[:120]

        # Founder extraction — yc-oss exposes founders on most active rows.
        # Each entry has {full_name, title, twitter_url, linkedin_url}.
        founders = []
        for f in (c.get("founders") or [])[:4]:
            if not isinstance(f, dict):
                continue
            full_name = (f.get("full_name") or "").strip()
            if not full_name:
                continue
            founders.append({
                "name": full_name,
                "title": (f.get("title") or "").strip() or None,
                "twitter": (f.get("twitter_url") or "").strip() or None,
                "linkedin": (f.get("linkedin_url_safe")
                              or f.get("linkedin_url") or "").strip() or None,
            })
        primary_founder = founders[0]["name"] if founders else None

        # Score-shaping. Base 65; bump for current-year batch, hot industry,
        # multiple-founder ops, presence of a public LinkedIn for direct
        # outreach.
        score = 65
        if batch and batch.split()[-1] == str(datetime.now(timezone.utc).year):
            score += 5  # current year batch
        if (c.get("industry") or "").lower() in {
            "b2b software", "saas", "developer tools", "fintech",
            "sales and marketing", "productivity",
        }:
            score += 5
        if any(f.get("linkedin") for f in founders):
            score += 5
        score = min(score, 88)

        rows.append({
            "extracted_company": name,
            "extracted_name": primary_founder,
            "extracted_url": website,
            "raw": {
                "title": f"YC {batch}: {name}" if batch else f"YC: {name}",
                "summary": (c.get("long_description") or c.get("one_liner") or "")[:500],
                "tagline": (c.get("one_liner") or "").strip()[:240] or None,
                "batch": batch,
                "industry": c.get("industry"),
                "subindustry": c.get("subindustry"),
                "team_size": c.get("team_size"),
                "tags": (c.get("tags") or [])[:6],
                "location": c.get("all_locations"),
                "yc_url": c.get("url"),
                "status": c.get("status"),
                "founders": founders,
                "is_hiring": bool(c.get("isHiring") or c.get("is_hiring")),
                "signal": "yc_recent_batch",
            },
            "relevance_score": score,
        })
    return await _insert_results(tenant_id, "directories", rows[:60])


# ─────────────────────────────────────────────────────────────────────────
# Job-board scrapers (Greenhouse / Lever / Ashby).
#
# All three publish public unauthenticated JSON. Hiring velocity + open
# role mix = direct buying-intent signal: a company opening 4+ sales/eng
# roles in 30 days is in active growth mode and probably evaluating
# tooling. Seed company tokens via env (JOB_BOARD_TOKENS=greenhouse:stripe,
# greenhouse:notion,lever:figma,...).
#
# Per the May-2026 trend scan: this is the highest signal:reliability ratio
# of any source we don't already have.
# ─────────────────────────────────────────────────────────────────────────

GREENHOUSE_BOARD_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
LEVER_BOARD_API      = "https://api.lever.co/v0/postings/{token}?mode=json"
ASHBY_BOARD_API      = "https://api.ashbyhq.com/posting-api/job-board/{token}"

# Departments / titles that signal active sales-tech buying. We elevate
# captures whose role mix skews to these — they're the companies most
# likely to need a CRM/RevOps/lead tool.
_SALES_INTENT_PATTERNS = re.compile(
    r"\b(sales|revops|revenue operations|growth|marketing|"
    r"business development|bizdev|account executive|sdr|bdr|"
    r"customer success|cs lead)\b",
    re.IGNORECASE,
)
_ENG_INTENT_PATTERNS = re.compile(
    r"\b(engineer|developer|software|infra|platform|swe)\b",
    re.IGNORECASE,
)


def _job_board_seeds() -> list[tuple[str, str]]:
    """Return [(provider, company_token), ...] from JOB_BOARD_TOKENS env.
    Format: 'greenhouse:stripe,lever:figma,ashby:posthog'. Defaults to a
    short demo list so the scraper does something out of the box."""
    raw = os.getenv("JOB_BOARD_TOKENS", "").strip()
    if raw:
        out = []
        for chunk in raw.split(","):
            if ":" not in chunk:
                continue
            prov, token = chunk.split(":", 1)
            prov = prov.strip().lower()
            token = token.strip().lower()
            if prov in ("greenhouse", "lever", "ashby") and token:
                out.append((prov, token))
        return out[:60]
    # Sensible defaults — well-known company-token examples that should
    # always exist. The user is expected to override with JOB_BOARD_TOKENS.
    return [
        ("greenhouse", "stripe"),
        ("greenhouse", "notion"),
        ("greenhouse", "figma"),
        ("greenhouse", "vercel"),
        ("lever", "figma"),
        ("lever", "scribd"),
        ("ashby", "posthog"),
        ("ashby", "mintlify"),
    ]


async def _fetch_greenhouse(client: httpx.AsyncClient, token: str) -> list[dict]:
    """Pull active jobs for a Greenhouse-hosted board. Returns a list of
    {title, location, department, url, updated_at}."""
    url = GREENHOUSE_BOARD_API.format(token=token)
    try:
        resp = await client.get(url, headers={"User-Agent": _USER_AGENTS[0]})
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    jobs = []
    for j in (data.get("jobs") or []):
        jobs.append({
            "title": (j.get("title") or "").strip(),
            "location": (j.get("location") or {}).get("name", ""),
            "department": ", ".join(d.get("name", "") for d in (j.get("departments") or [])),
            "url": j.get("absolute_url") or "",
            "updated_at": j.get("updated_at"),
        })
    return jobs


async def _fetch_lever(client: httpx.AsyncClient, token: str) -> list[dict]:
    url = LEVER_BOARD_API.format(token=token)
    try:
        resp = await client.get(url, headers={"User-Agent": _USER_AGENTS[0]})
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    jobs = []
    if not isinstance(data, list):
        return []
    for j in data:
        jobs.append({
            "title": (j.get("text") or "").strip(),
            "location": (j.get("categories") or {}).get("location", ""),
            "department": (j.get("categories") or {}).get("team", ""),
            "url": j.get("hostedUrl") or "",
            "updated_at": j.get("createdAt"),
        })
    return jobs


async def _fetch_ashby(client: httpx.AsyncClient, token: str) -> list[dict]:
    url = ASHBY_BOARD_API.format(token=token)
    try:
        resp = await client.get(url, headers={"User-Agent": _USER_AGENTS[0]})
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    jobs = []
    for j in (data.get("jobs") or []):
        jobs.append({
            "title": (j.get("title") or "").strip(),
            "location": j.get("locationName", ""),
            "department": j.get("departmentName", ""),
            "url": j.get("jobUrl") or "",
            "updated_at": j.get("publishedDate"),
        })
    return jobs


async def run_job_boards(tenant_id: uuid.UUID) -> int:
    """Scan every seeded company's job board, score by hiring velocity +
    sales/eng role mix. Each company → one capture row whose raw payload
    carries the open-role list so the opener generator can mention
    specific roles ('saw you're hiring 4 AEs')."""
    seeds = _job_board_seeds()
    if not seeds:
        log.info("job_boards: no seeds configured (set JOB_BOARD_TOKENS env)")
        return 0

    rows: list[dict] = []
    fetchers = {
        "greenhouse": _fetch_greenhouse,
        "lever": _fetch_lever,
        "ashby": _fetch_ashby,
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        # Parallel fetch with a semaphore so we don't fire 60 concurrent
        # requests at any one provider. 6 in flight is gentle.
        sem = asyncio.Semaphore(6)
        async def _one(provider: str, token: str):
            async with sem:
                return provider, token, await fetchers[provider](client, token)

        results = await asyncio.gather(
            *[_one(p, t) for p, t in seeds],
            return_exceptions=False,
        )

    for provider, token, jobs in results:
        if not jobs:
            continue
        # Filter to "recent" — opened or updated in the last 60 days.
        # When the job has no updated_at we keep it; the LLM scorer will
        # downweight if needed.
        recent_jobs = jobs[:30]  # cap per company
        if not recent_jobs:
            continue

        sales_count = sum(1 for j in recent_jobs if _SALES_INTENT_PATTERNS.search(j["title"] + " " + j["department"]))
        eng_count = sum(1 for j in recent_jobs if _ENG_INTENT_PATTERNS.search(j["title"] + " " + j["department"]))
        total = len(recent_jobs)

        # Score: base 60 (we're scraping public boards, so the quality
        # bar is "the company exists"). Boost for sales-intent role density.
        score = 60
        if sales_count >= 3:
            score += 15
        elif sales_count >= 1:
            score += 8
        if total >= 10:
            score += 5  # high overall hiring velocity
        if eng_count >= 5:
            score += 3  # eng-heavy growth
        score = min(score, 90)

        # Extract company display + a representative URL (career page).
        first = recent_jobs[0]
        sample_url = first.get("url") or ""
        company_name = token.replace("-", " ").title()
        rows.append({
            "extracted_company": company_name[:120],
            "extracted_url": sample_url or f"https://{token}.com",
            "raw": {
                "title": f"{company_name} — {total} open role(s)",
                "summary": f"{sales_count} sales/marketing, {eng_count} engineering, "
                           f"{total - sales_count - eng_count} other.",
                "provider": provider,
                "token": token,
                "open_role_count": total,
                "sales_role_count": sales_count,
                "eng_role_count": eng_count,
                "sample_titles": [j["title"] for j in recent_jobs[:5]],
                "sample_url": sample_url,
                "signal": "active_hiring",
            },
            "relevance_score": score,
        })

    return await _insert_results(tenant_id, "job_boards", rows)


# ─────────────────────────────────────────────────────────────────────────
# SEC EDGAR S-1 feed — pre-IPO companies, free no-auth, government API.
# Highest-budget buying segment (legal / HR / infra / sales tooling spend
# spikes 30-45 days post-S-1 filing). No other source captures this layer.
# ─────────────────────────────────────────────────────────────────────────

EDGAR_S1_API = (
    "https://efts.sec.gov/LATEST/search-index?"
    "forms=S-1&dateRange=custom&startdt={start}&enddt={end}"
)


async def run_edgar_s1(tenant_id: uuid.UUID) -> int:
    """Pull recent S-1 filings (last 60 days) from the EDGAR full-text
    search API. Each filing → one capture with the issuer's name + filing
    date + EDGAR detail URL.

    SEC's general guidance is 10 req/sec, no auth needed. We hit the API
    once per run.
    """
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
    url = EDGAR_S1_API.format(start=start, end=end)
    text = await _fetch_with_retry(
        url, source="edgar_s1",
        headers={"User-Agent": "SmartBizOS contact@example.com",
                 "Accept": "application/json"},
    )
    if not text:
        return 0
    import json
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("edgar_s1: response is not JSON")
        return 0

    hits = (data.get("hits") or {}).get("hits") or []
    rows: list[dict] = []
    for h in hits[:25]:
        src = h.get("_source") or {}
        # display_names is a list of company name(s); first is the issuer.
        names = src.get("display_names") or []
        company = (names[0] if names else "").strip()
        if not company:
            continue
        # Strip the trailing CIK suffix EDGAR appends: "Acme Inc (CIK 0001234567)"
        company_clean = re.sub(r"\s*\(CIK\s*\d+\)\s*$", "", company).strip()[:160]

        adsh = (src.get("adsh") or "").replace("-", "")
        cik = (h.get("_id") or "").split(":")[0]
        # Construct a permalink the user can click straight to the filing.
        if adsh and cik:
            edgar_url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar?"
                f"action=getcompany&CIK={cik}&type=S-1&dateb=&owner=include&count=10"
            )
        else:
            edgar_url = "https://www.sec.gov/edgar/searchedgar/companysearch.html"

        filed_at = src.get("file_date") or src.get("@timestamp")
        rows.append({
            "extracted_company": company_clean,
            "extracted_url": edgar_url,
            "raw": {
                "title": f"S-1 filing · {company_clean}",
                "summary": f"Filed {filed_at}. Pre-IPO — active legal / HR / "
                           f"infra spend window opens for the next 30-45 days.",
                "form": "S-1",
                "filed_at": filed_at,
                "cik": cik,
                "adsh": src.get("adsh"),
                "signal": "pre_ipo_filing",
            },
            # Pre-IPO is among the highest-budget signals; start at 80.
            "relevance_score": 80,
        })

    return await _insert_results(tenant_id, "edgar_s1", rows)


# ─────────────────────────────────────────────────────────────────────────
# Reddit intent monitor — explicit buying-intent posts in r/SaaS / r/devops
# / r/sysadmin / r/startups. Different signal class than launches: people
# saying "looking for a tool to do X" or "we're evaluating Y vs Z."
# ─────────────────────────────────────────────────────────────────────────

REDDIT_SUBS = ["SaaS", "devops", "sysadmin", "startups"]
REDDIT_INTENT_KEYWORDS = (
    "looking for",
    "any recommendations",
    "anyone using",
    "we're evaluating",
    "switched from",
    "alternatives to",
    "best tool for",
    "recommendations for",
)


def _reddit_intent_score(title: str, body: str) -> int:
    """Score 0..100 based on explicit-intent phrase match + context."""
    text = f"{title} {body}".lower()
    matches = sum(1 for kw in REDDIT_INTENT_KEYWORDS if kw in text)
    if matches == 0:
        return 0
    score = 55 + min(matches * 8, 24)
    # Pain-language bumps — people describing pain are pre-buying-stage.
    if any(p in text for p in ("frustrated", "fed up", "tired of", "broken")):
        score += 5
    return min(score, 90)


async def run_reddit_intent(tenant_id: uuid.UUID) -> int:
    """Scan a few subreddits' new posts, surface any with an explicit
    buying-intent keyword in title or body. Each match → one capture row."""
    rows: list[dict] = []
    base_headers = {
        "User-Agent": "SmartBizOS/0.1 (contact: smartbiz-os@github)",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for sub in REDDIT_SUBS:
            url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
            try:
                resp = await client.get(url, headers=base_headers)
                if resp.status_code != 200:
                    log.info("reddit %s: HTTP %s", sub, resp.status_code)
                    continue
                data = resp.json()
            except Exception as e:
                log.info("reddit %s: %s", sub, str(e)[:120])
                continue

            for child in (data.get("data") or {}).get("children", []):
                post = child.get("data") or {}
                title = (post.get("title") or "").strip()
                body = (post.get("selftext") or "").strip()
                if not title:
                    continue
                score = _reddit_intent_score(title, body)
                if score < 55:
                    continue

                permalink = post.get("permalink") or ""
                full_url = f"https://www.reddit.com{permalink}" if permalink else ""
                if not full_url:
                    continue

                rows.append({
                    "extracted_name": (post.get("author") or "").strip()[:80] or None,
                    # Reddit posts don't carry a company — leave empty so the
                    # triage UI doesn't show fake company names. The poster's
                    # username + the post URL are what the user clicks.
                    "extracted_company": None,
                    "extracted_url": full_url,
                    "raw": {
                        "title": title,
                        "summary": body[:500],
                        "subreddit": sub,
                        "author": post.get("author"),
                        "score_reddit": post.get("score"),
                        "num_comments": post.get("num_comments"),
                        "created_utc": post.get("created_utc"),
                        "signal": "reddit_intent",
                    },
                    "relevance_score": score,
                })

    return await _insert_results(tenant_id, "reddit_intent", rows[:25])


async def run_apollo_search(tenant_id: uuid.UUID) -> int:
    """Apollo.io — real B2B contact database. The legal alternative to live
    LinkedIn scraping. Searches their 230M+ contact db filtered to our ICP
    (titles + headcount range) and inserts each person as a captured row.

    Requires APOLLO_API_KEY (free tier: 100 searches/mo). When the key is
    missing we log a one-line note + return 0 so the source still appears
    in the UI but does nothing harmful.
    """
    api_key = os.getenv("APOLLO_API_KEY")
    if not api_key:
        log.info("apollo: APOLLO_API_KEY not set — skipping (visit apollo.io to grab a free key)")
        return 0

    # ICP filter — defaults pull VPs/Heads of Sales/RevOps at mid-market
    # SaaS. Workspace-level apollo_icp overrides any/all of titles /
    # seniorities / headcount_ranges so each tenant can target their
    # actual ICP without code changes.
    DEFAULT_TITLES = [
        "VP of Sales", "Head of Sales", "Sales Director",
        "VP of RevOps", "Head of RevOps", "Director of Revenue Operations",
        "Head of Growth", "VP of Marketing", "Head of Marketing",
        "Founder", "Co-Founder", "CEO",
    ]
    DEFAULT_SENIORITIES = ["c_suite", "vp", "head", "director"]
    DEFAULT_HEADCOUNT = ["11,50", "51,200", "201,500"]

    titles = list(DEFAULT_TITLES)
    seniorities = list(DEFAULT_SENIORITIES)
    headcounts = list(DEFAULT_HEADCOUNT)
    try:
        from db.entities import WorkspaceSettings
        async with SessionLocal() as ws_db:
            ws = (await ws_db.execute(
                select(WorkspaceSettings).where(WorkspaceSettings.tenant_id == tenant_id)
            )).scalar_one_or_none()
            override = (ws.apollo_icp if ws else None) or {}
            if isinstance(override.get("titles"), list) and override["titles"]:
                titles = [str(t)[:80] for t in override["titles"][:25]]
            if isinstance(override.get("seniorities"), list) and override["seniorities"]:
                seniorities = [str(s)[:40] for s in override["seniorities"][:10]]
            if isinstance(override.get("headcount_ranges"), list) and override["headcount_ranges"]:
                headcounts = [str(h)[:20] for h in override["headcount_ranges"][:6]]
    except Exception:
        # Soft-fail to defaults — never block the scraper on settings read.
        pass

    body = {
        "person_titles": titles,
        "person_seniorities": seniorities,
        "organization_num_employees_ranges": headcounts,
        "page": 1,
        "per_page": 25,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                APOLLO_SEARCH_API,
                json=body,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        # Apollo returns 422 for credit exhaustion — treat as soft failure.
        if e.response.status_code in (402, 422, 429):
            log.warning("apollo: rate-limited or out of credits (%s)", e.response.status_code)
            return 0
        raise

    rows: list[dict] = []
    for p in (data.get("people") or [])[:25]:
        first = (p.get("first_name") or "").strip()
        last = (p.get("last_name") or "").strip()
        full_name = (p.get("name") or f"{first} {last}").strip() or None
        org = p.get("organization") or {}
        company = (org.get("name") or "")[:120]
        domain = org.get("primary_domain") or org.get("website_url")
        # Apollo gives email_status: "verified", "unverified", "guessed", null.
        # We only auto-fill email when verified — the LLM still gets the
        # email_status as a signal even when we don't surface the address.
        email = None
        if p.get("email") and p.get("email_status") in ("verified", "available"):
            email = p["email"]
        rows.append({
            "extracted_name": full_name,
            "extracted_company": company,
            "extracted_email": email,
            "extracted_url": p.get("linkedin_url") or org.get("website_url") or "",
            "raw": {
                "title": p.get("title"),
                "summary": (org.get("short_description") or "")[:500],
                "seniority": p.get("seniority"),
                "departments": p.get("departments"),
                "location": ", ".join(filter(None, [p.get("city"), p.get("state"), p.get("country")])),
                "org": {
                    "name": company,
                    "domain": domain,
                    "industry": org.get("industry"),
                    "estimated_num_employees": org.get("estimated_num_employees"),
                    "raised": org.get("total_funding"),
                    "founded_year": org.get("founded_year"),
                    "linkedin_url": org.get("linkedin_url"),
                },
                "email_status": p.get("email_status"),
                "signal": "apollo_icp_match",
            },
            # Apollo matched our ICP filter, so they're already pre-qualified.
            # Start at 75; LLM refines based on org details.
            "relevance_score": 75,
        })
    return await _insert_results(tenant_id, "apollo", rows)


async def run_linkedin_seed(tenant_id: uuid.UUID) -> int:
    """Hard-disabled per legal — pulls from a seeded fixture instead.
    Useful for the demo so the button does *something* meaningful."""
    rows = []
    for fx in LINKEDIN_SEED_FIXTURES:
        rows.append({
            "extracted_name": fx["name"],
            "extracted_company": fx["company"],
            "extracted_url": fx["url"],
            "raw": {"source": "seed_fixture", **fx},
            "relevance_score": 60,
        })
    return await _insert_results(tenant_id, "linkedin_seed", rows)


# Source key → handler. Sources not in this map fall back to a stub run that
# just touches last_run_at (existing behaviour).
SCRAPER_HANDLERS = {
    "producthunt":     run_product_hunt,
    "linkedin_seed":   run_linkedin_seed,
    "hn_show_hn":      run_hn_show_hn,
    "hn_hiring":       run_hn_who_hiring,
    "techcrunch":      run_techcrunch_funding,
    "github_trending": run_github_trending,
    "directories":     run_yc_directory,
    "apollo":          run_apollo_search,
    # New sources from the May-2026 trend scan — top 3 signal:reliability
    # picks. All httpx-only, no headless / proxy needed.
    "job_boards":      run_job_boards,
    "edgar_s1":        run_edgar_s1,
    "reddit_intent":   run_reddit_intent,
}


async def execute_scraper(source_key: str, tenant_id: uuid.UUID) -> dict:
    """Run a scraper by key. Returns {ran: bool, inserted: int, error?: str}."""
    handler = SCRAPER_HANDLERS.get(source_key)
    if not handler:
        return {"ran": False, "inserted": 0, "error": "no handler for source"}
    try:
        inserted = await handler(tenant_id)
        return {"ran": True, "inserted": inserted}
    except Exception as e:
        log.exception("scraper %s failed", source_key)
        return {"ran": False, "inserted": 0, "error": str(e)[:200]}

"""
Hybrid page fetcher: cheap-first waterfall.

  1. httpx + BeautifulSoup        — works for static / SSR pages (~70% of B2B sites). Free.
  2. Firecrawl                    — for JS-heavy or bot-walled pages. ~$0.01/page on paid tier.

We try (1) first; only escalate to (2) when (1) returns content too thin to be
useful (no <main>, no <body> text, or < MIN_USEFUL_CHARS of extracted prose).
This keeps Firecrawl credits for pages that actually need a headless browser.

Output: a normalised dict with markdown-ish text + metadata, regardless of
which fetcher won.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("smartbiz.page_fetcher")


MIN_USEFUL_CHARS = 400  # below this we consider httpx output "thin" and try Firecrawl
HTTP_TIMEOUT = 12

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 SmartBizOS/0.1"
)

# Some sites only return real HTML to crawler-shaped UAs (Twitter, ProductHunt,
# many SPAs). We retry with this UA when the first httpx attempt looks thin.
GOOGLEBOT_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

_SCRIPT_RE = re.compile(r"\s+")


def _clean_text(s: str) -> str:
    return _SCRIPT_RE.sub(" ", s).strip()


def _soup_to_text(html: str) -> tuple[str, dict]:
    """Extract main-content text + key meta from raw HTML.
    Returns (text, meta) where meta has og:* + jsonld:type + title + description."""
    soup = BeautifulSoup(html, "lxml")
    # Drop noise.
    for tag in soup(["script", "style", "nav", "footer", "noscript", "iframe", "svg"]):
        tag.decompose()

    meta: dict = {}
    title = soup.find("title")
    if title and title.string:
        meta["title"] = title.string.strip()[:200]
    for prop in ("description", "og:description", "og:title", "og:site_name", "twitter:description"):
        tag = soup.find("meta", attrs={"name": prop}) or soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            meta[prop] = tag["content"].strip()[:300]

    # Prefer <main> / <article>; fall back to body.
    container = soup.find("main") or soup.find("article") or soup.body or soup
    text_parts: list[str] = []
    # h1/h2 first (so they always lead the description even if hidden by CSS).
    for h in container.find_all(["h1", "h2"], limit=4):
        t = _clean_text(h.get_text(" "))
        if t:
            text_parts.append(t)
    for p in container.find_all(["p", "li"], limit=80):
        t = _clean_text(p.get_text(" "))
        if t and len(t) > 30:
            text_parts.append(t)
    text = "\n\n".join(text_parts)[:8000]
    return text, meta


async def _fetch_httpx_once(url: str, user_agent: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
        if resp.status_code >= 400:
            return None
        ct = (resp.headers.get("content-type") or "").lower()
        if "html" not in ct and "xml" not in ct:
            return None
        text, meta = _soup_to_text(resp.text)
        return {
            "fetcher": "httpx" if user_agent == USER_AGENT else "httpx-googlebot",
            "url": str(resp.url),
            "status": resp.status_code,
            "text": text,
            "meta": meta,
            "raw_html_len": len(resp.text),
        }
    except Exception as e:
        log.warning("httpx fetch failed for %s (UA=%s): %s",
                    url, "googlebot" if user_agent == GOOGLEBOT_UA else "browser", e)
        return None


async def _fetch_httpx(url: str) -> Optional[dict]:
    """Two-shot httpx: browser UA first, Googlebot UA on thin/failed result.
    Many SaaS landing pages SSR a richer payload to crawlers than to browsers
    (for SEO), so the second pass routinely succeeds where the first failed."""
    primary = await _fetch_httpx_once(url, USER_AGENT)
    if not _is_thin(primary):
        return primary
    secondary = await _fetch_httpx_once(url, GOOGLEBOT_UA)
    return secondary or primary


async def _fetch_firecrawl(url: str) -> Optional[dict]:
    """Firecrawl markdown extraction. Falls back to None when key missing."""
    if not os.getenv("FIRECRAWL_API_KEY"):
        return None
    try:
        from enrichment_engine.tools.scraper import FirecrawlScraper
        scraper = FirecrawlScraper()
        md = await scraper.scrape_url(url)
        if not md:
            return None
        return {
            "fetcher": "firecrawl",
            "url": url,
            "status": 200,
            "text": md[:8000],
            "meta": {},
            "raw_html_len": len(md),
        }
    except Exception as e:
        log.warning("firecrawl fetch failed for %s: %s", url, e)
        return None


def _is_thin(result: Optional[dict]) -> bool:
    """True when httpx returned but the content is too sparse to be useful —
    indicator of JS-rendered SPAs, paywalls, or anti-bot interstitials."""
    if not result:
        return True
    text = result.get("text") or ""
    return len(text) < MIN_USEFUL_CHARS


async def fetch_page(url: str, force: Optional[str] = None) -> Optional[dict]:
    """Hybrid fetch. `force='httpx'|'firecrawl'` skips the waterfall.

    Returns a dict with: fetcher, url, status, text, meta, raw_html_len.
    Returns None when both backends fail."""
    if not url or not urlparse(url).scheme.startswith("http"):
        return None

    if force == "firecrawl":
        return await _fetch_firecrawl(url)
    if force == "httpx":
        return await _fetch_httpx(url)

    primary = await _fetch_httpx(url)
    if not _is_thin(primary):
        return primary

    log.info("page %s thin via httpx (%d chars), escalating to firecrawl",
             url, len((primary or {}).get("text") or ""))
    secondary = await _fetch_firecrawl(url)
    return secondary or primary  # return whichever has *something*

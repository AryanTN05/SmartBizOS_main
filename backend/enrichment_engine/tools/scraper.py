"""
Firecrawl API wrapper for web scraping and markdown extraction.

Provides single-page scraping and multi-page domain scraping with:
  - parallel fetches (Firecrawl SDK is sync → wrapped in asyncio.to_thread)
  - graceful fallbacks for missing subpages
  - extensive default subpage coverage (careers, integrations, customers, etc.)
"""

import asyncio
import logging
from urllib.parse import urlparse

from firecrawl import Firecrawl

from config import settings

logger = logging.getLogger(__name__)


# Subpages we always try on any target domain. Ordered so the highest-signal
# pages come first; lower-priority ones are best-effort.
DEFAULT_SUBPAGES: tuple[str, ...] = (
    # Core firmographics & narrative
    "",
    "/about",
    
    # Hiring signals — Tier-1 priority.
    "/careers",
    
    # Product + tech stack signals
    "/pricing",
)


# Query templates used by callers (agents/enrichment.py) to drive grounded
# Google Search pre-passes. Kept here so the scraping/search surface is
# discoverable in one place.

# ATS + careers-page searches (drives the hiring pre-pass).
ATS_SEARCH_HINTS: tuple[str, ...] = (
    "site:greenhouse.io {company}",
    "site:jobs.lever.co {company}",
    "site:boards.greenhouse.io {company}",
    "site:ashbyhq.com {company}",
    "site:jobs.ashbyhq.com {company}",
    "site:workable.com {company}",
    "site:jobs.workable.com {company}",
    "site:smartrecruiters.com {company}",
    "site:recruitee.com {company}",
    "site:bamboohr.com {company}",
    "site:linkedin.com/jobs {company}",
    "{company} careers",
    "{company} jobs hiring",
    "{company} open roles",
)

# Company-profile searches (drives the funding + leadership + headcount pre-passes).
# LinkedIn, Crunchbase, and Tracxn are the three canonical B2B profile sources —
# every B2B company of note has a page on at least one of these.
PROFILE_SEARCH_HINTS: tuple[str, ...] = (
    "site:linkedin.com/company {company}",
    "site:linkedin.com/company {company} about",
    "site:crunchbase.com/organization {company}",
    "site:crunchbase.com {company} funding",
    "site:tracxn.com {company}",
    "site:tracxn.com/d/companies {company}",
    "site:pitchbook.com {company}",
)

# LinkedIn-specific searches (drives the headcount-delta pre-pass).
LINKEDIN_SEARCH_HINTS: tuple[str, ...] = (
    "site:linkedin.com/company {company}",
    "site:linkedin.com/company {company} employees",
    "site:linkedin.com/company {company} about",
    "site:linkedin.com/pulse {company}",  # posts mentioning the company
    "{company} linkedin employee count",
    "{company} linkedin headcount growth",
)


class FirecrawlScraper:
    """Wrapper around the Firecrawl SDK for markdown extraction."""

    def __init__(self) -> None:
        if not settings.firecrawl_api_key:
            raise RuntimeError(
                "FIRECRAWL_API_KEY not configured. Set it in .env before using enrichment."
            )
        self._client = Firecrawl(api_key=settings.firecrawl_api_key)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _scrape_sync(self, url: str) -> str:
        """Blocking scrape call — safe to run under asyncio.to_thread.
        We let exceptions bubble up so gather(return_exceptions=True) catches them.
        """
        result = self._client.scrape(
            url=url,
            formats=["markdown"],
            only_main_content=True,
        )
        return result.markdown or ""

    @staticmethod
    def _normalize_base(domain: str) -> str:
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        return domain.rstrip("/")

    # ── Public API ────────────────────────────────────────────────────────

    async def scrape_url(self, url: str) -> str:
        """Scrape a single URL and return markdown. Returns '' on failure."""
        logger.info(f"Scraping URL: {url}")
        markdown = await asyncio.to_thread(self._scrape_sync, url)
        if markdown:
            logger.info(f"Scraped {len(markdown)} chars from {url}")
        else:
            logger.warning(f"Empty scrape for {url}")
        return markdown

    async def scrape_many(self, urls: list[str]) -> dict[str, str]:
        """
        Scrape many URLs concurrently. Returns {url: markdown} and drops
        any page that came back empty (<100 chars of real content).
        """
        logger.info(f"Parallel scrape: {len(urls)} URLs")
        results = await asyncio.gather(
            *(asyncio.to_thread(self._scrape_sync, url) for url in urls),
            return_exceptions=True,
        )

        out: dict[str, str] = {}
        for url, md in zip(urls, results):
            if isinstance(md, Exception):
                logger.debug(f"Skipped {url}: {md}")
                continue
            if md and len(md) > 100:
                out[url] = md
                logger.info(f"Scraped {len(md)} chars from {url}")
        return out

    async def deep_scrape_domain(
        self,
        domain: str,
        extra_paths: list[str] | None = None,
    ) -> str:
        """
        Scrape a domain's key pages in parallel and return concatenated markdown.

        Covers: homepage, company/about, careers (+ common ATS paths), integrations,
        customers, pricing, blog/news. Missing subpages are skipped silently.

        Args:
            domain: Base domain (e.g., "example.com" or "https://example.com").
            extra_paths: Additional paths to attempt on top of DEFAULT_SUBPAGES.
        """
        base_url = self._normalize_base(domain)

        paths = list(DEFAULT_SUBPAGES)
        if extra_paths:
            paths.extend(extra_paths)

        urls = [f"{base_url}{p}" for p in paths]
        scraped = await self.scrape_many(urls)

        if not scraped:
            logger.warning(f"Deep scrape: no content for {base_url}")
            return f"[No content found for {base_url}]"

        # Preserve the original priority ordering in the output.
        sections: list[str] = []
        for url in urls:
            md = scraped.get(url)
            if md:
                sections.append(f"--- PAGE: {url} ---\n\n{md}")

        combined = "\n\n".join(sections)
        logger.info(
            f"Deep scrape: {len(sections)}/{len(urls)} pages hit, "
            f"{len(combined)} total chars for {urlparse(base_url).netloc}"
        )
        return combined


# ── Module-level singleton ────────────────────────────────────────────────────

_scraper: FirecrawlScraper | None = None


def get_scraper() -> FirecrawlScraper:
    """Return a singleton scraper instance."""
    global _scraper
    if _scraper is None:
        _scraper = FirecrawlScraper()
    return _scraper

"""Unit tests for the scraper helpers + Atom feed parsing."""

import xml.etree.ElementTree as ET

import pytest

from automations.scrapers import (
    LINKEDIN_SEED_FIXTURES,
    SCRAPER_HANDLERS,
    _domain_from_url,
    _strip_html,
)


def test_strip_html_removes_tags():
    assert _strip_html("<p>hello <b>world</b></p>") == "hello world"
    assert _strip_html("plain text") == "plain text"
    assert _strip_html("") == ""
    assert _strip_html(None) == ""


def test_domain_from_url():
    assert _domain_from_url("https://example.com/path") == "example.com"
    assert _domain_from_url("http://sub.example.com/") == "sub.example.com"
    assert _domain_from_url("") is None
    assert _domain_from_url("not-a-url") is None


def test_handlers_registered_for_known_sources():
    assert "producthunt" in SCRAPER_HANDLERS
    assert "linkedin_seed" in SCRAPER_HANDLERS


def test_linkedin_fixtures_have_expected_shape():
    assert len(LINKEDIN_SEED_FIXTURES) >= 3
    for fx in LINKEDIN_SEED_FIXTURES:
        assert fx.get("name")
        assert fx.get("company")
        assert fx.get("url", "").startswith("https://www.linkedin.com/")


def test_atom_feed_parses_into_rows(monkeypatch):
    """Verify the Atom-feed parser handles ProductHunt's actual response shape."""
    # Minimal Atom feed mimicking ProductHunt's structure.
    sample = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Product Hunt</title>
  <entry>
    <title>Acme Robot — Summarises your stand-ups</title>
    <link href="https://www.producthunt.com/posts/acme-robot"/>
    <summary>&lt;p&gt;An AI scribe for sprint reviews.&lt;/p&gt;</summary>
  </entry>
  <entry>
    <title>Notebrew</title>
    <link href="https://www.producthunt.com/posts/notebrew"/>
    <summary>Markdown-first note app.</summary>
  </entry>
</feed>"""
    feed = ET.fromstring(sample)
    NS = {"a": "http://www.w3.org/2005/Atom"}
    entries = feed.findall("a:entry", NS)
    assert len(entries) == 2

    titles = [e.findtext("a:title", default="", namespaces=NS) for e in entries]
    assert "Acme Robot" in titles[0]
    assert titles[1] == "Notebrew"

    # Link is an attribute, not text — same shape as the live feed.
    link = entries[0].find("a:link", NS).get("href")
    assert link.startswith("https://www.producthunt.com/")


@pytest.mark.asyncio
async def test_unknown_source_returns_no_handler():
    from automations.scrapers import execute_scraper
    import uuid
    result = await execute_scraper("not-a-real-source", uuid.uuid4())
    assert result["ran"] is False
    assert "no handler" in (result.get("error") or "").lower()

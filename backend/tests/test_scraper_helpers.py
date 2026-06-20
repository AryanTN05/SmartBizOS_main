"""Tests for the pure helpers in automations/scrapers.py.

Stays out of network territory — only the parsers + dedup logic.
"""

from automations.scrapers import (
    _parse_funding, _normalize_domain, _reddit_intent_score,
    _is_recent_yc_batch, _job_board_seeds,
)


# ─── _parse_funding ────────────────────────────────────────────────────────


def test_funding_series_a_with_amount():
    out = _parse_funding("Acme raises $12M Series A from Sequoia")
    assert out["detected"] is True
    assert out["amount_raw"].startswith("$")
    assert out["round"] == "series-a"


def test_funding_seed_round():
    out = _parse_funding("Beta closes its $500K seed round from YC")
    assert out["detected"] is True
    assert out["round"] == "seed"


def test_funding_pre_seed():
    out = _parse_funding("Gamma announces $250K pre-seed funding")
    assert out["detected"] is True
    assert out["round"] == "pre-seed"


def test_funding_billion():
    out = _parse_funding("Delta raises $2.5 billion at $40B valuation")
    assert out["detected"] is True
    # First match wins — should be the $2.5 billion (the raise), not $40B
    # (the valuation).
    assert "billion" in out["amount_raw"].lower() or "2.5" in out["amount_raw"]


def test_funding_no_signal_returns_negative():
    out = _parse_funding("Acme launches new dashboard product")
    assert out["detected"] is False
    assert "round" not in out
    assert "amount_raw" not in out


# ─── _normalize_domain ─────────────────────────────────────────────────────


def test_normalize_strips_protocol_and_www():
    assert _normalize_domain("https://www.acme.com") == "acme.com"
    assert _normalize_domain("http://www.Acme.COM") == "acme.com"


def test_normalize_strips_path_and_query():
    assert _normalize_domain("https://acme.com/page?q=1") == "acme.com"


def test_normalize_reduces_subdomain_to_registrable():
    """blog.acme.com → acme.com so cross-source matching links the
    company even when one source links the blog and another the root."""
    assert _normalize_domain("https://blog.acme.com/post") == "acme.com"


def test_normalize_handles_port():
    assert _normalize_domain("http://acme.com:8080/x") == "acme.com"


def test_normalize_returns_none_for_garbage():
    assert _normalize_domain("") is None
    assert _normalize_domain("nodomain") is None
    assert _normalize_domain(None) is None


def test_normalize_handles_no_protocol():
    """Bare hostnames also normalize."""
    assert _normalize_domain("acme.com") == "acme.com"


# ─── _reddit_intent_score ──────────────────────────────────────────────────


def test_reddit_intent_explicit_match():
    score = _reddit_intent_score("Looking for a CRM that doesn't suck", "")
    assert score >= 55


def test_reddit_intent_multiple_keywords_higher():
    """Two keyword hits beats one."""
    a = _reddit_intent_score("Looking for a tool", "")
    b = _reddit_intent_score("Looking for a tool — anyone using Apollo?", "")
    assert b > a


def test_reddit_intent_pain_language_boost():
    """Pain words + intent keyword bump the score above the base."""
    base = _reddit_intent_score("Looking for a CRM", "")
    pain = _reddit_intent_score(
        "Looking for a CRM", "frustrated with hubspot, fed up with the upsells"
    )
    assert pain > base


def test_reddit_intent_no_keyword_zero():
    assert _reddit_intent_score("hello world", "just saying hi") == 0


def test_reddit_intent_score_capped():
    """Even with every keyword, score should never exceed 90."""
    # Stuff every keyword in
    body = " ".join([
        "looking for", "any recommendations", "anyone using",
        "we're evaluating", "switched from", "alternatives to",
        "best tool for", "recommendations for", "frustrated", "fed up",
    ])
    out = _reddit_intent_score("looking for", body)
    assert out <= 90


# ─── YC batch year filter ─────────────────────────────────────────────────


def test_yc_recent_batch():
    assert _is_recent_yc_batch("Winter 2026") is True
    assert _is_recent_yc_batch("Summer 2025") is True


def test_yc_old_batch():
    assert _is_recent_yc_batch("Winter 2018") is False
    assert _is_recent_yc_batch("Summer 2015") is False


def test_yc_empty_batch():
    assert _is_recent_yc_batch("") is False
    assert _is_recent_yc_batch(None) is False


# ─── job board seeds ──────────────────────────────────────────────────────


def test_job_board_seeds_default():
    """Without env config, return sensible default seeds."""
    seeds = _job_board_seeds()
    assert len(seeds) > 0
    for prov, token in seeds:
        assert prov in ("greenhouse", "lever", "ashby")
        assert token  # non-empty


def test_job_board_seeds_from_env(monkeypatch):
    monkeypatch.setenv("JOB_BOARD_TOKENS",
                       "greenhouse:stripe,lever:figma,ashby:posthog,bogus:thing")
    seeds = _job_board_seeds()
    # Bogus provider filtered out.
    assert ("bogus", "thing") not in seeds
    assert ("greenhouse", "stripe") in seeds
    assert ("lever", "figma") in seeds
    assert ("ashby", "posthog") in seeds

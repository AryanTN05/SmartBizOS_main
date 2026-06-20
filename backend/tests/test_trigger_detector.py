"""Tests for the buying-intent trigger detector.

Pure regex + field-presence logic. Verifies hiring/funding/launch/
tech_stack_change pattern matches across notes/title/scraper/enrichment
and the score-boost cap.
"""

from automations.trigger_detector import (
    detect_triggers, score_boost_for, MAX_BOOST, PER_TRIGGER_BOOST,
    TRIGGER_VALUES,
)


def test_no_signal_returns_empty():
    assert detect_triggers() == []
    assert detect_triggers(notes="completely benign text") == []


def test_hiring_in_notes():
    assert detect_triggers(notes="We're hiring 5 engineers") == ["hiring"]
    assert detect_triggers(notes="Now hiring across the team") == ["hiring"]


def test_funding_in_notes():
    assert detect_triggers(notes="Acme raised a Series B last week") == ["funding"]
    assert detect_triggers(notes="Just closed our seed round") == ["funding"]


def test_funding_via_enrichment_field():
    """When the structured enrichment carries a stage, that's a hard hit
    even without keyword text."""
    out = detect_triggers(
        notes="ordinary about page",
        enrichment={"funding": {"stage": "series-a"}},
    )
    assert "funding" in out


def test_launch_via_keyword():
    out = detect_triggers(notes="Just launched on Product Hunt today!")
    assert "launch" in out


def test_launch_via_scraper_source():
    """PH origin counts as a launch signal even without keyword."""
    out = detect_triggers(scraper_raw={"source": "product_hunt"})
    assert "launch" in out


def test_tech_stack_shift():
    out = detect_triggers(notes="Migrated from Postgres to Kafka")
    assert "tech_stack_change" in out


def test_canonical_order():
    """Multiple triggers come back in canonical order regardless of which
    field they were detected from."""
    out = detect_triggers(
        notes="We're hiring",
        scraper_raw={"description": "Just launched on Product Hunt"},
        enrichment={"funding": {"stage": "seed"}},
    )
    # Order from TRIGGER_VALUES: hiring, funding, launch, tech_stack_change
    assert out == ["hiring", "funding", "launch"]


def test_score_boost_per_trigger():
    assert score_boost_for([]) == 0
    assert score_boost_for(["hiring"]) == PER_TRIGGER_BOOST
    assert score_boost_for(["hiring", "funding"]) == PER_TRIGGER_BOOST * 2


def test_score_boost_capped():
    """Cap protects from runaway scores — a lead with all 4 triggers
    shouldn't pile up to 100 from triggers alone."""
    assert score_boost_for(list(TRIGGER_VALUES)) == MAX_BOOST


def test_unknown_trigger_doesnt_count():
    assert score_boost_for(["unknown"]) == 0


def test_no_double_counting():
    """A lead with hiring mentioned twice in different fields should
    still only carry the trigger once."""
    out = detect_triggers(
        notes="we're hiring",
        title="hiring across the team",
        scraper_raw={"description": "Job openings posted"},
    )
    assert out.count("hiring") == 1

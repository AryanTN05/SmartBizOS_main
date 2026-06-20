"""Unit tests for report-stats helpers (no DB required)."""

from datetime import datetime, timezone

from routers.reports import _format_headline


def test_headline_with_full_stats():
    stats = {
        "leads": {"new_leads_count": 89, "hot_count": 16},
        "automations": {"reply_rate": 0.084},
    }
    headline = _format_headline(stats)
    assert "89" in headline
    assert "16" in headline
    assert "8.4%" in headline


def test_headline_handles_zero_stats():
    stats = {
        "leads": {"new_leads_count": 0, "hot_count": 0},
        "automations": {"reply_rate": 0.0},
    }
    headline = _format_headline(stats)
    assert "0 new leads" in headline
    assert "0 hot" in headline


def test_headline_handles_missing_keys():
    # When stats are partial (e.g. tenant just spun up, no leads yet),
    # headline should still render a sane string instead of throwing.
    headline = _format_headline({"leads": {}, "automations": {}})
    assert "0" in headline


def test_headline_handles_none_reply_rate():
    stats = {
        "leads": {"new_leads_count": 5, "hot_count": 1},
        "automations": {"reply_rate": None},
    }
    headline = _format_headline(stats)
    # Falls back to 0% when the rate is None.
    assert "0.0%" in headline

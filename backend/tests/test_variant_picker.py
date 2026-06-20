"""Tests for the A/B opener variant picker.

Pure-Python — no DB, no LLM. Verifies the epsilon-greedy logic:
explore until every variant has 3+ sends, then exploit by reply rate.
"""

from automations.variant_picker import (
    pick_variant, record_send, record_reply, _EXPLORE_FLOOR,
)


def test_pick_empty_returns_none():
    assert pick_variant([]) is None
    assert pick_variant(None) is None


def test_pick_fresh_picks_first():
    """Three brand-new variants — round-robin starts at index 0."""
    variants = [{"sent_count": 0}, {"sent_count": 0}, {"sent_count": 0}]
    assert pick_variant(variants) == 0


def test_pick_under_explored_picks_lowest_count():
    """One variant has 5 sends, one has 1 — pick the under-sampled one."""
    variants = [
        {"sent_count": 5, "replied_count": 1, "text": "a"},
        {"sent_count": 1, "replied_count": 0, "text": "b"},
    ]
    assert pick_variant(variants) == 1


def test_pick_at_floor_picks_by_reply_rate():
    """All variants past the explore floor — winner is highest reply rate."""
    variants = [
        {"sent_count": 3, "replied_count": 0, "text": "a"},
        {"sent_count": 3, "replied_count": 2, "text": "b"},  # 67%
        {"sent_count": 3, "replied_count": 1, "text": "c"},  # 33%
    ]
    assert pick_variant(variants) == 1  # b wins


def test_pick_ties_broken_by_declaration_order():
    """Two variants with identical reply rates — earlier wins."""
    variants = [
        {"sent_count": 3, "replied_count": 1, "text": "a"},
        {"sent_count": 3, "replied_count": 1, "text": "b"},
        {"sent_count": 3, "replied_count": 0, "text": "c"},
    ]
    assert pick_variant(variants) == 0


def test_record_send_increments_only_target():
    variants = [
        {"sent_count": 1, "replied_count": 0, "text": "a"},
        {"sent_count": 1, "replied_count": 0, "text": "b"},
    ]
    out = record_send(variants, 1)
    assert out[0]["sent_count"] == 1   # untouched
    assert out[1]["sent_count"] == 2   # bumped
    # Original list isn't mutated (defensive copy).
    assert variants[1]["sent_count"] == 1


def test_record_send_out_of_range_is_noop():
    variants = [{"sent_count": 1, "text": "a"}]
    out = record_send(variants, 5)
    assert out[0]["sent_count"] == 1


def test_record_reply_matches_by_text():
    variants = [
        {"sent_count": 3, "replied_count": 0, "text": "alpha"},
        {"sent_count": 3, "replied_count": 0, "text": "beta"},
    ]
    out = record_reply(variants, "beta")
    assert out[0]["replied_count"] == 0
    assert out[1]["replied_count"] == 1


def test_record_reply_no_match_is_noop():
    variants = [{"sent_count": 1, "replied_count": 0, "text": "a"}]
    out = record_reply(variants, "z")
    assert out[0]["replied_count"] == 0


def test_record_reply_returns_input_when_no_variants():
    assert record_reply(None, "anything") is None
    assert record_reply([], "anything") == []


def test_explore_floor_is_three():
    """Pin the explore-floor constant — changing it changes outbound
    behavior in production, so the test exists to make the change loud."""
    assert _EXPLORE_FLOOR == 3

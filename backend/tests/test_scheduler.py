"""Unit tests for the automation scheduler step transitions."""

from automations.scheduler import STEPS, WAIT_AFTER, _next_step


def test_step_transition_from_start():
    assert _next_step(None) == "load_lead"


def test_step_transition_through_pipeline():
    assert _next_step("load_lead") == "render_email_day0"
    assert _next_step("render_email_day0") == "send_day0"
    assert _next_step("send_day0") == "wait_3_days"
    assert _next_step("wait_3_days") == "wait_open"


def test_step_transition_from_terminal():
    # wait_open is the last in STEPS — next should be None (run completes).
    assert _next_step("wait_open") is None


def test_step_transition_unknown_returns_none():
    assert _next_step("not-a-real-step") is None


def test_send_day0_is_wait_after():
    # The wait happens *after* send_day0 fires (so there's a gap before
    # wait_3_days). If this changes, the scheduler timing changes too.
    assert "send_day0" in WAIT_AFTER


def test_steps_pipeline_is_intact():
    # Sanity: the canonical pipeline order hasn't drifted.
    assert STEPS == [
        None,
        "load_lead",
        "render_email_day0",
        "send_day0",
        "wait_3_days",
        "wait_open",
    ]

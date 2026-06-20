"""Tests for reply intent classification.

Only the heuristic pre-filter is exercised here — LLM path requires a
key + network so it's covered by integration runs, not unit tests. The
pre-filter handles the highest-volume cases (unsubscribe, OOO) so it
needs to be rock-solid.
"""

import asyncio
import os

import pytest

from automations.reply_intent import (
    INTENT_VALUES, _heuristic_classify, classify_reply_intent,
)


def test_intent_values_set():
    """Pin the canonical intent set — changing it breaks the FE
    intentMeta() lookup table; test exists to make the change loud."""
    assert set(INTENT_VALUES) == {
        "positive", "negative", "neutral",
        "wrong_person", "unsubscribe", "auto_reply",
    }


def test_heuristic_unsubscribe_variants():
    cases = [
        "Please unsubscribe me",
        "stop emailing me",
        "Take me off the list",
        "remove me from this list",
        "I want to opt out",
        "Opt-out request",
    ]
    for c in cases:
        assert _heuristic_classify(c) == "unsubscribe", f"missed: {c!r}"


def test_heuristic_ooo_variants():
    cases = [
        "Out of office until Monday",
        "I'm on vacation this week",
        "Currently out — back next week",
        "I will be back on January 15",
        "On annual leave through Friday",
    ]
    for c in cases:
        assert _heuristic_classify(c) == "auto_reply", f"missed: {c!r}"


def test_heuristic_returns_none_for_real_replies():
    """Substantive replies must NOT be classified by the heuristic —
    they fall through to the LLM. Returning a wrong intent here would
    save a token but corrupt the data."""
    cases = [
        "Sounds great, can we talk Tuesday?",
        "Not interested, thanks.",
        "Wrong person — try Sarah at sarah@example.com",
        "Tell me more about your pricing",
    ]
    for c in cases:
        assert _heuristic_classify(c) is None, f"shouldn't classify: {c!r}"


def test_heuristic_empty_returns_neutral():
    """Empty / whitespace snippets degrade to neutral."""
    assert _heuristic_classify("") == "neutral"


def test_classify_async_falls_back_when_no_llm_key():
    """Without an LLM key set + no heuristic match → "neutral" not raise."""
    # Strip every supported key for the duration of this call.
    saved = {k: os.environ.pop(k, None)
             for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")}
    try:
        out = asyncio.run(classify_reply_intent("Sounds great, let's chat"))
        assert out == "neutral"
    finally:
        for k, v in saved.items():
            if v:
                os.environ[k] = v


def test_classify_unsubscribe_doesnt_call_llm():
    """Heuristic should fire BEFORE the LLM path so unsubscribes work
    even with no key set."""
    saved = {k: os.environ.pop(k, None)
             for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")}
    try:
        out = asyncio.run(classify_reply_intent("Please unsubscribe me from this"))
        assert out == "unsubscribe"
    finally:
        for k, v in saved.items():
            if v:
                os.environ[k] = v

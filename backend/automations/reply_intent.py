"""Reply intent classifier.

Takes a snippet of a prospect's reply and returns one of:
   positive, negative, neutral, wrong_person, unsubscribe, auto_reply

Used by both the IMAP poller and the manual /reply endpoint. Falls back
to "neutral" when no LLM key is set or the call fails — never blocks the
reply-detection path. The classification gives the SDR an at-a-glance
sense of where to spend time, and gives us per-template signal data on
which messaging variants generate positive vs negative replies.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger("smartbiz.reply_intent")

INTENT_VALUES = (
    "positive", "negative", "neutral",
    "wrong_person", "unsubscribe", "auto_reply",
)

_UNSUB_PATTERNS = re.compile(
    r"\b(unsubscribe|opt[\s\-]?out|stop emailing|remove me|take me off)\b",
    re.IGNORECASE,
)
_OOO_PATTERNS = re.compile(
    r"\b(out of office|on vacation|annual leave|away from my desk|"
    r"will be back on|currently out)\b",
    re.IGNORECASE,
)


def _heuristic_classify(snippet: str) -> Optional[str]:
    """Quick regex-based pre-filter so we don't spend an LLM call on
    obviously-classifiable replies. Returns None when uncertain → caller
    falls through to LLM."""
    if not snippet:
        return "neutral"
    s = snippet.lower()
    if _UNSUB_PATTERNS.search(s):
        return "unsubscribe"
    if _OOO_PATTERNS.search(s):
        return "auto_reply"
    return None


_SYSTEM_PROMPT = """You classify a B2B sales prospect's email reply into one of:
- positive: showed interest, asked a question, agreed to a meeting
- negative: declined, said no, said the timing is bad
- neutral: acknowledged but didn't commit either way
- wrong_person: said you have the wrong contact / forwarded
- unsubscribe: asked to be removed from the list
- auto_reply: out-of-office, vacation auto-responder

Respond with ONLY the single category word. No punctuation, no quotes,
no explanation. If unclear, return neutral.
"""


async def classify_reply_intent(snippet: str) -> str:
    """Classify a reply snippet. Always returns a valid intent string,
    never raises. Falls back to 'neutral' on any error."""
    if not snippet:
        return "neutral"

    # Cheap regex pre-filter for the easy cases.
    quick = _heuristic_classify(snippet)
    if quick:
        return quick

    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
        return "neutral"  # no LLM available — degrade silently

    try:
        from lara_smartbiz.utils.llm import complete_text
        # Trim to ~2KB so we don't pay for long forwarded threads.
        clip = snippet[:2000]
        raw = (await complete_text(
            f"Reply:\n\n{clip}",
            system=_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=8,
        )).lower()
        # Strip stray quotes / punctuation the model sometimes adds.
        for q in ('"', "'", "`", "*", ".", ",", ":"):
            raw = raw.strip(q)
        # Take just the first word in case the model adds explanation.
        token = raw.split()[0] if raw else ""
        if token in INTENT_VALUES:
            return token
        log.info("reply_intent: unrecognized response %r → neutral", raw)
        return "neutral"
    except Exception as e:
        log.warning("reply_intent classifier failed: %s → neutral", e)
        return "neutral"

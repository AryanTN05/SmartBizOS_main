"""
Lara LLM layer — Gemini-only via google-genai.

This is the unified replacement for the previous LiteLLM-based calls scattered
across the backend. Single SDK, single model family, no provider abstraction
to keep in sync.

Two surfaces:
- `complete_text(...)` — one-shot text completion. Used by batch jobs
  (lead scoring, opening lines, reports narrative, reply-intent classifier,
  enrichment). Synchronous in feel, async under the hood.
- (Live API for interactive chat / voice lives in services/voice.py and
  routers/stream.py — they hold the streaming sessions directly.)

Model selection:
- Batch default: `gemini-2.5-flash` (override with LARA_MODEL env var).
- Live default: `gemini-3.1-flash-live-preview` (override with LARA_VOICE_MODEL).

The LARA_MODEL value may carry the legacy LiteLLM `gemini/` prefix (e.g.
`gemini/gemini-2.5-flash`) — `_resolve_model()` strips it so existing
env values keep working without an ops change.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from google.genai import types

from lara_smartbiz.utils.clients import get_gemini_client

log = logging.getLogger("smartbiz.llm")

_DEFAULT_BATCH_MODEL = "gemini-2.5-flash"


def _resolve_model(model: Optional[str]) -> str:
    """Strip the LiteLLM `gemini/` prefix if present so callers can pass
    either form (`gemini/gemini-2.5-flash` or `gemini-2.5-flash`)."""
    raw = model or os.getenv("LARA_MODEL") or _DEFAULT_BATCH_MODEL
    if raw.startswith("gemini/"):
        return raw.split("/", 1)[1]
    return raw


async def complete_text(
    user_prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.4,
    max_output_tokens: int = 1024,
    response_json: bool = False,
    response_schema: Optional[Any] = None,
    google_search: bool = False,
    extra_tools: Optional[list] = None,
) -> str:
    """One-shot Gemini text completion.

    Args:
        user_prompt: The user's input. Required.
        system: Optional system instruction. Equivalent to LiteLLM's
                {"role": "system"} message.
        model: Override the model. Defaults to LARA_MODEL or gemini-2.5-flash.
        temperature: Sampling temperature.
        max_output_tokens: Cap on the response length.
        response_json: If True, ask Gemini for JSON output (sets
                       response_mime_type=application/json). Caller still
                       runs json.loads() on the return.
        response_schema: Pydantic model class describing the expected JSON
                         shape. Implies response_json=True. Gemini enforces
                         the schema server-side.
        google_search: If True, attach the Google Search grounding tool.
        extra_tools: Additional types.Tool entries to attach.

    Returns:
        The model's text response (empty string if blocked / no candidates).
    """
    client = get_gemini_client()
    resolved = _resolve_model(model)

    cfg_kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    if system:
        cfg_kwargs["system_instruction"] = system
    if response_schema is not None:
        cfg_kwargs["response_mime_type"] = "application/json"
        cfg_kwargs["response_schema"] = response_schema
    elif response_json:
        cfg_kwargs["response_mime_type"] = "application/json"

    tools = list(extra_tools or [])
    if google_search:
        tools.append(types.Tool(google_search=types.GoogleSearch()))
    if tools:
        cfg_kwargs["tools"] = tools

    config = types.GenerateContentConfig(**cfg_kwargs)

    resp = await client.aio.models.generate_content(
        model=resolved,
        contents=user_prompt,
        config=config,
    )
    return (resp.text or "").strip()

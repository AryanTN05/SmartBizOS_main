"""
Lara agent loop — Gemini Live API, TEXT modality.

Replaces the previous LiteLLM-based loop so the chat and voice paths share
one model + SDK. Each call opens a Live session, sends the conversation as
Content turns, and iterates server messages (text deltas + function_calls)
until turn_complete with no further tool calls.
"""

from __future__ import annotations

import inspect
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from google.genai import types
from google.genai.types import (
    LiveConnectConfig, SpeechConfig, VoiceConfig, PrebuiltVoiceConfig, HistoryConfig,
)

from lara_smartbiz.tools import get_tool_registry, TOOL_FUNCTIONS
from lara_smartbiz.utils.clients import get_gemini_client


# Default model — same Live alias the voice path uses. Override via
# LARA_VOICE_MODEL (single env var shared by both interactive paths).
DEFAULT_MODEL = os.getenv("LARA_VOICE_MODEL", "gemini-3.1-flash-live-preview")


@dataclass
class AgentContext:
    session_id: str
    messages: list[dict[str, Any]]
    system_prompt: str = ""
    current_module: str = ""
    memory_snippets: str = ""
    seed_context: str = ""


def build_system_prompt(context: AgentContext) -> str:
    import datetime
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
    return f"""You are Lara — the AI brain of SmartBiz OS, an AI business platform.
You can read and write data across all modules: CRM, Automation, Reports, etc.
Current date and time: {current_time}

HEAVY GUARDRAILS & IDENTITY:
1. You MUST strictly maintain your identity as Lara at all times. Never break character.
2. Your sole purpose is to assist with business operations, CRM, reporting, outreach, analytics, and business research.
3. IF the user asks about ANYTHING else (e.g., coding, tech support, personal advice, general trivia, entertainment), you MUST decline gracefully.
4. For example: "I am Lara, your business assistant. I only handle tasks related to SmartBiz OS and business operations."
5. DO NOT write code. DO NOT provide coding instructions.
6. Be concise, direct, and professional.

IMPORTANT OUTPUT STRUCTURE:
Your response MUST be formatted as a JSON object containing:
- "answer": Your direct, conversational response to the user.
- "artifacts": An object with "url", "table", and "charts" fields.
  - "url": If your response references a specific video or image, provide its URI here (otherwise empty string).
  - "table": If your response includes tabular data or structured lists, provide it here in HTML format (otherwise empty string).
  - "charts": If your response includes chart data, provide a stringified JSON Chart.js configuration object here (otherwise empty string).

Current module the user is viewing: {context.current_module or 'dashboard'}

Relevant memory from past interactions:
{context.memory_snippets}

Business context:
{context.seed_context}

Be concise and direct. You're an intelligent business assistant.
"""


# ─────────────────────────────────────────
# Agent loop — Gemini Live, TEXT modality
# ─────────────────────────────────────────

DISPLAY_ONLY_TOOLS = {"show_artifact"}
MAX_ITERATIONS = 5


def _build_live_tools() -> list[types.Tool]:
    """Convert get_tool_registry() into Gemini Live FunctionDeclarations.
    The registry already uses Google-style schema (UPPER-CASE types), so
    we pass parameters through unchanged."""
    declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t.get("parameters") or {"type": "OBJECT", "properties": {}},
        )
        for t in get_tool_registry()
    ]
    return [types.Tool(function_declarations=declarations)]


async def run(context: AgentContext) -> AsyncIterator[str]:
    """Stream Gemini Live's response tokens. Handles tool calls inline —
    when Gemini emits tool_call, we execute and send FunctionResponses
    back on the same session, which triggers another model turn. Caps at
    MAX_ITERATIONS to avoid runaway loops."""
    system_text = build_system_prompt(context)
    turns = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in context.messages if m.get("content")
    ]

    # Gemini Live's `gemini-3.1-flash-live-preview` only accepts AUDIO
    # response_modalities. We use output_audio_transcription to receive the
    # response as text (discarding the audio bytes). Same workaround as
    # routers/agents_zero_to_prod.py._build_live_config.
    config = LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(parts=[types.Part.from_text(text=system_text)]),
        tools=_build_live_tools(),
        speech_config=SpeechConfig(
            voice_config=VoiceConfig(
                prebuilt_voice_config=PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        history_config=HistoryConfig(initial_history_in_client_content=True) if len(turns) > 1 else None,
    )

    iterations_remaining = MAX_ITERATIONS
    tool_calls_this_turn = False
    artifact_data = {"url": "", "table": "", "charts": ""}
    all_display_only = True

    async with get_gemini_client().aio.live.connect(model=DEFAULT_MODEL, config=config) as session:
        # Seed history (if any) without triggering a response, then send the
        # latest user turn via send_realtime_input to fire the actual reply.
        if len(turns) > 1:
            await session.send_client_content(turns=turns[:-1], turn_complete=False)
        if turns:
            await session.send_realtime_input(text=turns[-1].parts[0].text)

        async for message in session.receive():
            sc = getattr(message, "server_content", None)
            if sc:
                ot = getattr(sc, "output_transcription", None)
                if ot and ot.text:
                    yield ot.text
                if getattr(sc, "turn_complete", False):
                    if not tool_calls_this_turn:
                        return
                    if all_display_only:
                        # show_artifact-only turns: short-circuit with a
                        # canned answer so we don't loop on display tools.
                        yield json.dumps({
                            "answer": "Here is the artifact you requested.",
                            "artifacts": artifact_data,
                        })
                        return
                    tool_calls_this_turn = False
                    iterations_remaining -= 1
                    if iterations_remaining <= 0:
                        yield "\n[Lara reached maximum reasoning steps for this query.]"
                        return
                    continue

            tc = getattr(message, "tool_call", None)
            if tc and getattr(tc, "function_calls", None):
                tool_calls_this_turn = True
                function_responses = []
                for fc in tc.function_calls:
                    args = dict(fc.args or {})
                    if fc.name != "show_artifact":
                        all_display_only = False
                    if fc.name == "search_documents":
                        args["session_id"] = context.session_id
                    print(f"Executing tool: {fc.name} with args {args}")
                    try:
                        result = await _execute_tool(fc.name, args)
                    except Exception as e:
                        result = {"error": str(e)}
                    if fc.name == "show_artifact":
                        for k in ("url", "table", "charts"):
                            if k in args:
                                artifact_data[k] = args[k]
                    function_responses.append(types.FunctionResponse(
                        name=fc.name,
                        id=fc.id or f"call_{uuid.uuid4().hex[:8]}",
                        response={"result": result},
                    ))
                await session.send_tool_response(function_responses=function_responses)


async def _execute_tool(name: str, args: dict) -> Any:
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    if inspect.iscoroutinefunction(fn):
        return await fn(**args)
    return fn(**args)


# Backwards-compat: the old code used Pydantic AgentContext. Some imports may
# rely on `from lara_smartbiz.services.agent import AgentContext` — that still works
# because the dataclass version is API-compatible (positional + kwarg init).
__all__ = ["AgentContext", "build_system_prompt", "run"]

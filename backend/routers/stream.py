"""
routers/stream.py — AI-SDK-compatible chat stream.

Speaks the Vercel AI SDK v6 data-stream protocol over SSE. Two personas:

  • Demo (anon / demo_session) — describes capabilities, doesn't claim live CRM access.
  • Admin (admin_session)     — talks like the in-product assistant, with a
                                 small live-stats brief injected so the model
                                 can answer questions about real numbers.

Real tool execution still goes through /lara-smartbiz/chat (the agent loop). This
endpoint stays text-only so the chat panel stays snappy; tools land here
when we plumb them into the AI-SDK protocol's tool-call frames.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Optional, Any

from google.genai import types
from google.genai.types import (
    LiveConnectConfig, SpeechConfig, VoiceConfig, PrebuiltVoiceConfig, HistoryConfig,
)
from fastapi import APIRouter, Cookie, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import decode_access_token
from config import settings
from db.connection import get_db
from db.entities import AdminUser, AutomationRun, Lead
from lara_smartbiz.db.connection import SessionLocal as LaraSessionLocal
from lara_smartbiz.db.models import Conversation
from lara_smartbiz.utils.clients import get_gemini_client

router = APIRouter(prefix="/api/stream", tags=["Stream"])

log = logging.getLogger("smartbiz.stream")

# Same Gemini Live model the voice path uses — single brand, same SDK.
# Override via LARA_VOICE_MODEL if Google rolls a new alias.
DEFAULT_MODEL = os.getenv("LARA_VOICE_MODEL", "gemini-3.1-flash-live-preview")


class StreamMessage(BaseModel):
    role: str
    content: str | None = None


class StreamRequest(BaseModel):
    messages: list[StreamMessage]
    conversation_id: str | None = None
    options: dict | None = None


_DEMO_SYSTEM = """You are Lara — the AI brain of SmartBiz OS.
Be concise, friendly, and direct. You have access to tools to interact with the CRM.
Use them to answer questions or perform actions on behalf of the user.
"""

_ADMIN_SYSTEM_TEMPLATE = """You are Lara — the AI brain of SmartBiz OS.
You're operating inside the live admin. The signed-in operator is {admin_name}.
You have read access to their real CRM. Be concise, direct, and act like a
seasoned revops analyst. Reply in plain prose unless the user explicitly asks
for code, lists, or tables.

Live workspace snapshot (refreshed each turn):
{live_brief}

{rag_section}Use these numbers when relevant. You have access to tools to interact with the CRM.
Use them to answer questions or perform actions on behalf of the user.
"""


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _persist_message(session_id: str, role: str, content: str) -> None:
    """Sync write into the Lara SQLite store (it's a sync sessionmaker).
    Called from a worker thread to keep the async stream non-blocking."""
    if not session_id or not content:
        return
    try:
        with LaraSessionLocal() as db:
            db.add(Conversation(session_id=session_id, role=role, content=content))
            db.commit()
    except Exception as e:
        log.warning("persist_message failed for session %s: %s", session_id, e)


async def _persist_async(session_id: str, role: str, content: str) -> None:
    if not session_id or not content:
        return
    await asyncio.to_thread(_persist_message, session_id, role, content)


async def _admin_from_cookie(token: Optional[str], db: AsyncSession) -> Optional[AdminUser]:
    if not token:
        return None
    try:
        user_id = decode_access_token(token)
    except ValueError:
        return None
    return (await db.execute(
        select(AdminUser).where(AdminUser.id == user_id, AdminUser.status == "active")
    )).scalar_one_or_none()


async def _rag_brief(query: str, admin_id: str) -> str:
    """Run a quick semantic search over the admin's documents + extracted
    memory facts; return a short context block to inject into the system
    prompt. Empty string when nothing relevant."""
    if not query:
        return ""
    try:
        from lara_smartbiz.services.memory import search_memory
        # Search across both the admin session's memory and the global "admin"
        # bucket where Lara-extracted facts land.
        sessions = [f"admin:{admin_id}", "admin", "demo_session"]
        all_hits: list[str] = []
        for sid in sessions:
            try:
                hits = await search_memory(query, sid, top_k=3)
                all_hits.extend(hits)
            except Exception:
                continue
        seen = set()
        unique = []
        for h in all_hits:
            if h and h not in seen:
                seen.add(h)
                unique.append(h)
            if len(unique) >= 5:
                break
        if not unique:
            return ""
        joined = "\n".join(f"- {h.strip()[:300]}" for h in unique)
        return (
            "Relevant context from uploaded docs + remembered facts:\n"
            f"{joined}\n\n"
        )
    except Exception as e:
        log.warning("rag brief failed: %s", e)
        return ""


async def _live_brief(db: AsyncSession) -> str:
    """Tiny SQL roll-up the model can quote without us wiring real tools yet."""
    tenant = uuid.UUID(settings.default_tenant_id)
    try:
        active_leads = (await db.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant, Lead.deleted_at.is_(None),
                Lead.status != "lost",
            )
        )).scalar() or 0
        hot = (await db.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant, Lead.deleted_at.is_(None),
                Lead.score >= 75,
            )
        )).scalar() or 0
        runs_running = (await db.execute(
            select(func.count(AutomationRun.id)).where(
                AutomationRun.tenant_id == tenant,
                AutomationRun.status == "running",
            )
        )).scalar() or 0
        runs_failed = (await db.execute(
            select(func.count(AutomationRun.id)).where(
                AutomationRun.tenant_id == tenant,
                AutomationRun.status == "failed",
            )
        )).scalar() or 0
        # Top 5 leads by score, with names + companies + scores.
        top_rows = (await db.execute(
            select(Lead.name, Lead.company_name, Lead.score, Lead.status)
            .where(Lead.tenant_id == tenant, Lead.deleted_at.is_(None))
            .order_by(Lead.score.desc()).limit(5)
        )).all()
        top = "\n".join(
            f"  - {n} ({c or '—'}) · score {s} · stage {st}"
            for (n, c, s, st) in top_rows
        ) or "  (none yet)"
        return (
            f"- active leads: {active_leads}\n"
            f"- hot leads (score ≥ 75): {hot}\n"
            f"- automation runs in flight: {runs_running}\n"
            f"- automation runs failed (all-time): {runs_failed}\n"
            f"- top leads by score:\n{top}"
        )
    except Exception as e:
        log.warning("live brief failed: %s", e)
        return "(stats temporarily unavailable)"


@router.post("/chat")
async def stream_chat(
    body: StreamRequest,
    demo_session: Optional[str] = Cookie(default=None),
    admin_session: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """AI-SDK data-stream chat. Yields text-delta + finish events."""

    admin = await _admin_from_cookie(admin_session, db)
    if admin:
        last_user_msg = next((m.content for m in reversed(body.messages)
                              if m.role == "user" and m.content), "")
        brief, rag = await asyncio.gather(
            _live_brief(db),
            _rag_brief(last_user_msg, str(admin.id)),
        )
        system = _ADMIN_SYSTEM_TEMPLATE.format(
            admin_name=(admin.name or admin.email).split("@")[0],
            live_brief=brief,
            rag_section=rag,
        )
    else:
        system = _DEMO_SYSTEM

    convo: list[dict] = [{"role": "system", "content": system}]
    for m in body.messages:
        if m.role in ("user", "assistant") and m.content:
            convo.append({"role": m.role, "content": m.content})

    # Pick a stable session id for persistence. Prefer the conversation_id
    # the SPA mints per chat (useLaraChat mints a UUID on mount). If absent,
    # fall back to a per-request UUID under the admin/demo namespace — never
    # the bare admin id, which would merge every chat into one bucket and
    # break the Conversations list grouping.
    session_id = body.conversation_id
    if not session_id:
        owner = f"admin:{admin.id}" if admin else (f"demo:{demo_session}" if demo_session else "anon")
        session_id = f"{owner}:{uuid.uuid4().hex[:12]}"
    last_user = next((m for m in reversed(body.messages) if m.role == "user" and m.content), None)
    if last_user:
        await _persist_async(session_id, "user", last_user.content)

    async def event_stream():
        # We emit the data-session frame after the stream finishes (when we
        # actually know the token usage). Send a placeholder up front so the
        # FE counter renders something while waiting.
        yield _sse({"type": "data-session", "data": {"tokens_remaining": None}})

        assistant_buf: list[str] = []
        usage_total = 0

        from lara_smartbiz.tools import get_tool_registry, TOOL_FUNCTIONS
        import inspect

        # Build Live API tool declarations directly from the registry. Gemini's
        # FunctionDeclaration accepts the same parameter dict shape we already
        # store (UPPER-CASE TYPE enums included), so no schema normalization is
        # needed — that was a LiteLLM-era detail.
        registry = get_tool_registry()
        function_declarations = [
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t.get("parameters") or {"type": "OBJECT", "properties": {}},
            )
            for t in registry
        ]
        live_tools = [types.Tool(function_declarations=function_declarations)]

        async def _execute_tool(name: str, args: dict) -> Any:
            fn = TOOL_FUNCTIONS.get(name)
            if not fn:
                return {"error": f"Unknown tool: {name}"}
            if inspect.iscoroutinefunction(fn):
                return await fn(**args)
            return fn(**args)

        # ── Live session ─────────────────────────────────────────────────
        # convo is OpenAI-shaped: [{role: 'system'|'user'|'assistant', content}].
        # For Live we pull the system message out into system_instruction and
        # send the rest as Content turns. The last user message will be the
        # latest turn with turn_complete=True; prior messages prime context.
        system_text = next((m["content"] for m in convo if m["role"] == "system"), "")
        non_system = [m for m in convo if m["role"] != "system"]
        history_turns = [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part.from_text(text=m["content"])],
            )
            for m in non_system if m.get("content")
        ]

        # Gemini Live's `gemini-3.1-flash-live-preview` only accepts AUDIO
        # response_modalities. To get text streamed back we set
        # output_audio_transcription — Live then emits the text alongside the
        # audio bytes, and we just drop the audio. Same pattern the agents
        # module uses in routers/agents_zero_to_prod.py (see _build_live_config).
        config = LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part.from_text(text=system_text)]) if system_text else None,
            tools=live_tools,
            speech_config=SpeechConfig(
                voice_config=VoiceConfig(
                    prebuilt_voice_config=PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            history_config=HistoryConfig(initial_history_in_client_content=True) if len(history_turns) > 1 else None,
        )

        try:
            async with get_gemini_client().aio.live.connect(model=DEFAULT_MODEL, config=config) as session:
                # Prior turns (if any) are seeded as context with
                # turn_complete=False; the latest user turn is sent via
                # send_realtime_input(text=...) which triggers the response.
                # This matches the agents_zero_to_prod pattern.
                if len(history_turns) > 1:
                    await session.send_client_content(turns=history_turns[:-1], turn_complete=False)
                if history_turns:
                    await session.send_realtime_input(text=history_turns[-1].parts[0].text)

                # Multi-turn agent loop: each pass through `async for message`
                # ends when Gemini emits turn_complete. If that turn contained
                # tool_calls we sent FunctionResponses back inline, which
                # implicitly opens a new turn — so the iterator keeps yielding.
                MAX_ITERATIONS = 5
                iterations_remaining = MAX_ITERATIONS
                tool_calls_this_turn = False

                async for message in session.receive():
                    sc = getattr(message, "server_content", None)
                    if sc:
                        # Text comes back via output_transcription (NOT model_turn
                        # since we're in AUDIO modality and discard the audio).
                        ot = getattr(sc, "output_transcription", None)
                        if ot and ot.text:
                            assistant_buf.append(ot.text)
                            yield _sse({"type": "text-delta", "delta": ot.text})
                        if getattr(sc, "turn_complete", False):
                            if not tool_calls_this_turn:
                                # Final assistant message — done.
                                break
                            tool_calls_this_turn = False
                            iterations_remaining -= 1
                            if iterations_remaining <= 0:
                                yield _sse({"type": "error",
                                            "errorText": "Reached max tool-call iterations"})
                                break
                            continue

                    tc = getattr(message, "tool_call", None)
                    if tc and getattr(tc, "function_calls", None):
                        tool_calls_this_turn = True
                        function_responses = []
                        for fc in tc.function_calls:
                            call_id = fc.id or f"call_{uuid.uuid4().hex[:8]}"
                            args = dict(fc.args or {})
                            yield _sse({
                                "type": "tool-input-start",
                                "toolCallId": call_id, "toolName": fc.name,
                            })
                            yield _sse({
                                "type": "tool-input-available",
                                "toolCallId": call_id, "toolName": fc.name, "input": args,
                            })
                            if fc.name == "search_documents":
                                args["session_id"] = session_id
                            try:
                                result = await _execute_tool(fc.name, args)
                                yield _sse({
                                    "type": "tool-output-available",
                                    "toolCallId": call_id, "toolName": fc.name, "output": result,
                                })
                            except Exception as e:
                                result = {"error": str(e)}
                                yield _sse({
                                    "type": "tool-output-error",
                                    "toolCallId": call_id, "errorText": str(e),
                                })
                            function_responses.append(types.FunctionResponse(
                                name=fc.name, id=fc.id, response={"result": result},
                            ))
                        await session.send_tool_response(function_responses=function_responses)

            yield _sse({"type": "finish"})
        except Exception as e:
            log.exception("stream_chat failed")
            yield _sse({"type": "error", "errorText": str(e)[:200]})
            yield _sse({"type": "finish"})
        finally:
            full = "".join(assistant_buf).strip()
            if full:
                await _persist_async(session_id, "assistant", full)
                # Fire-and-forget memory extraction so the SSE finish isn't
                # blocked by the (LLM-backed) fact extractor. We attach a
                # done-callback so silent task failures (embed-API down,
                # pgvector outage, schema drift) get logged — without it,
                # background extraction errors disappear into the void.
                try:
                    from lara_smartbiz.services.memory import extract_and_store_memory
                    t = asyncio.create_task(extract_and_store_memory(full, session_id))
                    def _on_done(task: asyncio.Task) -> None:
                        if task.cancelled():
                            return
                        exc = task.exception()
                        if exc is not None:
                            log.warning("memory extract task failed: %s", exc)
                    t.add_done_callback(_on_done)
                except Exception as e:
                    log.warning("memory extract scheduling failed: %s", e)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )

# M1 Lara — Research & Decisions

**Date:** 2026-04-19
**Status:** Research for team review.
**Depends on:** foundation.md (shared infra), `../2026-04-19-tech-research.md` (stack decisions)

## Summary

- Lara is the conversational layer across **all** SmartBiz modules. It's not a chatbot widget — it's a first-class interface with the same privilege as the dashboards, and it reads/writes/acts on every module via MCP tool calls.
- Brain lives in **FastAPI** as a hand-rolled tool loop. Dataclass-first domain types. Provider-agnostic client via a thin `httpx` wrapper (not LiteLLM) so we never couple to a vendor. Structured output via **msgspec** — an order of magnitude faster than Pydantic/mashumaro and better suited to our no-Pydantic policy.
- Transport to the Vite+React frontend is **SSE emitting the Vercel AI SDK v7 data-stream protocol** (UI message stream, `x-vercel-ai-ui-message-stream: v1`). `@ai-sdk/react`'s `useChat` works standalone with a non-Next backend when the backend speaks the protocol; this buys us chat-state helpers, streaming, reconnect, and tool-part rendering for free.
- Three-tier memory: working (in-request), short-term (Redis per-visitor session), long-term (Postgres + pgvector, three kinds: `fact`, `doc_chunk`, `conversation_summary`). Retrieval is exposed as a `recall` MCP tool — model decides when to fetch.
- Voice is a **deliberate sandwich**: Whisper STT → LLM → Cartesia TTS. Sonic-3 speaks Hindi natively, so MiniMax is a quality-tier fallback, not the default. Barge-in is approximate via client-side VAD + abort; we do not promise realtime duplex.
- Demo mode is enforced by a mid-stream token counter in Redis with an abort controller on the LLM stream, not `onFinish`-style post-hoc. Countdown timer is server-pushed on every SSE frame.

## Tool loop architecture

### Dataclass-first domain types

We keep all agent-internal types as stdlib `@dataclass(slots=True, frozen=True)`. Pydantic only appears on FastAPI request/response schemas. The agent loop never sees a `BaseModel`.

Core types:

- `Message` — role, content parts (text / tool_call / tool_result), timestamps.
- `ToolCall` — id, name, arguments dict, raw provider payload.
- `ToolResult` — tool_call_id, content (str or structured), `is_error: bool`.
- `ToolDefinition` — name, description, JSON schema (`dict`), async handler callable. Kept in a `ToolRegistry` keyed by namespaced name (`crm__add_lead`).
- `LLMResponse` — stop_reason, usage, text parts, tool_calls. Normalized shape regardless of provider.

Validation at provider boundaries uses **msgspec.Struct** when we need speed and `dataclasses.asdict` / a hand-written `from_dict` for internal conversions. Rationale: msgspec benchmarks ~10–80× faster than alternatives and avoids Pydantic's import-time cost ([msgspec benchmarks](https://jcristharif.com/msgspec/benchmarks.html)). `dataclasses-json` is easy but slow; `mashumaro` is fine but we don't need runtime decorators; hand-written `from_dict` stays cheap when the shape is under our control.

### Provider-agnostic client

Decision: **hand-rolled `httpx.AsyncClient` wrapper, not LiteLLM.** LiteLLM standardizes 100+ providers on an OpenAI-shaped request/response, which is useful, but it adds ~50× P99 overhead vs thin HTTP (cited benchmarks) and pulls in a large dependency for what in V0 is 2–3 providers. We write ~150 lines:

```
clients/
  base.py         # LLMClient protocol (async def complete/stream)
  anthropic.py    # Messages API; native tool-use format
  openai.py       # Responses API; native tool format
  gemini.py       # generateContent; native function calls
  registry.py     # env-driven selection; simple router
```

Each provider adapter normalizes into our internal `LLMResponse` + streaming `Chunk` types. Swap is env-var: `JARVIS_LLM=anthropic|openai|gemini`.

If a new provider lands or we want observability/fallback, we can introduce LiteLLM or OpenRouter behind the same interface later. We do **not** architect around them now.

### The loop shape

```
state.messages = [system, recall, user]
for step in range(MAX_STEPS):              # hard cap, 8 for demo, 20 authed
    stream = client.stream(state.messages, tools=registry.all())
    async for chunk in stream:
        if chunk.is_text:
            yield text delta out via SSE (AI SDK TextDelta part)
            token_counter.incr(chunk.tokens)
            if token_counter.over_cap:
                await stream.aclose()
                yield session_exhausted event
                return
        elif chunk.is_tool_call_delta:
            accumulate into partial ToolCall
    response = finalize(chunks)
    if response.stop_reason == "end_turn":
        break
    # Execute tool calls in parallel (asyncio.gather) — Anthropic + OpenAI both support
    # parallel calls unless explicitly disabled.
    results = await asyncio.gather(*[registry.call(tc) for tc in response.tool_calls])
    state.messages.append(assistant_with_tool_calls)
    state.messages.extend(tool_results)
    # loop continues — model sees results, decides to emit more text or call more tools
```

**Branching / parallel calls.** Let the model decide. Claude Sonnet/Opus and GPT-4-class models emit multiple `tool_use` blocks in one turn; we execute them concurrently via `asyncio.gather`, then feed all results back in a single user turn. This is how cross-module reasoning ("leads this week vs overdue invoices this week") works without orchestration on our side.

**Iteration cap.** 8 in demo mode, 20 authenticated. The Anthropic Python SDK's built-in runner uses 10 as default ([Anthropic tool-use docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)). Exceeding the cap yields a final text like "I've hit my reasoning budget for this turn — can you narrow the question?"

**Failure modes.**
- Tool returns empty → pass `{"result": null, "note": "no rows"}` back; model usually recovers.
- Tool raises → wrap as `ToolResult(is_error=True, content=str(exc))`; most models handle one retry before giving up.
- Tool times out (5s default, 15s for doc ingest) → cancel the task, return `is_error=True, content="timeout"`.
- Provider 5xx → one retry with exponential backoff in the httpx client, then surface as SSE `error` part.

## Streaming protocol

**Decision: emit the Vercel AI SDK v7 data-stream protocol from FastAPI.**

Why:
- `@ai-sdk/react` (`useChat`, `DefaultChatTransport`) works standalone with any backend that speaks the protocol — confirmed via context7 on `/websites/ai-sdk_dev_v7`. No Next.js required. Set `transport: new DefaultChatTransport({ api: 'https://backend/api/lara' })`.
- Backend must set header `x-vercel-ai-ui-message-stream: v1` and emit SSE frames with typed parts (`text-start`, `text-delta`, `text-end`, `tool-input-start`, `tool-input-delta`, `tool-output`, `data-*`, `finish`).
- Frontend gets for free: message list, status, reconnection, tool-part rendering, abort.

Tradeoff rejected: "define our own simpler SSE shape." Saves maybe a day of backend work, costs a week of frontend chat plumbing. Not worth it for a demo.

Implementation: either adopt [`fastapi-ai-sdk`](https://github.com/doganarif/fastapi-ai-sdk) (`AIStreamBuilder`, handles the v1 framing) or hand-roll ~200 lines of event serialization. Lean toward hand-rolled — the package is young (83 snippets on context7, low benchmark score), and we want no surprises in the hot path. Port the wire format, skip the decorator magic.

### SSE specifics

- **Transport:** SSE over HTTP/1.1. `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no` (nginx), `Connection: keep-alive`.
- **Heartbeat:** every 15s send a `: ping\n\n` comment frame to keep proxies from culling the connection. AI SDK v7's data-stream protocol already specifies keep-alive pings.
- **Reconnect:** AI SDK supports stream resume via a separate GET endpoint (`prepareReconnectToStreamRequest`); we won't build true resume for V0. If the socket drops, the frontend retries the turn. Session state in Redis is the source of truth.
- **Chunk shape:** one JSON object per `data:` line. Provider text deltas get forwarded ~immediately; tool-call deltas get buffered until the full call is assembled, then streamed as `tool-input-start` → `tool-input-delta` → `tool-input-available` → (we run the tool) → `tool-output-available`.
- **Custom data parts.** For demo-mode metadata we use `data-session` frames (`{ time_remaining, tokens_remaining }`) on every turn. `@ai-sdk/react` exposes these as typed `DataUIPart`s.

## Memory: three tiers

### Working memory (in-turn)

The `state.messages` list passed to the LLM. Not persisted beyond the request. Contains system prompt, optional recall-injected context, user turn, assistant turns with tool calls, tool results.

### Short-term memory (per visitor session)

Redis key `lara:session:{uuid}`. Hash fields:

- `turns` — JSON list of `{role, content, tokens, ts}` (last 20 trimmed FIFO).
- `tokens_used` — int counter for the 2000-token cap.
- `started_at` — epoch seconds; paired with 5-min TTL to drive countdown timer.
- `tenant_id` — null in demo, set for authed users.
- `tool_catalog_hash` — see "MCP tool discovery" below.

TTL 1 hour (covers session + grace period for reconnect). Hard session cutoff at 5 min for demo. Redis expiry is the truth.

### Long-term memory (per tenant, authed only)

Postgres table `lara_memory`:

```
tenant_id      uuid
id             uuid (pk)
kind           enum('fact','doc_chunk','conversation_summary')
content        text
embedding      vector(1536)            # depends on model, see below
source_ref     jsonb                   # {type:'doc', doc_id, page} or {type:'conv', session_id}
created_at     timestamptz
metadata       jsonb                   # free-form; e.g. doc title, chunk idx, confidence
```

Indexes: HNSW on `embedding`, btree on `(tenant_id, kind)`. Partial index on `(tenant_id, kind) where kind='fact'` for fast recall without ANN.

Three kinds:
- **`fact`** — extracted assertions ("Acme's ARR is ₹2 Cr", "Priya prefers morning demo slots"). Short, atomic. Written by the session-end summarizer.
- **`doc_chunk`** — 400-token chunks from ingested PDFs/DOCX. See "Document ingest".
- **`conversation_summary`** — one row per completed session, 2–4 sentence summary + linked facts.

### Retrieval as a tool, not blind RAG

Lara sees an MCP tool `memory__recall(query: str, kind?: str, k?: int = 5)`. The model decides when to call it. This preserves prompt caching (system prompt stays static) and avoids the RAG anti-pattern where you dump 20 irrelevant chunks into every turn and confuse the model.

We also expose `memory__remember(fact: str, source_ref?: dict)` so the model can explicitly commit a fact mid-conversation ("got it, I'll remember Priya prefers morning slots").

### Embeddings model

Pick: **OpenAI `text-embedding-3-small`** for V0.

- $0.02 / 1M tokens — effectively free at demo volume ([pricing comparison](https://elephas.app/blog/best-embedding-models)).
- 1536 dims — pgvector HNSW handles fine.
- MTEB quality is strong enough for our sparse corpus.
- No infra to host.

Runners-up noted:
- **Voyage 4 Lite** ($0.02/1M) if we want ~14% NDCG@10 lift over OpenAI, but adds a second vendor.
- **Sentence-transformers (bge-small or similar)** on our worker box — zero marginal cost, but adds GPU/CPU overhead and a model cache. Worth revisiting post-V0 if cost scales.

### Write path

At session end (or hourly background sweep for long sessions):
1. Summarizer job runs on a cheap model (Haiku / gpt-4o-mini / Gemini Flash) with the full transcript.
2. Produces `{summary: str, facts: [{content, source_ref}]}` via msgspec-validated JSON.
3. Embed summary + each fact; upsert with `tenant_id`, `kind`, `source_ref={type:'conv', session_id}`.
4. Demo sessions (no tenant) are **not** written to long-term memory. Demo is ephemeral by design.

Background runner: `asyncio.create_task` on session end for V0. Move to ARQ / Inngest once we see queue backpressure.

## Voice pipeline

### Flow

```
Browser mic  →  PCM frames (16kHz mono)  →  WebSocket /voice/stream
                                              │
                                              ▼
                        FastAPI voice endpoint
                         │     │     │
                         ▼     ▼     ▼
                       VAD   Whisper   (on VAD-end: commit partial → final)
                                  │
                                  ▼
                           Lara tool loop (same as text path, streaming)
                                  │
                                  ▼
                           Text deltas
                                  │
                                  ▼
                   Cartesia Sonic-3 (or MiniMax) — SSE stream
                                  │
                                  ▼
                           PCM frames back  →  <audio> element
```

### Components

- **STT:** `faster-whisper` (CTranslate2) on the worker box. ~120ms partials, RTF ~0.2 with INT8 quantization ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)). Streaming transcription via WebSocket, finalize on VAD-end.
- **VAD:** Silero VAD in the browser (preferred, keeps server idle) or server-side if client-side proves flaky. VAD-end triggers STT finalize and kicks off the LLM turn.
- **TTS:** Cartesia Sonic-3 — 40ms TTFB, streaming chunks, 42 languages, WebSocket multiplexing ([Cartesia Sonic-3](https://cartesia.ai/sonic)). We feed LLM text deltas (buffered to sentence boundaries) as they arrive, so TTS starts before generation completes.

### Hindi routing

Cartesia Sonic-3 **supports Hindi natively** per Cartesia's language list. This changes the prior assumption that MiniMax is required for Hindi.

Routing strategy:
- **Default:** Cartesia for everything, language auto-inferred from the response text or set via a UI toggle. No `Accept-Language` complexity.
- **Fallback:** MiniMax Speech 2.8 HD **only** if A/B testing shows Cartesia Hindi quality is below bar. MiniMax is a separate vendor, separate API, separate billing — bring it in only if needed.
- **Language detection:** cheap — check if any Devanagari codepoints appear in the LLM output, else Latin. That's 99% accurate for our use.

UI: a language pill on the voice widget (EN / HI) that seeds the system prompt and picks the voice. Auto-detect overrides if user visibly switches.

### Latency budget

```
VAD end               ~50ms
STT finalize          ~200ms (faster-whisper INT8)
LLM first token       ~600–1000ms (Sonnet) / ~300–500ms (Haiku, demo)
TTS first audio       ~40ms (Sonic-3)
                    ────────
Felt latency        ~1.0–1.3s
```

Acceptable for V0. Under 1.5s is conversational; users tolerate up to ~2s if the response is good. Do **not** promise sub-500ms.

### Barge-in (honest)

True duplex is out. Our sandwich pipeline can't pause TTS mid-syllable based on fresh user audio without a realtime framework (Pipecat, LiveKit, Deepgram Flux).

What we do instead:
- Browser VAD runs during TTS playback. If VAD fires with >300ms of speech, the client:
  1. Stops the `<audio>` element.
  2. Sends an abort signal over the voice WebSocket.
  3. Backend cancels the in-flight LLM stream, cancels pending Cartesia requests, starts a fresh STT pass.
- Cost: ~300–500ms between "user starts speaking" and "Lara stops talking." Good enough to not feel broken.

Known failure: echo (Lara's own audio re-entering the mic). Require headphones or add a software echo-cancellation pass (browser `echoCancellation: true` is usually enough).

## Document ingest

### Flow

```
User drops file in chat UI
   │
   ▼
POST /docs/upload → stored in S3-compat (Backblaze B2 / R2 for V0, not Vercel Blob — backend lives off-Vercel)
   │
   ▼
docs-worker (FastMCP server, async job queue via ARQ)
   │
   ├── PyMuPDF page-scan → if any page has <0.5× expected-density native text → mark for OCR
   │       (PyMuPDF4LLM hybrid-OCR strategy: auto-OCR pages with no selectable text;
   │        readability threshold 0.9)
   │
   ├── If >X% of pages need OCR → route to Nanonets OCR (free tier: 500 pages/mo)
   │       Otherwise use PyMuPDF's own OCR plugin via Tesseract for simple cases
   │
   ├── Chunk: recursive-character splitter, 400 tokens, 60-token overlap
   │       (Chroma research: recursive at 400 tokens = 85–90% recall, semantic ~91% at 5–10× cost.
   │        Not worth the complexity for V0.)
   │
   ├── Embed each chunk (OpenAI 3-small)
   │
   └── Insert into lara_memory (kind='doc_chunk', source_ref={doc_id, page_range, chunk_idx})
```

### Quality detection

PyMuPDF4LLM already does this: if a page has no selectable text or fails the readability threshold (0.9), it triggers OCR. We trust its classifier for the first pass. If the per-page mark-for-OCR count exceeds 5, we escalate the whole document to Nanonets (OCR quality > speed on scanned docs).

### Chunking

**Decision: recursive-character, 400 tokens, 60 overlap.**

- Simple, cheap, well-understood.
- Semantic chunking buys 2–3% recall at 5–10× compute (Chroma, Weaviate benchmarks, [Firecrawl's 2026 guide](https://www.firecrawl.dev/blog/best-chunking-strategies-rag)).
- Revisit post-V0 if recall is visibly lacking in the demo.

For invoices / structured docs (M7), we may add a separate pipeline that extracts fields directly into structured rows, not chunks. Out of M1 scope.

### Storage

- **Raw files:** S3-compatible bucket on the worker box's provider (Backblaze B2 or Cloudflare R2 — both cheap, both S3 API). Vercel Blob is Vercel-coupled and we've committed to a hybrid deploy, so don't concentrate storage there.
- **Chunks + embeddings:** pgvector in Postgres.
- **Extracted text (cache):** Postgres `documents` table, `text` column. Skip reprocessing on re-ingest.

### Nanonets rationing

500 free pages / month. At ~30¢/page paid, rationing matters.

- **Budget:** default 400 pages/month allocated to demo and authed traffic combined. 100-page buffer.
- **Prioritize:** authed tenants first, demo second.
- **Circuit breaker:** Redis counter `nanonets:pages_used:YYYY-MM`. If >400, fall back to Tesseract-only (worse quality, free) and flag the doc as "degraded OCR."
- **Preemptive triage:** any doc over 50 pages requires tenant login. No one burns half the monthly budget on a demo.

## MCP tool discovery

### Handshake

At session start (first request to `/api/lara-smartbiz/session`):

1. Backend calls `tools/list` on the MCP gateway over Streamable HTTP.
2. Gateway fans out to registered module servers (CRM, automation, reports, docs, scrapers, memory, fintech, third-party: HubSpot/Sheets/etc).
3. Gateway returns namespaced catalog: `crm__add_lead`, `docs__search`, `memory__recall`, etc.
4. Backend stores the catalog JSON in Redis under `lara:session:{uuid}.tool_catalog` and a `tool_catalog_hash` alongside.
5. LLM system prompt is built with full catalog and marked `cache_control: ephemeral` (Anthropic) or equivalent caching hint.

### Static for the session

**Critical constraint:** Anthropic's prompt cache hierarchy is `tools → system → messages` ([Anthropic prompt caching](https://docs.claude.com/en/docs/build-with-claude/prompt-caching)). Any change at the tool level invalidates everything downstream. A hot-added tool mid-session → cache miss → ~10× cost spike on the next turn.

Rules:
- Tool catalog is **frozen for the life of the session**. Period.
- Module hot-adds are visible only on the next session.
- If a module goes offline mid-session, we mark its tools as "temporarily unavailable" in the gateway response (tool still exists, call returns error) rather than dropping it from the catalog. Cache-preserving.

### Module additions

Choice: **accept cache miss on next session; never invalidate mid-session.** Document it in the gateway README.

If a session absolutely needs a new tool, we end the session and ask the user to refresh. Demo-mode 5-min caps mean this almost never matters.

### Gateway topology

```
FastAPI /api/lara-smartbiz  ──►  FastAPI MCP Gateway (in-process module, not a separate service for V0)
                            │
                            ├── FastMCP: crm (in-process)
                            ├── FastMCP: automation (in-process)
                            ├── FastMCP: reports (in-process)
                            ├── FastMCP: memory (in-process)
                            ├── FastMCP: docs (HTTP → docs-worker, off-Vercel)
                            ├── FastMCP: scrape (HTTP → docs-worker)
                            └── Third-party MCP servers (HubSpot, Sheets, Inngest)
```

Gateway is ~200 lines: auth check, tenant → allow-list filter, name-prefix namespacing, fan-out on `tools/list`, pass-through on `tools/call`.

## Demo guardrails

### Token counter

Lives in Redis `lara:session:{uuid}.tokens_used`. Two writes per turn:
1. On every text-delta chunk, increment by the chunk's token count (estimated via tiktoken; exact numbers come from provider `usage` at stream end and we reconcile).
2. On turn end, reconcile with provider-reported `usage.output_tokens`.

Cap: 2000 tokens per session. When the counter crosses it mid-stream:

1. Call `stream.aclose()` on the httpx stream (abort the upstream provider connection).
2. Emit an SSE `data-session` frame with `status='exhausted'`.
3. Emit AI SDK `finish` part with `finishReason='length'`.
4. Write `exhausted=true` in the Redis session.
5. Frontend swaps chat input for a "Book a call" CTA.

### Time counter

Computed from `started_at` in Redis. On every turn response (and every heartbeat frame), emit `data-session: { time_remaining_sec }`. Frontend shows countdown.

At 5-min expiry, Redis TTL lapses. Next request fails auth check, backend returns 410 Gone + CTA payload.

### Rate limit

1 session per IP per hour. Nginx / Cloudflare rule or FastAPI middleware backed by Redis sliding window. Key: `ratelimit:ip:{hash}`, TTL 3600.

### End-of-session flow

SSE event `data-cta: { type: 'book_call', url: '...' }`. Frontend renders a large CTA card in the chat stream. Session is done.

### Cost per session

Target ₹2–8. With Haiku 4.5 at demo-time input ~$1/M and output ~$5/M tokens, cap 2000 tokens output = ~$0.01 = ₹0.85. Plus input for full catalog (~3–5k tokens first turn, cached after) ≈ ₹0.50–₹1. Plus TTS (Cartesia at ~$65/1M chars, 2000 tokens ≈ 8k chars = ~$0.52 = ₹45 uncapped — this is the real cost driver). **TTS is the binding cost constraint, not LLM.** Budget voice as opt-in on the demo, not default.

## Cross-module reasoning

### Pattern

"Which leads came in the same week we had the most overdue invoices?"

Model thinks:
1. Need lead-count-by-week. Call `crm__list_leads_by_week`.
2. Need overdue-invoice-count-by-week. Call `fintech__overdue_invoices_by_week`.
3. Correlate in its own reasoning (or ask for a join tool if we provide one).
4. Answer.

Both tool calls emit in one turn. Our loop executes them with `asyncio.gather`. Both results feed into the next LLM turn. Model writes the answer.

Key insight: the model orchestrates. We don't plan. `stop_reason='end_turn'` tells us we're done; `stop_reason='tool_use'` tells us to keep going. Hard cap of 8 iterations is the backstop.

### Failure modes

- **Tool returns nothing:** `{"rows": [], "count": 0}`. Model typically says "no overdue invoices in the last 4 weeks" gracefully.
- **Tool errors:** `ToolResult(is_error=True, content="db timeout")`. Model usually retries once then apologizes. We log and alert.
- **Tool timeout (5s default):** same as error. We surface a `data-tool-timeout` custom part for dashboard to highlight slow tools.
- **Infinite loop (model keeps calling the same tool with the same args):** detect via simple arg-hash dedup over last 3 calls; inject a synthetic `ToolResult(is_error=True, content="already tried — try something else")`.
- **Catastrophic model loop:** MAX_STEPS cap; return partial answer with a note.

## Open questions

1. **LLM provider for demo mode.** Claude Haiku 4.5 vs GPT-4o-mini vs Gemini Flash. Decide based on: (a) tool-use quality at that tier, (b) cost, (c) Hindi fluency for mixed voice sessions. Run a 50-prompt bake-off in Foundation week.
2. **FastMCP + dataclass tool schemas.** FastMCP may expect Pydantic for tool input schemas. If so, we isolate Pydantic at the registration boundary only and keep the loop pure-dataclass. Verify.
3. **Hindi voice quality.** Blind A/B Cartesia Hindi vs MiniMax with 5 sample phrases before committing. If Cartesia passes, drop MiniMax from V0 entirely.
4. **Memory summarizer cadence.** End-of-session vs hourly sweep vs token-threshold. Cheapest is end-of-session; sweep catches long authed sessions.
5. **Reranking.** Voyage rerank-2 on top of retrieved chunks? Probably post-V0. Note and defer.
6. **Should `memory__remember` be allowed in demo mode?** Currently no (ephemeral). Could be a demo moment though ("watch me remember this") if we scope writes to the session-only tier.
7. **AI SDK v6 vs v7.** Confirm the React frontend targets v7 (which is what current context7 docs reflect). v6 uses a different wire protocol.

## Gotchas

1. **TTS is the real cost driver, not LLM.** Voice demos cost ~50× text demos. Make voice opt-in with a clear label ("voice uses extra credits").
2. **Tool catalog changes bust Anthropic cache.** Load full catalog at session start, keep it frozen, never hot-add. Any module that comes online mid-session is invisible until next session.
3. **MCP stdio transport doesn't work over HTTP.** All module servers must be Streamable HTTP. FastMCP supports both; enforce HTTP in config.
4. **Pre-emptive token cutoff must watch deltas.** Counting in `on_finish` or after streaming completes means the user sees the full over-cap response before the cutoff. Abort the httpx stream mid-delta.
5. **SSE through reverse proxies buffers by default.** Set `X-Accel-Buffering: no` and disable nginx proxy_buffering for the lara endpoints.
6. **msgspec + JSON schema.** msgspec.Struct types generate JSON schemas via `msgspec.json.schema`; perfect for tool input validation. Verify this covers all the shapes we need before committing.
7. **Voice barge-in without duplex is imperfect.** Set expectation: 300–500ms cut-off latency, not instant. Don't pitch "interrupt anytime" as a headline feature.
8. **Browser `<audio>` + streamed PCM.** Stitch Cartesia's chunks via MediaSource Extensions or Web Audio API; don't naively feed base64 into `<audio src=>` (breaks chunking). Reference implementations exist in the Cartesia SDK docs.

## Sources

- [Vercel AI SDK v7 — Stream Protocol](https://ai-sdk.dev/v7/docs/ai-sdk-ui/stream-protocol)
- [Vercel AI SDK v7 — DefaultChatTransport & resume](https://ai-sdk.dev/v7/docs/ai-sdk-ui/chatbot-resume-streams)
- [AI SDK UI: Stream Protocols (public)](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol)
- [fastapi-ai-sdk (Python emitter for AI SDK data-stream)](https://github.com/doganarif/fastapi-ai-sdk)
- [FastMCP — transports, streamable HTTP](https://gofastmcp.com/)
- [Anthropic — Prompt caching](https://docs.claude.com/en/docs/build-with-claude/prompt-caching)
- [Anthropic — Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [Anthropic — Advanced (programmatic) tool use](https://www.anthropic.com/engineering/advanced-tool-use)
- [msgspec benchmarks](https://jcristharif.com/msgspec/benchmarks.html)
- [LiteLLM overview and perf caveats](https://github.com/BerriAI/litellm)
- [Cartesia Sonic-3 TTS](https://cartesia.ai/sonic)
- [Cartesia language support (incl. Hindi)](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest)
- [MiniMax Speech 2.8 Turbo vs HD (2026)](https://aimlapi.com/blog/minimax-speech-2-8-turbo-vs-hd-the-ultimate-2026-tts-showdown)
- [faster-whisper (CTranslate2)](https://github.com/SYSTRAN/faster-whisper)
- [WhisperFlow — streaming STT](https://itnext.io/whisperflow-a-real-time-speech-to-text-library-274279d98cba)
- [LiveKit — sequential pipeline architecture for voice agents](https://livekit.com/blog/sequential-pipeline-architecture-voice-agents)
- [Deepgram Flux — conversational STT](https://deepgram.com/learn/introducing-flux-conversational-speech-recognition)
- [PyMuPDF4LLM — hybrid OCR and quality detection](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)
- [Nanonets pricing / free tier](https://nanonets.com/pricing)
- [Firecrawl — best RAG chunking strategies 2026](https://www.firecrawl.dev/blog/best-chunking-strategies-rag)
- [Extend — semantic chunking best practices (Mar 2026)](https://www.extend.ai/resources/semantic-chunking-methods-5-best-practices-rag-results)
- [Embedding model comparison 2026 (Voyage / OpenAI / Cohere)](https://elephas.app/blog/best-embedding-models)
- [Model Context Protocol — 2026 roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)
- [MCP specification (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25)

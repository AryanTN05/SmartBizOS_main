# M1 Lara — API Contracts

**Date:** 2026-04-19
**Status:** Draft for team review.
**Depends on:** `docs/specs/api-contracts/foundation.md` (conventions, auth, error shapes).
**Research:** `docs/research/modules/m1-lara.md`.

Lara is the demo's **headline surface** — most of the wow happens here. It's the only module that streams, handles audio, and speaks the Vercel AI SDK data-stream protocol so `@ai-sdk/react`'s `useChat` works for free. The contracts below are the widest in the app.

---

## Scope

**In this module:**
- Streaming chat endpoint (SSE, AI SDK data-stream protocol v1).
- Conversation list + load + rename + delete (backend persistence of chat history).
- Document upload + list + delete (corpus Lara can answer from).
- Text-to-speech endpoint (for voice mode — Cartesia / MiniMax).
- Admin memory browser (read + delete long-term memory entries).

**Out of scope (handled elsewhere):**
- Tool implementations themselves — each tool lives in its module's MCP server (`crm__add_lead` in M2, `reports__get_latest` in M6, etc.). M1 only *orchestrates* the tools.
- Speech-to-text: handled **client-side via the browser Web Speech API**. No backend STT endpoint in V0. Reduces latency, keeps audio off our servers, zero backend cost.
- Memory writes: automatic after session close via an Inngest background job. No public endpoint.

---

## Pages

| Page | Route (frontend) | Purpose |
|---|---|---|
| Lara chat | `/lara` | Full-page chat. The landing-page "Start chatting with Lara" lands here. Works for demo + admin |
| Lara dock | (any `/admin/*` page) | Slide-out chat panel inside the admin shell. Same endpoints, narrower UI |
| Conversations | `/admin/conversations` | Admin-only. List past conversations (demo + admin) with filters and search |
| Conversation detail | `/admin/conversations/:id` | Read-only transcript view with tool calls expanded |
| Documents | `/admin/documents` | Admin-only. Corpus manager — upload, view extraction status, delete |
| Memory browser | `/admin/memory` | Admin-only. Browse extracted facts / doc chunks / conversation summaries. Delete bad entries |

---

## Per-page needs & actions

### Lara chat (`/lara`)

**On load:**
- `GET /api/session/me` (from Foundation) — if demo, render countdown timer. If admin, load conversation sidebar.
- `GET /api/config` — read `voice_enabled` flag to decide whether to show the mic button.
- For admins: `GET /api/conversations?limit=20` — left-rail conversation list.

**Actions:**
- Send message → `POST /api/stream/chat` (SSE).
- Stop generation → close the `EventSource`; backend detects via `request.is_disconnected()`.
- New conversation (admin) → simply send next message without a `conversation_id`; backend creates one.
- Upload file → `POST /api/documents/upload`; file becomes available to Lara immediately as a new MCP tool-surface entry (`docs__search` picks it up).
- Play audio response → triggers `POST /api/tts` with the assistant's text.

### Lara dock (inside `/admin/*`)
Same endpoints as the chat page; the dock just renders narrower.

### Conversations (`/admin/conversations`)

**On load:**
- `GET /api/conversations?limit=50&cursor=...` — paginated.

**Actions:**
- Rename → `PATCH /api/conversations/:id`.
- Delete → `DELETE /api/conversations/:id`.
- Open detail → navigate to `/admin/conversations/:id`.

### Conversation detail (`/admin/conversations/:id`)

**On load:**
- `GET /api/conversations/:id` — full transcript with tool calls.

No actions beyond navigation and delete.

### Documents (`/admin/documents`)

**On load:**
- `GET /api/documents?limit=50&cursor=...`.

**Actions:**
- Upload → `POST /api/documents/upload` (multipart). Extraction is async; returned `extraction_status` starts as `pending`. Page polls `GET /api/documents/:id` every 2s until `ready` or `failed`.
- Delete → `DELETE /api/documents/:id`.

### Memory browser (`/admin/memory`)

**On load:**
- `GET /api/admin/memory?kind=fact|doc_chunk|conversation_summary&cursor=...`.

**Actions:**
- Delete entry → `DELETE /api/admin/memory/:id`. Useful for removing hallucinated facts or outdated info.

---

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/stream/chat` | demo or admin | SSE streaming chat (AI SDK data-stream protocol v1) |
| `GET` | `/api/conversations` | demo (own) or admin (all) | List conversations |
| `GET` | `/api/conversations/{id}` | demo (own) or admin | Load full conversation |
| `PATCH` | `/api/conversations/{id}` | admin | Rename |
| `DELETE` | `/api/conversations/{id}` | admin | Delete |
| `POST` | `/api/documents/upload` | demo or admin | Upload a document (multipart) |
| `GET` | `/api/documents` | admin | List corpus |
| `GET` | `/api/documents/{id}` | admin | Document detail + extraction status |
| `DELETE` | `/api/documents/{id}` | admin | Delete document |
| `POST` | `/api/tts` | demo or admin | Text → audio stream (returns audio bytes) |
| `GET` | `/api/admin/memory` | admin | List memory entries |
| `DELETE` | `/api/admin/memory/{id}` | admin | Delete a memory entry |

Twelve endpoints. Matches the research memo's 8–10 estimate (the extras are conversation CRUD + memory browser).

---

## Contracts

### Shared types

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class Message:
    id: str                       # UUID, server-assigned on first persist
    role: str                     # "user" | "assistant" | "tool"
    content: str                  # text content (may be empty if pure tool-call)
    tool_calls: list["ToolCall"] = field(default_factory=list)
    created_at_unix: int = 0

@dataclass
class ToolCall:
    id: str                       # provider-assigned call id
    name: str                     # namespaced, e.g. "crm__add_lead"
    args: dict                    # JSON-shaped args — opaque here; module contracts define per-tool shape
    result: dict | None = None    # populated once the tool returns; None while in-flight
    error: str | None = None      # populated on failure

@dataclass
class Conversation:
    id: str                       # UUID
    title: str                    # auto-generated from first user message; admin can PATCH
    created_at_unix: int
    updated_at_unix: int
    message_count: int
    kind: str                     # "demo" | "admin" — source of the session
    demo_session_id: str | None   # populated when kind=="demo"
    admin_user_id: str | None     # populated when kind=="admin"

@dataclass
class Document:
    id: str                       # UUID
    filename: str                 # original upload name
    mime_type: str                # "application/pdf" | "text/plain" | ...
    size_bytes: int
    uploaded_at_unix: int
    uploaded_by_kind: str         # "demo" | "admin"
    uploaded_by_id: str           # demo session UUID or admin user UUID
    extraction_status: str        # "pending" | "ready" | "failed"
    extraction_error: str | None
    page_count: int | None        # populated once extraction finishes
    text_preview: str | None      # first ~500 chars; populated when ready
    chunk_count: int | None       # how many pgvector rows this doc produced

@dataclass
class MemoryEntry:
    id: str                       # UUID
    kind: str                     # "fact" | "doc_chunk" | "conversation_summary"
    content: str                  # the stored text
    source_ref: str | None        # e.g., "conversation:{id}" or "document:{id}:chunk:{n}"
    created_at_unix: int
    used_count: int               # how many times `memory__recall` returned this — useful for pruning
```

### POST `/api/stream/chat`

The headline endpoint. This is the one that must feel magical.

**Request:**
```python
@dataclass
class ChatRequest:
    messages: list[Message]           # full conversation history client-side state
    conversation_id: str | None       # None = create new on first persistable message
    options: ChatOptions = field(default_factory=lambda: ChatOptions())

@dataclass
class ChatOptions:
    voice_mode: bool = False          # frontend hint; affects response brevity + post-hoc TTS flow
    language: str = "en"              # "en" | "hi" — routes to MiniMax for Hindi voice later
    model_hint: str | None = None     # admin-only: override the routed model. Demo always uses the configured demo model.
```

**Auth:** demo or admin. Demo cookie's token/time budget is enforced inside the stream.

**Response:** **SSE** (`Content-Type: text/event-stream`). Wire format follows the **Vercel AI SDK data-stream protocol v1**; we emit the header `x-vercel-ai-ui-message-stream: v1` so `@ai-sdk/react`'s `useChat` + `DefaultChatTransport` parses it natively.

#### Event wire format

Each SSE `data:` line is a JSON object. Event types we emit:

| Type | When | Shape |
|---|---|---|
| `text-delta` | Assistant text chunk | `{"type":"text-delta","id":"<msg_id>","delta":"<text>"}` |
| `tool-input-start` | Model decided to call a tool | `{"type":"tool-input-start","toolCallId":"<id>","toolName":"crm__add_lead"}` |
| `tool-input-delta` | Streaming tool args | `{"type":"tool-input-delta","toolCallId":"<id>","inputTextDelta":"<json fragment>"}` |
| `tool-input-available` | Args fully parsed | `{"type":"tool-input-available","toolCallId":"<id>","toolName":"...","input":{...}}` |
| `tool-output-available` | Tool returned | `{"type":"tool-output-available","toolCallId":"<id>","output":{...}}` |
| `tool-output-error` | Tool failed | `{"type":"tool-output-error","toolCallId":"<id>","errorText":"..."}` |
| `data-session` | Demo-mode heartbeat | `{"type":"data-session","data":{"seconds_remaining":..., "tokens_remaining":...}}` |
| `data-cutoff` | Demo session about to end mid-stream | `{"type":"data-cutoff","data":{"reason":"demo_expired" \| "demo_tokens_exhausted"}}` |
| `finish` | Turn complete | `{"type":"finish","finishReason":"stop" \| "tool-calls" \| "length" \| "error","usage":{"promptTokens":...,"completionTokens":...}}` |
| `error` | Unrecoverable | `{"type":"error","errorText":"..."}` |

**`data-*` events are our extension** — the AI SDK v7 protocol reserves the `data-` prefix for client-custom payloads, exactly for things like session-state heartbeats. Frontend handles via `useChat`'s `onData` callback.

**Behavior highlights:**
- On first persistable message of a new chat (no `conversation_id`): server assigns a UUID, emits it as part of the first `finish` event's `usage` metadata so the client can tag the conversation.
- **Pre-emptive token cap.** The stream wrapper counts completion tokens as deltas arrive. Two checks per delta: (a) is the session's `tokens_used + this_delta > 2000`? (b) is the wall-clock past `expires_at`? On either, emit `data-cutoff`, emit `finish { finishReason: "error" }`, close the stream, and HINCRBY the used counter to exactly the cap.
- **Tool calls run in-process.** Lara's agent loop makes tool calls via the MCP gateway; the gateway routes to module servers; results stream back through `tool-output-available`. If a tool takes > 30s, the stream emits a `data-heartbeat` every 10s (reuses the `data-session` channel) so proxies don't kill the connection.
- **Tool catalog is frozen per session** (see research memo — Anthropic prompt caching requires this). The catalog is fetched once from the MCP gateway at turn 1 and cached in Redis for the session's lifetime. Module additions are visible only on the next session.
- **Cross-module reasoning** is handled by the agent loop — multiple tool calls per turn are possible, looped until the model returns plain text or hits the loop cap (8 iterations for demo, 20 for admin).

**Errors (not emitted as `error` events, but HTTP errors before stream starts):**
- `401 unauthenticated` — neither demo nor admin session valid.
- `402 demo_expired` / `demo_tokens_exhausted` — if the session was already exhausted **before** the request started. Mid-stream exhaustion uses `data-cutoff`.
- `422 validation_failed` — malformed `messages`.

### GET `/api/conversations`

**Request:** query params:
- `cursor: str | None`
- `limit: int = 25`
- `kind: str | None` — admin filter: `"demo" | "admin"`. Demo sessions only see their own, kind filter ignored.

**Response 200:**
```python
@dataclass
class ConversationListResponse:
    items: list[Conversation]
    next_cursor: str | None
```

**Auth & scoping:**
- Demo: returns only conversations with `demo_session_id == request.session_id`.
- Admin: returns all, filterable by `kind`.

### GET `/api/conversations/{id}`

**Response 200:**
```python
@dataclass
class ConversationDetailResponse:
    conversation: Conversation
    messages: list[Message]       # ordered oldest-first
```

**Errors:** `404 not_found` if id doesn't exist or caller lacks access (demo viewing someone else's conversation).

### PATCH `/api/conversations/{id}`

**Request:**
```python
@dataclass
class ConversationUpdateRequest:
    title: str
```
**Auth:** admin only.
**Response 200:** `Conversation` (updated).

### DELETE `/api/conversations/{id}`

**Auth:** admin only.
**Response 204.**

Deleting cascades to `messages` table. Memory entries with `source_ref = "conversation:{id}:*"` are NOT deleted automatically — the admin can prune those via the memory browser. This preserves extracted facts even if the underlying conversation is cleared.

### POST `/api/documents/upload`

**Request:** multipart/form-data
- `file: File` (required)
- `tags: str | None` — comma-separated tags for corpus organization

**Response 201:**
```python
@dataclass
class DocumentUploadResponse:
    document: Document
```

**Behavior:**
- Stores file in Cloudflare R2 under `documents/{tenant_id}/{doc_id}.{ext}`.
- Enqueues an Inngest event `document.uploaded { document_id }` which triggers extraction + chunking + embedding as a background job.
- Returns immediately with `extraction_status == "pending"`. Frontend polls `GET /api/documents/:id`.

**Limits:**
- Max file size: 20 MB. Returns `413 payload_too_large` (add to error enum) above this.
- Allowed mime types for V0: PDF, DOCX, TXT, MD. Returns `422 validation_failed` on others.
- **Demo users:** one document per session. Returns `402 demo_expired` with `details.reason = "doc_limit"` after that.

### GET `/api/documents`

**Request:** query params as `PageRequest` + optional `status: "pending" | "ready" | "failed"` filter.
**Auth:** admin only.
**Response 200:** `Page[Document]`.

### GET `/api/documents/{id}`

**Auth:** admin, or demo that uploaded this doc in the current session.
**Response 200:** `Document`.

### DELETE `/api/documents/{id}`

**Auth:** admin only.
**Response 204.**

Cascades: R2 object deleted, pgvector rows (`lara_memory` where `kind == "doc_chunk"` and `source_ref LIKE 'document:{id}:%'`) deleted, document row deleted. All in one transaction.

### POST `/api/tts`

**Request:**
```python
@dataclass
class TTSRequest:
    text: str                     # max 2000 chars per request (split longer responses client-side)
    voice: str = "default"        # "default" | "hindi" | "neutral" — maps to Cartesia voice or MiniMax
    format: str = "mp3"           # "mp3" | "ogg"
```

**Auth:** demo (rate-limited) or admin.

**Response 200:** raw audio bytes, `Content-Type: audio/mpeg` or `audio/ogg`. Streamed chunk-by-chunk as Cartesia/MiniMax returns them.

**Rate limits (demo):**
- Max 10 TTS calls per demo session (enforced via `demo:session:{uuid}:tts_count`).
- Exceeding returns `429 rate_limited`.

**Why this is a separate endpoint and not part of the chat stream:** keeps the chat stream a pure text-stream (all AI SDK protocol events). Voice is opt-in per message, frontend calls this after the chat stream finishes. Also: TTS is ~50× more expensive per token than LLM text (from the research memo) — keeping it opt-in prevents runaway demo cost.

### GET `/api/admin/memory`

**Request:** query params:
- `cursor: str | None`
- `limit: int = 25`
- `kind: str | None` — `"fact" | "doc_chunk" | "conversation_summary"`
- `search: str | None` — if provided, does a pgvector similarity search over `content` (top-`limit` results, ordered by distance)

**Auth:** admin only.
**Response 200:** `Page[MemoryEntry]`.

### DELETE `/api/admin/memory/{id}`

**Auth:** admin only.
**Response 204.**

Hard delete — no soft-delete in V0. Memory is regenerable from source (conversations and documents still exist), so losing an entry isn't catastrophic.

---

## Open questions

1. **STT provider.** V0 plan is browser Web Speech API (client-side, free, no backend endpoint). Works in Chrome/Edge but not Firefox/Safari without user opt-in. If the demo audience is mixed-browser, we may need a `/api/stt` endpoint wrapping Whisper. Decide before M1 build.
2. **Message persistence trigger.** Currently: persist on `finish` event. If a message errors mid-stream, do we persist the partial? Proposal: yes, with `tool_calls[].error` filled — the admin audit trail wants to see failures.
3. **Conversation title auto-generation.** From the first user message (truncated to 60 chars) or from a Haiku-class summarization call? Proposal: truncate for V0 (zero latency, zero cost); summarize only when admin explicitly renames to "auto".
4. **Doc-upload demo quota.** 1 doc/session seems right for cost control, but it kills the "upload two contracts and compare" demo moment. Consider raising to 3 with a per-file size cap of 5 MB.
5. **Memory delete cascade behavior.** When an admin deletes a conversation, we *keep* its extracted facts. But we don't keep its `conversation_summary` memory entry — or do we? Proposal: keep the summary, drop the `source_ref`. Team call.
6. **Tool-call timeout display.** If `crm__add_lead` takes 45s (rare, but an integration could hang), the UI shows nothing but heartbeats for that time. Do we surface a "tool running..." indicator with the tool name, or stay quiet? Proposal: show it, name is non-PII (`crm__add_lead`).
7. **Voice mode end-of-utterance detection.** Client-side VAD (voice activity detection) triggers "send" automatically. Tunability (how long of silence counts as "done") matters for UX. V0: hardcode 800ms; make admin-configurable in V1.

---

## Gotchas

1. **SSE disconnect detection.** FastAPI's `StreamingResponse` doesn't notice a closed TCP connection until the next `yield`. Add `await request.is_disconnected()` checks on every delta or the agent loop keeps burning tokens after the user navigates away. Quote from Foundation gotchas — it applies doubly here.
2. **AI SDK protocol version.** `@ai-sdk/react` is on v7 as of early 2026; the data-stream protocol is v1 but could bump. Pin the frontend to a specific AI SDK version and fail loud in CI on mismatch.
3. **Tool catalog freeze is not optional.** If the catalog changes mid-session, Anthropic's prompt cache (tools are in the cache prefix) invalidates and cost per turn jumps ~10×. The catalog is loaded once at session creation and frozen — any hot-reload of MCP servers requires a new session.
4. **Pre-emptive token cap is *async*.** The counter increment happens after the delta arrives. Race condition: a large delta could push us past the cap before the check runs. Use `asyncio.Lock` around the increment/check pair. Test with a prompt-injection "write a 5000-word essay" input.
5. **`data-*` event `type` must not collide with reserved AI SDK types.** Stick to the `data-` prefix (`data-session`, `data-cutoff`, `data-heartbeat`). Never emit `data` alone — that's reserved.
6. **Multipart uploads bypass JSON middleware.** FastAPI body parsing differs; the demo-session middleware must still run (cookie check + rate limit). Register the middleware at the ASGI level, not in a JSON-only hook.
7. **Audio streaming + Cloud Run.** Cloud Run's streaming limit is 60 minutes per request; a 2000-char TTS call completes in seconds. No issue in practice, but if we ever generate very long audio, split client-side.
8. **Demo conversation visibility leak.** A demo user whose session UUID is somehow leaked could `GET /api/conversations/:id` on another demo's conversation. The auth check must compare *cookie UUID* to stored `demo_session_id` — never accept a UUID passed in the path as authoritative. Easy to get wrong, easy to test.
9. **`tool-input-delta` is streamed JSON fragments, not valid JSON.** The client accumulates them into a final JSON string at `tool-input-available`. Don't try to parse intermediate fragments — they're partial.

---

## Next contracts to write

- **M2 Sales Intel** — leads CRUD, kanban moves, integrations OAuth, scraper runs, enrichment. ~12 endpoints.
- **M3 Automation** — timelines, templates, runs, channel registry. ~8 endpoints.
- **M6 Reports** — list, detail, generate-on-demand, compare. ~5 endpoints.
- **M7 Fintech** — invoices CRUD, spend analytics, anomalies. ~7 endpoints.

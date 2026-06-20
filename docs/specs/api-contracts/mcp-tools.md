# MCP Tools — Cross-Cutting Contract

**Date:** 2026-04-19
**Status:** Draft for team review.
**Depends on:** All module REST contracts (Foundation, M1–M7). This doc is the integration surface between Lara and every module.

This is the machine-readable equivalent of the REST surface — the tools Lara can call. The REST endpoints are for the admin UI; the MCP tools are for the LLM. Most tools mirror REST shapes; a few (like natural-language search) are MCP-specific because they only make sense when an LLM is on the other side.

---

## How MCP is wired

```
Lara (FastAPI agent loop)
          │  HTTP Streamable transport
          ▼
    MCP Gateway              ← single endpoint /mcp
   (auth + namespace         ← enforces demo vs admin allow-list
    + fan-out)               ← freezes catalog per session
          │
   ┌──────┼──────┬──────┬──────┬──────────┐
   ▼      ▼      ▼      ▼      ▼          ▼
  crm.*  docs.* auto.* rep.* fin.*    hubspot.* / zoho.* / sheets.*
  (M2)   (M1)   (M3)  (M6)  (M7)     (third-party, mounted)
```

**Pattern:**
- Each module exposes a FastMCP server as part of the FastAPI app (mounted at `/mcp/<module>`, internal-only — never hit directly by anyone except the gateway).
- The gateway is a FastMCP composite proxy (`create_proxy(mcpServers=...)`) that aggregates all module servers into a single unified catalog.
- Lara connects only to the gateway. It never knows which module a tool lives in — it just sees `crm__search_leads` and calls it.
- Third-party MCPs (HubSpot, Zoho, Sheets) mount into the same gateway. Their tools get the same namespacing treatment.

**Session binding.** Every MCP request carries session context (demo UUID or admin user_id + role) injected by the gateway middleware into a `ContextVar`. Module tools read session via the ContextVar — never trust any claim the client made.

---

## Conventions

### Tool naming

`<module>__<verb>_<noun>` — double underscore separates namespace from tool name. Examples:
- `crm__search_leads`
- `docs__search`
- `reports__get_latest`
- `automation__start_run`
- `fintech__list_invoices`

Verbs we use consistently: `list`, `get`, `search`, `add`, `update`, `delete`, `start`, `pause`, `cancel`, `trigger`, `compare`.

Namespaces: `crm` (M2), `docs` (M1), `memory` (M1), `lara` (M1 self), `automation` (M3), `reports` (M6), `fintech` (M7), `hubspot`, `zoho`, `sheets` (third-party).

### Input / output shapes

- **Every tool input is a `@dataclass`.** Stdlib types only (`str`, `int`, `bool`, `list[X]`, `dict`, `X | None`). No Pydantic.
- **Every tool output is a `@dataclass`** — same rules. Tools never return raw dicts; FastMCP auto-generates JSON schema from the return-type hint so the LLM gets structured output.
- **Reuse REST dataclasses** where the shape overlaps. Only introduce a tool-specific dataclass when there's a genuine difference (natural-language query field, LLM-ranking hint, etc.).
- **Empty inputs** are represented as `@dataclass class Empty: pass` rather than `None` — keeps schema generation consistent.

### Auth + allow-list

Every tool is tagged with who can call it:
- `public` — any session (demo or admin). Only read-tools qualify.
- `admin` — admin session only. Includes all writes + anything involving PII.

The gateway enforces via FastMCP's transform layer:
- On `tools/list`: filter the catalog by allow-list before returning.
- On `tools/call`: verify the tool's allow-list matches the session; reject with MCP error `-32602` (method not found or unauthorized) otherwise — deliberately ambiguous, matches the M2 gotcha about not leaking admin surface existence.

### Error handling

Tools never raise raw exceptions. All exceptions caught and mapped:
- **Not found** → return a tool result with `error` populated (e.g., `{"found": false, "error": "lead_not_found"}`) rather than raising. Lets the LLM handle gracefully.
- **Upstream failure** (LLM, third-party API) → MCP error `-32603` (internal error) with `data: {"code": "upstream_failed", "retryable": true}`. The agent loop can retry.
- **Rate-limited** → MCP error `-32029` (custom in our range) with `data: {"code": "rate_limited", "retry_after_seconds": int}`. Agent loop backs off.
- **Validation error** → MCP error `-32602` with details.

AI SDK's `tool-output-error` event surfaces these to the frontend as clean error messages.

### Catalog freeze per session

**Hard requirement from M1 research memo.** Anthropic's prompt cache is `tools → system → messages`; any mid-session tool-list change busts the cache and spikes cost ~10×. The gateway:
1. On first request of a session, loads the full catalog (filtered by allow-list), caches it in Redis under `mcp:catalog:{session_id}` with the session's TTL.
2. Every subsequent `tools/list` call in the same session returns the cached catalog — even if a module hot-reloaded and now advertises a new tool.
3. New tools are visible only on the **next** session.

This is intentional. Costs stability > feature freshness within a 5-minute window.

### Session context injection

Gateway middleware sets a `ContextVar` on every tool call:

```python
@dataclass
class McpSessionContext:
    kind: str                     # "demo" | "admin"
    session_id: str               # demo UUID or admin JWT subject
    admin_user_id: str | None     # populated when kind == "admin"
    role: str | None              # populated when kind == "admin"
    tenant_id: str                # DEFAULT_TENANT_ID in V0
    demo_seconds_remaining: int | None  # demo-only
    demo_tokens_remaining: int | None   # demo-only
```

Module tool implementations read via `McpSessionContext.current()`. Never accept session fields as tool input — the LLM will hallucinate them.

---

## Gateway contract

A thin FastAPI router mounted at `/mcp`. The gateway itself doesn't expose tools — it proxies.

### `POST /mcp`

**Auth:** demo or admin (session cookie).

**Behavior:**
1. Extract session from cookies. 401 if neither valid.
2. Resolve `McpSessionContext`, store in `ContextVar`.
3. Delegate to the `FastMCPProxy` composite server, which handles the MCP JSON-RPC request:
   - `initialize` → standard MCP handshake.
   - `tools/list` → returns cached catalog for session (load + filter on first call).
   - `tools/call` → allow-list check → route to downstream module server → return result.
4. Any MCP-level errors surface as standard JSON-RPC error objects.

**Transport:** Streamable HTTP only. No stdio (won't work in Cloud Run). No SSE for MCP itself (SSE is for Lara's chat stream, which carries tool results as `tool-output-available` events — separate concern).

### `GET /mcp/tools` (debug)

Admin-only. Returns the current session's catalog as JSON. Useful for troubleshooting ("does Lara actually see the HubSpot tools after I connected?").

### `GET /mcp/health`

Public. Pings each downstream module server in parallel with 2s timeout. Returns per-module status. Used by the Inngest keep-alive cron and CI.

---

## Tool catalog

### `lara.*` (M1 — Lara self-reflection)

| Tool | Auth | Purpose |
|---|---|---|
| `lara__get_session_status` | public | Returns time/tokens remaining for the current demo session. Lara uses this to shape responses ("I have 90 seconds left, I'll be brief"). |

**Input:** `Empty` (session is implicit via ContextVar).
**Output:**
```python
@dataclass
class LaraSessionStatus:
    kind: str                     # "demo" | "admin"
    seconds_remaining: int | None # None for admin
    tokens_remaining: int | None
    model_in_use: str             # "groq-llama-4-70b" | "claude-haiku-4.5" | ...
```

---

### `memory.*` (M1 — long-term memory)

| Tool | Auth | Purpose |
|---|---|---|
| `memory__recall` | public | Retrieve relevant memory entries (facts, doc chunks, conversation summaries) for a query |
| `memory__store_fact` | admin | Explicitly store a fact (admin can teach Lara things) |

**`memory__recall` input:**
```python
@dataclass
class MemoryRecallInput:
    query: str
    kind: str | None = None       # "fact" | "doc_chunk" | "conversation_summary" | None for all
    k: int = 5                    # max results
```
**Output:**
```python
@dataclass
class MemoryRecallOutput:
    entries: list[MemoryEntry]    # reuses M1's MemoryEntry dataclass
```

Per M1 research: **not blind RAG**. The LLM decides when to call `memory__recall`. The tool returns relevant-to-query entries ranked by cosine similarity on embedding + freshness.

---

### `docs.*` (M1 — document Q&A)

| Tool | Auth | Purpose |
|---|---|---|
| `docs__search` | public | Semantic search over uploaded documents |
| `docs__get_full_text` | public | Fetch full text of a specific doc (when admin asks "summarize the MSA") |
| `docs__list_available` | public | List docs the current session can see (demo sees session-uploaded + seed corpus; admin sees all) |

**`docs__search` input:**
```python
@dataclass
class DocsSearchInput:
    query: str
    k: int = 5
    document_id: str | None = None  # optional — restrict to one doc
```
**Output:**
```python
@dataclass
class DocsSearchOutput:
    chunks: list[DocChunkHit]

@dataclass
class DocChunkHit:
    document_id: str
    document_filename: str
    chunk_index: int
    text: str
    page_number: int | None
    similarity_score: float       # 0-1, cosine similarity
```

---

### `crm.*` (M2 — Sales Intelligence)

| Tool | Auth | Purpose |
|---|---|---|
| `crm__search_leads` | public | Natural-language + filter search over leads |
| `crm__get_lead` | public | Fetch a single lead by id (demo sees seeded; admin sees all) |
| `crm__add_lead` | admin | Create a new lead |
| `crm__update_lead` | admin | Partial update on a lead |
| `crm__change_stage` | admin | Kanban-move equivalent |
| `crm__enrich_lead` | admin | Trigger enrichment (async; returns job_id) |
| `crm__rescore_lead` | admin | Sync rescore, returns new Score |
| `crm__list_activity` | admin | Activity timeline for a lead |
| `crm__list_integrations` | admin | What's connected |
| `crm__trigger_sync` | admin | Manual sync on an integration |

**`crm__search_leads` input:** `SearchLeadsQuery` (see M2 contracts — natural-language + structured filters).
**Output:** `SearchLeadsResult`.

The other tools' inputs/outputs mirror the M2 REST contract shapes (`Lead`, `LeadActivity`, `EnrichmentData`, `Score`, etc.) — see `m2-sales-intel.md`.

---

### `automation.*` (M3 — Automation Engine)

| Tool | Auth | Purpose |
|---|---|---|
| `automation__list_running` | public | Current active runs (demo sees seed data; admin sees real) |
| `automation__get_timeline` | public | Full ordered event timeline for one run |
| `automation__list_templates` | public | Available nurture sequences |
| `automation__start_run` | admin | Start a new run for a lead |
| `automation__pause_run` | admin | Pause |
| `automation__cancel_run` | admin | Cancel |
| `automation__inngest_diagnostics` | admin | Passthrough to Inngest's official MCP for deep debugging |

Input/output shapes mirror M3 REST contracts (`AutomationRun`, `AutomationEvent`, `AutomationTemplate`). See `m3-automation.md`.

**`automation__inngest_diagnostics`** is the passthrough tool — input is `{run_id, tool_name, args_dict}` and it proxies to Inngest's MCP. Exists so admins can ask Lara "why did run X fail at step 3" without leaving the chat.

---

### `reports.*` (M6 — Reports)

| Tool | Auth | Purpose |
|---|---|---|
| `reports__get_latest` | public | Most recent report of a kind |
| `reports__list` | public | Paginated list |
| `reports__get_by_period` | public | Fetch by explicit period |
| `reports__compare` | public | Two reports in one call — Lara synthesizes the diff |
| `reports__search` | public | Embedding-backed search over past report narratives ("when did we have that big invoice spike?") |
| `reports__generate_now` | admin | Trigger on-demand generation |

Shapes mirror M6 REST. `reports__search` is the one tool with no REST equivalent — it's a pgvector query over the narrative embedding column, useful when the admin asks Lara fuzzy time questions.

---

### `fintech.*` (M7 — Fintech, optional)

Exposed only when `m7_fintech_enabled == true` in config. Otherwise these tools are absent from the catalog (not 404'd — just never listed).

| Tool | Auth | Purpose |
|---|---|---|
| `fintech__list_invoices` | public | Filtered list |
| `fintech__get_invoice` | public | Single detail |
| `fintech__spend_by_category` | public | Aggregated breakdown |
| `fintech__spend_trend` | public | Time series |
| `fintech__overdue_invoices` | public | Overdue list |
| `fintech__anomalies` | public | Anomaly list |
| `fintech__recategorize_invoice` | admin | Change category (also updates vendor default) |

Shapes mirror M7 REST (`Invoice`, `InvoiceLineItem`, `SpendByCategory`, `AnomalyFlag`). Money stays decimal-stringified.

---

### Third-party MCP integrations

Mounted via the gateway using FastMCP's composite proxy. These are **admin-only** — demo sessions never see them in the catalog.

| Namespace | Source | Auth in our system | Auth to provider |
|---|---|---|---|
| `hubspot__*` | Official HubSpot MCP (GA late 2025) at `mcp.hubspot.com` | admin | OAuth 2.1 PKCE via URL-mode elicitation |
| `zoho__*` | Official Zoho MCP | admin | OAuth |
| `sheets__*` | `mcp-google-sheets` community server | admin | OAuth |

**Tools exposed:** whatever each provider's MCP server advertises. We don't re-document them here — Lara auto-discovers via `tools/list` fan-out, and the tool names get namespaced (`hubspot__list_contacts`, etc.).

**Connection flow** is per M2 contracts: admin clicks "Connect HubSpot" → `POST /api/integrations/connect` returns `oauth_elicitation_url` → popup handles OAuth → tokens stored encrypted → gateway picks up the now-connected MCP on next session's catalog load.

**Demo users do NOT see third-party tools** in their catalog. Keeping them server-side admin-only prevents a demo visitor from discovering that we're connected to "zerotoprod-sandbox" HubSpot (information leak) and prevents accidental mutation on real external data.

---

## Allow-list matrix

Summary table of who can call what. **public** = both demo + admin; **admin** = admin only.

| Namespace | Tools | Allow |
|---|---|---|
| `lara__*` | `get_session_status` | public |
| `memory__*` | `recall` | public |
| `memory__*` | `store_fact` | admin |
| `docs__*` | `search`, `get_full_text`, `list_available` | public |
| `crm__*` | `search_leads`, `get_lead` | public |
| `crm__*` | all mutations + activity + integrations | admin |
| `automation__*` | `list_running`, `get_timeline`, `list_templates` | public |
| `automation__*` | `start_run`, `pause_run`, `cancel_run`, `inngest_diagnostics` | admin |
| `reports__*` | all reads + `search` | public |
| `reports__*` | `generate_now` | admin |
| `fintech__*` | all reads | public (gated on `m7_fintech_enabled`) |
| `fintech__*` | `recategorize_invoice` | admin |
| `hubspot__*` / `zoho__*` / `sheets__*` | all | admin |

**Demo catalog size** at V0 is roughly 18 tools. Small enough that the LLM can hold the full catalog in its tool-use context without ceremony.
**Admin catalog size** is roughly 35 tools + third-party (10–30 more depending on connected integrations).

---

## Open questions

1. **Do we ship `memory__store_fact` in V0?** Admin "teach Lara" is a nice demo moment ("Remember that Acme's preferred channel is email") but means adding a write path and UI affordance. Proposal: yes — it's ~20 lines and makes Lara feel alive on demo.
2. **Inngest MCP as a production dep.** The official Inngest MCP is framed as dev-only. Our `automation__inngest_diagnostics` passthrough depends on it. Option A: run Inngest MCP against prod and accept the "dev-server" label. Option B: build a thin REST-to-MCP shim ourselves against Inngest's REST API. V0 call needed.
3. **Third-party MCP auth token storage.** HubSpot/Zoho/Sheets tokens live encrypted in `integrations.encrypted_tokens`. The gateway needs to decrypt per-session to set the right Authorization header when fanning out `tools/call`. Performance: 1–2ms per call; acceptable. Key rotation: deferred.
4. **Catalog cache invalidation.** Frozen per session is fine for demo (5-minute sessions). Admin sessions are 7 days — if we connect a new integration mid-day, admin can't see the new tools without signing out + in. Proposal: add `POST /mcp/refresh-catalog` admin-only endpoint that flushes the Redis cache. Cheap to build.
5. **Token counting.** Tool-call arguments + tool-call results count toward Anthropic/Groq/etc. token accounting. The demo-mode pre-emptive token cap already sums these via the streaming delta counter — no MCP-specific accounting needed. Confirm during M1 build.
6. **Tool output size caps.** A `crm__search_leads(limit=20)` returning 20 full `Lead` rows including embeddings could be ~30KB — fine for one call, problematic across a long agent loop. Trim outputs to essentials in each tool; define a per-namespace size budget during build.
7. **Natural-language search on every list tool?** Right now only `crm__search_leads` takes `natural_query`. Adding it to `fintech__list_invoices`, `reports__search`, etc. is a good V1 win. Defer.

---

## Gotchas

1. **The gateway is the only MCP surface.** Don't expose module MCP servers publicly. They're internal — only the gateway fan-out reaches them. Mount them on private paths (or even in-process if FastMCP supports it) and lock down with middleware.

2. **Demo-mode token cap applies to MCP calls.** A tool-call result that streams back as `tool-output-available` contains tokens the LLM will re-ingest on the next turn. The pre-emptive token counter in M1 must count these. Test case: `crm__search_leads` returning 20 leads → the result JSON is ~5k tokens → one call burns 25% of the 2000-token demo budget.

3. **Tool errors must not leak PII.** A `crm__get_lead` for a missing id returns `{"found": false, "error": "lead_not_found"}` — never echo the lead_id in the error message if the lead belonged to a different tenant (not an issue in V0's single-tenant model but a V1 landmine).

4. **`tools/list` must be deterministic.** If the catalog varies between two calls in the same session (e.g., because of a race on integration-connect), Anthropic's cache invalidates mid-session. The Redis-cached catalog avoids this — but only if the Redis write is idempotent. Use `SET NX` on first write; subsequent session-lifetime reads are read-only.

5. **Catalog filtering happens at `tools/list` time, not `tools/call` time.** Both enforcement points exist (defense in depth), but the list-time filter is what the LLM sees. A demo session that somehow smuggled a tool name it shouldn't see will still get `-32602` on call — but relying on that would mean the LLM already wasted tokens on a call it couldn't make. List-time filter is the primary gate.

6. **Third-party MCP tools can be slow.** HubSpot's MCP has a ~500ms–2s P95. If Lara chains three HubSpot calls, a demo session can burn significant wall-clock. Wrap third-party tool calls with a 5s timeout and fail fast with `upstream_failed`.

7. **Don't accept `session_id` / `tenant_id` / `admin_user_id` as tool inputs.** The LLM will hallucinate them. Always read from `McpSessionContext.current()`. Tools that take these as inputs are a security hole.

8. **Streamable HTTP transport only.** stdio doesn't work in Cloud Run's stateless functions. All module servers speak Streamable HTTP. Write this in the developer docs loud enough that nobody accidentally writes a stdio server.

9. **Tool descriptions are the UI for the LLM.** The text in each tool's description field is what the model reads when deciding to call the tool. Be precise: "Search leads by natural language query + optional filters. Returns up to 20 leads ranked by relevance." Vague descriptions → tool-choice errors.

10. **FastMCP's `create_proxy` namespace collision.** If two downstream servers both advertise a tool called `search`, the proxy uses `<server_name>__search`. Make sure module server names (crm, docs, fintech) match our intended namespaces. Verified during Foundation build.

---

## What's NOT in this doc

- Individual module REST contracts — see `foundation.md`, `m1-lara.md`, `m2-sales-intel.md`, `m3-automation.md`, `m6-reports.md`, `m7-fintech.md`.
- The Lara tool-use loop itself (max iterations, retry-on-error logic) — see `m1-lara.md`.
- Prompt-caching specifics with Anthropic — see `m1-lara.md`'s research + gotchas.
- FastMCP implementation patterns — defer to the build phase.

---

## Next contracts

None at the module-spec level. Remaining work:
- MCP gateway implementation (Foundation-level build task).
- Per-module FastMCP server scaffolding (each module's build task).
- Tool descriptions (the actual prose each tool ships with — written during implementation).
- Third-party MCP integration-test fixtures.

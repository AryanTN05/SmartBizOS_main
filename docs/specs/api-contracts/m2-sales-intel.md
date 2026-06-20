# M2 AI Sales Intelligence — API Contracts

**Date:** 2026-04-19
**Status:** Draft for team review.
**Depends on:** `docs/specs/api-contracts/foundation.md` (conventions, auth, error shapes, pagination), `docs/specs/api-contracts/m1-lara.md` (shared dataclass idioms, `Page[T]` usage).
**Research:** `docs/research/modules/m2-sales-intel.md`.

M2 is the **wedge module** — the one that carries the whole SmartBiz pitch: *"Keep your existing CRM, we'll make it smarter."* It's five cooperating layers (native CRM, MCP integrations, scrapers, enrichment, explainable scoring) surfaced through a conventional admin UI *and* as MCP tools Lara can call. The contracts below cover the REST surface only; the MCP tool surface is documented in the research memo (`crm.*`, `integrations.*`) and re-exported via the gateway — the REST endpoints and MCP tools share the same underlying service layer.

---

## Scope

**In this module:**
- Leads CRUD — list, get, create, update, delete, kanban-move (stage change).
- Lead enrichment trigger (manual) and scoring trigger (manual).
- Activity timeline (paginated, per-lead).
- Integrations management — list connected providers, start OAuth (URL-mode elicitation), disconnect, trigger sync.
- Scraper control — list configured scrapers, get status, trigger manual run.
- Shared dataclasses covering `Lead`, `LeadActivity`, `EnrichmentData`, `Score`, `Integration`, `Scraper`.

**Out of scope (handled elsewhere):**
- Lara chat over leads — M1 `/api/stream/chat` routes tool calls through the gateway. The `crm__search_leads` MCP tool is documented here for shape, but it's not a REST endpoint.
- OAuth callback handling for HubSpot / Zoho / Sheets — frontend + MCP gateway own the URL-mode elicitation popup lifecycle. REST here only exposes the *initiation* and the post-connect state.
- Automation runs (M3) that *consume* lead events — M2 emits Inngest events (`lead.created`, `lead.stage_changed`, `lead.scored`); M3 subscribes.
- Report rollups over leads (M6).
- Actual scraping / enrichment execution — those run as Inngest background jobs. REST endpoints only *trigger* and *observe*.

**Demo vs admin access:**
- All leads CRUD, integrations, and scraper control endpoints are **admin-only.** Demo sessions do not hit these endpoints directly.
- Demo sessions interact with leads **only through Lara** (M1 chat) via the `crm__search_leads` MCP tool, which reads seeded leads. Demo never writes. No tenant isolation is required — SmartBiz OS is single-tenant; `tenant_id` is populated from `DEFAULT_TENANT_ID` on every row.

---

## Pages

| Page | Route (frontend) | Purpose |
|---|---|---|
| Leads list | `/admin/leads` | Table view with filters (status, source, score range, owner, tags). Toggle to Kanban view for drag-between-stages |
| Lead detail | `/admin/leads/:id` | Full profile — basics, enrichment dossier, score breakdown with reasons, activity timeline, attached docs, automation runs |
| Integrations settings | `/admin/integrations` | Connect HubSpot / Zoho / Sheets via MCP; list connected sources; trigger manual sync; see last-sync timestamp and token health |
| Scraper control | `/admin/scrapers` | Configured scrapers list (Product Hunt daily, one directory weekly, LinkedIn seeded-only). Manual-run trigger and last-run status |
| Enrichment view | inline on `/admin/leads/:id` | Apollo/PDL dossier, wappalyzergo tech stack, LLM website summary, raw provider payload drawer |

---

## Per-page needs & actions

### Leads list (`/admin/leads`)

**On load:**
- `GET /api/leads?cursor=&limit=50&status=&source=&min_score=&max_score=&tag=&view=table` — paginated. `view` is a hint for the backend: `"table"` returns flat `Lead` rows; `"kanban"` returns `Lead` rows grouped by `stage` (frontend groups client-side either way, but `view` lets us cap per-stage counts so a 2000-lead Kanban board doesn't explode).
- `GET /api/config` — feature flags.

**Actions:**
- Filter / search → refetch with query params.
- Toggle to Kanban → same endpoint, different client rendering.
- Drag a card between columns → `POST /api/leads/:id/kanban-move { stage }`.
- Click a lead → navigate to `/admin/leads/:id`.
- "New lead" button → `POST /api/leads` (modal form).
- Bulk actions (tag, delete) → V1, not covered here.

### Lead detail (`/admin/leads/:id`)

**On load:**
- `GET /api/leads/:id` — full lead including latest score, latest enrichment, tags, owner.
- `GET /api/leads/:id/activity?limit=50&cursor=` — first page of activity timeline.

**Actions:**
- Edit fields → `PATCH /api/leads/:id`.
- Delete → `DELETE /api/leads/:id` (with confirmation).
- "Re-enrich" button → `POST /api/leads/:id/enrich`; returns immediately with `job_id`. Frontend polls activity timeline or receives push via SSE (future).
- "Re-score" button → `POST /api/leads/:id/rescore`; **synchronous** — returns fresh `Score` dataclass with reasons so the UI updates instantly. (Scoring is fast: single LLM call, ~1s.)
- "Change stage" → same `POST /api/leads/:id/kanban-move`.
- "Add note" → handled via M3 / activity endpoint (kind=`note`). Out of scope here.

### Integrations settings (`/admin/integrations`)

**On load:**
- `GET /api/integrations` — list of all providers (connected + available-but-not-connected).

**Actions:**
- "Connect HubSpot" → `POST /api/integrations/connect { provider: "hubspot" }`. Backend starts OAuth 2.1 PKCE, returns `oauth_elicitation_url`. Frontend opens a popup to that URL. When the OAuth callback lands server-side, the integration row transitions to `status=connected`. Frontend polls `GET /api/integrations` every 2s while the popup is open.
- "Disconnect" → `POST /api/integrations/:id/disconnect`. Revokes stored tokens.
- "Sync now" → `POST /api/integrations/:id/sync`. Triggers an Inngest event; returns 202 immediately.

### Scraper control (`/admin/scrapers`)

**On load:**
- `GET /api/scrapers` — list of configured scrapers with schedule + last-run state.

**Actions:**
- "Run now" → `POST /api/scrapers/:id/run`. Triggers the underlying Inngest function ad-hoc; returns 202 with a `run_id`.
- "Enable/Disable" → `PATCH /api/scrapers/:id { enabled: bool }`.
- No "create scraper" UI in V0 — scrapers are defined in code (Inngest functions). The list is seeded from a config table on migration.

### Enrichment view (inline on lead detail)

No dedicated endpoint — reads from `lead.enrichment_data` in the lead-detail payload. Dossier panel, tech-stack chips, website summary block, "view raw provider data" expander for the JSONB `raw_sources` blob (admin debugging only).

---

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/leads` | admin | Paginated lead list with filters (status, source, score range, tags, owner) |
| `GET` | `/api/leads/{id}` | admin | Full lead detail including latest score + latest enrichment |
| `POST` | `/api/leads` | admin | Create a lead manually |
| `PATCH` | `/api/leads/{id}` | admin | Update lead fields |
| `DELETE` | `/api/leads/{id}` | admin | Soft-delete (tombstone for DPDP audit) |
| `POST` | `/api/leads/{id}/kanban-move` | admin | Change stage; records a `status_change` activity |
| `POST` | `/api/leads/{id}/enrich` | admin | Trigger manual enrichment run (async, returns 202) |
| `POST` | `/api/leads/{id}/rescore` | admin | Trigger manual scoring (sync, returns fresh `Score`) |
| `GET` | `/api/leads/{id}/activity` | admin | Paginated activity timeline for a lead |
| `GET` | `/api/integrations` | admin | List all integrations + current status |
| `POST` | `/api/integrations/connect` | admin | Start OAuth flow; returns `oauth_elicitation_url` |
| `POST` | `/api/integrations/{id}/disconnect` | admin | Revoke tokens, flip status to `disconnected` |
| `POST` | `/api/integrations/{id}/sync` | admin | Trigger ad-hoc sync (async, returns 202) |
| `GET` | `/api/scrapers` | admin | List configured scrapers |
| `PATCH` | `/api/scrapers/{id}` | admin | Toggle enabled flag |
| `POST` | `/api/scrapers/{id}/run` | admin | Trigger manual scraper run (async, returns 202) |

**Sixteen endpoints** — a hair over the ~12 estimate in Foundation, but split: 9 for leads/activity, 4 for integrations, 3 for scrapers. Every endpoint is admin-only; demo reaches leads only via Lara's `crm__search_leads` tool (not shown in this table, see shared types below for the query shape).

---

## Shared types

All dataclasses use plain stdlib types (`str`, `int`, `bool`, `list[X]`, `dict`, `X | None`). Timestamps are Unix seconds as `int`. IDs are UUID strings. No Pydantic — these are the domain dataclasses the service layer operates on; the Pydantic boundary lives at the FastAPI request/response edge and is derived from these shapes.

```python
from dataclasses import dataclass, field

@dataclass
class Lead:
    id: str                               # UUID
    tenant_id: str                        # Always DEFAULT_TENANT_ID in V0
    name: str                             # Full name. Empty string if unknown.
    email: str | None
    phone: str | None
    company: str | None                   # Company name (denormalized for list views)
    company_domain: str | None            # Canonical domain, used for enrichment keying
    title: str | None                     # Role / job title
    source: str                           # "hubspot" | "sheets" | "zoho" | "tally" | "scraper_linkedin" | "scraper_producthunt" | "scraper_directory" | "scraper_review" | "manual" | "lara"
    source_ref: str | None                # External ID from the source system; used for idempotent upsert on sync
    status: str                           # Kanban stage. "New" | "Contacted" | "Qualified" | "Meeting" | "Proposal" | "Won" | "Lost"
    tags: list[str] = field(default_factory=list)
    score: "Score | None" = None          # Latest score (denormalized pointer). None until first scoring pass.
    enrichment_data: "EnrichmentData | None" = None  # Latest enrichment. None until first enrichment pass.
    owner_admin_user_id: str | None = None
    created_at_unix: int = 0
    updated_at_unix: int = 0
    last_activity_at_unix: int | None = None   # Most recent `lead_activities.occurred_at`; null if no activity yet

@dataclass
class LeadActivity:
    id: str                               # UUID
    lead_id: str
    kind: str                             # "note" | "email" | "status_change" | "enrichment" | "automation_event" | "score_changed" | "mcp_sync"
    payload: dict                         # Kind-specific shape. Free-form JSONB at the DB layer.
    occurred_at_unix: int
    actor_kind: str                       # "admin" | "lara" | "cron" | "integration" | "demo" (demo only via Lara-initiated side effects; rare)
    actor_id: str | None                  # Admin UUID, integration id, or None for cron/lara

@dataclass
class EnrichmentData:
    company_size: str | None              # e.g. "11-50", "51-200". Apollo-style bands.
    industry: str | None
    funding: str | None                   # Free-text (e.g. "Series B, $20M, 2025"). JSONB at DB layer.
    tech_stack: list[str] = field(default_factory=list)       # From wappalyzergo or DetectZeStack
    recent_news: list[str] = field(default_factory=list)      # 3 bullet summaries of last-30-day news
    person_role: str | None = None
    person_seniority: str | None = None   # "IC" | "Manager" | "Director" | "VP" | "C-level"
    website_summary: str | None = None    # LLM-generated description of what the company does (from homepage/about/pricing)
    providers: list[str] = field(default_factory=list)        # Which enrichment providers were hit this pass. e.g. ["apollo", "pdl", "firecrawl", "llm"]
    enriched_at_unix: int = 0

@dataclass
class Score:
    value: int                            # 0-100
    category: str                         # "hot" | "warm" | "cold" | "unqualified"
    reasons: list[str]                    # 3-5 short human-readable clauses. This is the money field.
    rubric_version: str                   # e.g. "v1.0" — lets us detect stale scores after a rubric change
    model: str                            # Model id used (e.g. "claude-sonnet-4-6")
    scored_at_unix: int

@dataclass
class Integration:
    id: str                               # UUID
    provider: str                         # "hubspot" | "zoho" | "sheets" | "tally"
    status: str                           # "connected" | "pending_oauth" | "disconnected"
    last_sync_at_unix: int | None         # Null if never synced
    lead_count_synced: int                # Running total of leads pulled from this integration
    oauth_elicitation_url: str | None     # Populated when status=="pending_oauth"; null otherwise
    connected_account_label: str | None   # Human-readable ("HubSpot: zerotoprod-sandbox"), shown in the UI

@dataclass
class Scraper:
    id: str                               # UUID
    source: str                           # "producthunt" | "directory_clutch" | "reviews_g2" | "linkedin_seed"
    schedule: str                         # Cron expression. e.g. "0 6 * * *" (PH daily). "manual" for scrapers with no schedule.
    enabled: bool
    last_run_at_unix: int | None
    last_run_status: str | None           # "success" | "partial" | "failed" | "running" | None if never run
    last_run_leads_added: int             # Count from most recent completed run
    notes: str | None = None              # Surface labels. e.g. "LinkedIn: seeded-only per legal. Not live."
```

### `crm__search_leads` (MCP tool; not a REST endpoint)

Documented for shape — this is how Lara queries leads on behalf of demo sessions. The tool lives in the `crm.*` FastMCP server; the request shape below is what Lara passes through the gateway.

```python
@dataclass
class SearchLeadsQuery:
    natural_query: str | None = None      # e.g. "founders of fintech SaaS companies with recent funding"
    status: list[str] | None = None       # Kanban stages to include
    min_score: int | None = None
    max_score: int | None = None
    tags: list[str] | None = None
    source: list[str] | None = None
    limit: int = 20                       # Always capped at 20 for demo. LLM re-ranks to top 10.

@dataclass
class SearchLeadsResult:
    leads: list[Lead]                     # Same Lead dataclass
    total_matched: int                    # Before limit; informational
    explain: str | None = None            # Optional natural-language rationale the LLM attaches ("ranked by recent-news signal + score")
```

The tool embeds `natural_query` against `leads.embedding` + `enrichment_data.website_embedding` (cosine similarity), intersects with the structured filters, and the agent loop re-ranks the top 20 before returning. Demo sessions hit this tool via Lara chat; admin sessions can hit it too for power-search use.

---

## Contracts

### `GET /api/leads`

**Request:** query params (all optional unless noted):
- `cursor: str | None`
- `limit: int = 25` (max 100)
- `status: str | None` — exact match against a stage. Repeatable (`?status=New&status=Contacted`) → treated as OR.
- `source: str | None` — exact match on `Lead.source`. Repeatable.
- `min_score: int | None`
- `max_score: int | None`
- `tag: str | None` — repeatable, AND-ed.
- `owner_admin_user_id: str | None`
- `view: str = "table"` — `"table"` or `"kanban"`. Pure frontend hint; does not change shape, only caps per-stage results when `"kanban"` to prevent payload blow-up (hard cap: 50 per stage).

**Response 200:**
```python
@dataclass
class LeadsListResponse:
    items: list[Lead]
    next_cursor: str | None
    total_estimate: int                   # Best-effort count of leads matching filters (pre-cursor). For display: "312 leads"
```

**Auth:** admin only. Demo returns `401 unauthenticated`.

**Errors:**
- `401 unauthenticated` — no admin session.
- `422 validation_failed` — `min_score > max_score`, or unknown `status`/`source` enum value.

**Behavior notes:**
- Default sort: `last_activity_at_unix DESC NULLS LAST, created_at_unix DESC`.
- `tenant_id` is set server-side to `DEFAULT_TENANT_ID` — never accepted from the client.
- When `view=kanban`, the per-stage cap is 50 (ordered by score DESC within each stage). Frontend shows "... and 42 more" below a capped column.

### `GET /api/leads/{id}`

**Request:** no body.

**Response 200:**
```python
@dataclass
class LeadDetailResponse:
    lead: Lead                            # Includes .score and .enrichment_data populated
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found` — lead doesn't exist or has been soft-deleted.

**Behavior:**
- Returns the *latest* score and enrichment (denormalized pointers). Full history lives in DB; not exposed via REST in V0 — if admin wants to see score history, surface through the activity timeline (`kind="score_changed"` entries).

### `POST /api/leads`

**Request:**
```python
@dataclass
class CreateLeadRequest:
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    company_domain: str | None = None
    title: str | None = None
    source: str = "manual"                # Default. Integrations bypass REST; they upsert directly via the MCP sync layer.
    tags: list[str] = field(default_factory=list)
    owner_admin_user_id: str | None = None
```

**Response 201:**
```python
@dataclass
class CreateLeadResponse:
    lead: Lead                            # Fully materialized; .score and .enrichment_data are None until background jobs land
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `422 validation_failed` — missing `name`, or `source` not in the source enum, or malformed email/domain.
- `409 conflict` — add this code if a duplicate lead (matching email OR `company_domain + name`) already exists. Response `details.existing_lead_id` points at the dupe so the UI can offer a "view existing" link.

**Behavior:**
- Creates the lead, emits `lead.created` Inngest event, returns immediately. The event triggers enrichment + scoring asynchronously (30-60s to settle). Frontend can poll `GET /api/leads/:id` or wait for the activity timeline to update.
- `tenant_id` set to `DEFAULT_TENANT_ID`.

### `PATCH /api/leads/{id}`

**Request:** partial shape — any field from `Lead` except `id`, `tenant_id`, `source`, `source_ref`, `created_at_unix`, `score`, `enrichment_data`, `last_activity_at_unix`.
```python
@dataclass
class UpdateLeadRequest:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    company_domain: str | None = None
    title: str | None = None
    status: str | None = None             # Use kanban-move endpoint for UX consistency, but PATCH also works
    tags: list[str] | None = None
    owner_admin_user_id: str | None = None
```

**Response 200:**
```python
@dataclass
class UpdateLeadResponse:
    lead: Lead
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found`
- `422 validation_failed` — unknown `status` enum, malformed email.

**Behavior:**
- Only provided fields are updated (`None` means "don't touch"). To clear a field, an explicit sentinel is NOT supported in V0 — the admin can empty-string a value if needed.
- Writing `status` here records a `status_change` activity (same as kanban-move).
- Updating `tags` replaces the full list (not additive).

### `DELETE /api/leads/{id}`

**Request:** no body.

**Response 204.**

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found`

**Behavior:**
- **Soft delete.** Sets `deleted_at_unix` on the row; filters all list/get endpoints. Activity timeline, enrichment history, and scores are retained (for DPDP audit retention — see research memo).
- Associated pgvector rows stay put until a separate housekeeping cron reaps them (default 30 days).
- A hard-delete endpoint is deferred to the data-subject-erasure flow (DPDP).

### `POST /api/leads/{id}/kanban-move`

**Request:**
```python
@dataclass
class KanbanMoveRequest:
    stage: str                            # Must be a valid Kanban stage
```

**Response 200:**
```python
@dataclass
class KanbanMoveResponse:
    lead: Lead
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found`
- `422 validation_failed` — unknown stage.

**Behavior:**
- Updates `Lead.status`, bumps `updated_at_unix`, inserts a `LeadActivity { kind: "status_change", payload: {from, to}, actor_kind: "admin", actor_id: <admin_uuid> }`, emits Inngest event `lead.stage_changed` (consumed by M3 automations).
- Idempotent on same-stage move (no-op, returns 200 with unchanged lead).

### `POST /api/leads/{id}/enrich`

**Request:** optional body:
```python
@dataclass
class EnrichTriggerRequest:
    providers: list[str] | None = None    # None = use default fan-out. Otherwise restrict to a subset (e.g. ["apollo"] for a cheap refresh)
    force: bool = False                   # If False, returns the existing enrichment if < 7 days old
```

**Response 202:**
```python
@dataclass
class EnrichTriggerResponse:
    lead_id: str
    job_id: str                           # Inngest run id; for ops debugging only
    status: str                           # "queued" | "already_fresh" (when force=False and existing is <7d)
    existing_enrichment_age_seconds: int | None   # Populated when status=="already_fresh"
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found`
- `422 validation_failed` — unknown provider in the list.

**Behavior:**
- Emits Inngest event `lead.enrichment_requested { lead_id, providers, force }`.
- Handler calls Apollo + PDL + Firecrawl + LLM + tech-stack-fingerprinter per the research memo, writes a new `enrichment_data` row, updates `leads.latest_enrichment_id`, logs a `LeadActivity { kind: "enrichment" }`.
- Frontend learns about completion by polling `GET /api/leads/:id` or by fetching `GET /api/leads/:id/activity` (looking for the new `enrichment` activity).

### `POST /api/leads/{id}/rescore`

**Request:**
```python
@dataclass
class RescoreRequest:
    force: bool = False                   # If False, returns the existing score if the rubric version matches and it's <48h old
```

**Response 200:**
```python
@dataclass
class RescoreResponse:
    score: Score
    was_cached: bool                      # True when we returned an existing score (force=False, <48h, matching rubric)
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found`
- `409 conflict` — lead has no enrichment yet. `details.reason = "needs_enrichment_first"`. Frontend offers "Enrich & score" which chains `/enrich` then `/rescore` once the activity lands.
- `502 upstream_failed` — LLM call failed; operation is retryable.

**Behavior:**
- **Synchronous.** Single LLM call against the rubric prompt (see research memo §"Lead scoring"). ~1s wall clock for Sonnet-class.
- Writes a new `scores` row, updates `leads.latest_score_id`, logs a `LeadActivity { kind: "score_changed", payload: {old, new, reasons} }`.
- This is the endpoint the "Re-score" button on the lead detail page calls. The UI updates with the fresh `reasons` list inline.

### `GET /api/leads/{id}/activity`

**Request:** query params — `cursor`, `limit` (default 25, max 100), optional `kind` filter (repeatable).

**Response 200:**
```python
@dataclass
class LeadActivityResponse:
    items: list[LeadActivity]
    next_cursor: str | None
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found` — if lead doesn't exist (empty timeline returns 200 with `items: []`).

**Behavior:**
- Default sort: `occurred_at_unix DESC`.
- Pagination is cursor-based over `occurred_at_unix + id` — matches Foundation's convention.

### `GET /api/integrations`

**Request:** no body.

**Response 200:**
```python
@dataclass
class IntegrationsListResponse:
    items: list[Integration]
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`

**Behavior:**
- Returns one row per known provider (hubspot, zoho, sheets, tally), whether connected or not. Disconnected rows have `status="disconnected"`, `last_sync_at_unix=None`, etc.
- Tally in V0 is always `status="connected"` with `connected_account_label="Tally (seeded demo)"` — the research memo flags this as a stub.
- Not paginated; the list is bounded (4-5 providers).

### `POST /api/integrations/connect`

**Request:**
```python
@dataclass
class ConnectIntegrationRequest:
    provider: str                         # "hubspot" | "zoho" | "sheets"
```

**Response 200:**
```python
@dataclass
class ConnectIntegrationResponse:
    integration_id: str                   # UUID of the pending Integration row
    oauth_elicitation_url: str            # URL the frontend opens in a popup
    elicitation_mode: str                 # "url" — per MCP spec; reserved for future modes like "device_code"
    expires_at_unix: int                  # When the auth URL/state token expires (default 10min)
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `422 validation_failed` — unknown provider.
- `409 conflict` — provider already connected. `details.existing_integration_id`. UI offers "Disconnect first" path.

**Behavior:**
- Creates an `Integration` row with `status="pending_oauth"`, stores the PKCE verifier + state token server-side (Redis, 10min TTL).
- For HubSpot/Zoho/Sheets: builds the provider's authorize URL with PKCE challenge + our callback URL.
- Frontend opens the URL in a popup. OAuth callback (not documented here — handled by a separate internal callback route) exchanges the code for tokens, encrypts at rest, flips `Integration.status` to `"connected"`, populates `connected_account_label`.
- Frontend polls `GET /api/integrations` every 2s while the popup is open; sees the status change and closes the popup.
- **Note:** the MCP URL-mode elicitation spec is what Claude Code 2.1.76 consumes; our web frontend re-uses the same URL flow for browser sessions. Both paths land on the same OAuth callback.

### `POST /api/integrations/{id}/disconnect`

**Request:** no body.

**Response 204.**

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found`
- `409 conflict` — integration is already `status="disconnected"`. Idempotency choice: return 204 anyway (treat as no-op). Currently documenting 409 as the strict option; to be decided in open questions.

**Behavior:**
- Revokes tokens with the provider where the provider supports it (HubSpot yes, Sheets partial, Zoho yes).
- Decrypts, revokes upstream, then nulls the encrypted token columns.
- Flips `Integration.status` to `"disconnected"`. Previously-synced leads remain in the DB; their `source` column still reflects the integration. Last-sync timestamp preserved for audit.
- Does NOT delete leads that were synced from this provider. Admin must manually delete if desired.

### `POST /api/integrations/{id}/sync`

**Request:** optional body:
```python
@dataclass
class SyncIntegrationRequest:
    mode: str = "incremental"             # "incremental" (since last_sync_at_unix) | "full"
```

**Response 202:**
```python
@dataclass
class SyncIntegrationResponse:
    integration_id: str
    job_id: str                           # Inngest run id
    mode: str
    started_at_unix: int
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found`
- `409 conflict` — integration `status != "connected"`. `details.status`.
- `429 rate_limited` — manual sync already in flight for this integration (one concurrent sync per provider; Redis lock, 5min TTL).

**Behavior:**
- Emits Inngest event `integrations.sync_requested { integration_id, mode }`.
- The handler calls the provider MCP, upserts leads by `source_external_id` (idempotent), maps stage strings using the per-integration stage dictionary (see research memo), and updates `Integration.last_sync_at_unix` + `lead_count_synced` on completion.
- UI surfaces completion via the integration list refresh.

### `GET /api/scrapers`

**Request:** no body.

**Response 200:**
```python
@dataclass
class ScrapersListResponse:
    items: list[Scraper]
```

**Auth:** admin only.

**Behavior:**
- Returns all configured scrapers. In V0: Product Hunt daily, one directory (Clutch) weekly, G2 reviews weekly (seeded + one live run per demo), LinkedIn seeded-only (`enabled=false` by default, with `notes="LinkedIn: seeded-only per legal. hiQ settlement = do not run live."`).
- Not paginated; bounded list.

### `PATCH /api/scrapers/{id}`

**Request:**
```python
@dataclass
class UpdateScraperRequest:
    enabled: bool | None = None
```

**Response 200:**
```python
@dataclass
class UpdateScraperResponse:
    scraper: Scraper
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found`
- `422 validation_failed` — attempting to enable the LinkedIn seed scraper (blocked server-side per legal policy; `details.reason="linkedin_live_scraping_disabled"`).

**Behavior:**
- The LinkedIn scraper's `enabled` field is *hard-pinned to false*. Even an admin cannot flip it. This is a belt-and-suspenders guard on top of the code-level "seeded-only" mode — matches the research memo's legal callout.

### `POST /api/scrapers/{id}/run`

**Request:** optional body:
```python
@dataclass
class ScraperRunRequest:
    dry_run: bool = False                 # If True, run the scrape but don't persist leads — useful for demo pre-flight
```

**Response 202:**
```python
@dataclass
class ScraperRunResponse:
    scraper_id: str
    job_id: str
    started_at_unix: int
    dry_run: bool
```

**Auth:** admin only.

**Errors:**
- `401 unauthenticated`
- `404 not_found`
- `409 conflict` — scraper is already running (`last_run_status == "running"`). One concurrent run per scraper.
- `422 validation_failed` — scraper is `enabled=false` (e.g. LinkedIn). `details.reason`.

**Behavior:**
- Emits Inngest event `scrapers.run_requested { scraper_id, dry_run }`.
- Flips `Scraper.last_run_status` to `"running"`, sets `last_run_at_unix` to now.
- Handler runs the scrape, writes leads with `source=scraper_*`, emits `lead.created` events for each.
- On completion: `last_run_status` transitions to `"success" | "partial" | "failed"`, `last_run_leads_added` updated.

---

## Open questions

1. **Stage enum as config vs code.** V0 hardcodes seven Kanban stages (`New → Contacted → Qualified → Meeting → Proposal → Won → Lost`). Per-tenant configurable stages are a reasonable V1 ask — but SmartBiz is single-tenant until further notice, so the demo can live with hardcoded. Decision deferred, but the integration stage-mapping dictionary (HubSpot/Zoho pipeline → our stages) IS configurable via a per-integration JSONB column.

2. **Soft delete vs hard delete.** V0 uses soft delete everywhere. For DPDP data-subject-erasure requests, we need an actual hard-delete path that purges the lead, all activities, all enrichment history, all scores, and the pgvector rows. Proposal: `POST /api/leads/:id/erase` admin-only, async, emits `lead.erased` event and runs the purge. Deferred.

3. **Integration token encryption key rotation.** Foundation flags KMS encryption but doesn't pin a rotation policy. Proposal: 90-day rotation, re-encrypt on read. Needs a team call — impacts the `integrations.sync_*` crons.

4. **One-sync-at-a-time Redis lock vs queue.** Currently we 429 if a manual sync overlaps with a cron sync. Alternative: queue the manual request behind the cron and return 202 with an ETA. The queue path is nicer UX but adds an Inngest state we'd have to surface. V0: keep 429, revisit if demos show the limitation.

5. **Per-lead RBAC for "owner".** `Lead.owner_admin_user_id` exists but no endpoint respects it yet — admin can see/edit all leads regardless of owner. Forward-compat hook for a V1.5 "sales rep sees only their leads" feature (once `admin_users.role` grows beyond `"admin"`).

6. **Scoring idempotency key.** If a client clicks "Re-score" twice quickly, we'll get two LLM calls and two `scores` rows. Debounce client-side is easy; server-side `Idempotency-Key` header is cleaner but adds Redis state. Proposal: client debounce for V0, add the header pattern if it becomes a real issue.

7. **`view=kanban` per-stage cap strategy.** Hard cap at 50 per stage is a guess; needs calibration on seed data. If a pipeline has 300 leads in "Contacted", the list view already handles it via cursor; Kanban UI just needs to communicate the truncation cleanly.

8. **Activity timeline retention.** V0 keeps everything forever. Inngest re-score cron + hourly integration polling means a single lead can accumulate hundreds of activities over months. Proposal: 365-day retention with a daily cleanup cron, but preserve `status_change`, `score_changed`, and `note` indefinitely. Discuss.

---

## Gotchas

1. **Source-agnostic scoring is a *contract* with the integration layer, not just a convention.** The scoring prompt must never see `Lead.source` — only `enrichment_data` and `lead_activities`. If the integration layer ever dumps provider-specific jargon into an activity's `payload` ("HubSpot lifecycle_stage_change"), the scorer will start to bias. Canonicalize activity payloads at ingest time.

2. **`source_external_id` is the upsert key, not email.** Two LinkedIn profiles with the same name but different person-IDs should create two leads. Two HubSpot contacts with the same `hs_contact_id` from different syncs should upsert to one. Email collision detection happens at a separate deduplication pass, not at sync time.

3. **Kanban-move races.** Two admins dragging the same card to different columns within a second will produce two `status_change` activities and a "last write wins" on `status`. V0 accepts this — single-team tool, the UI shows stale state briefly. Optimistic-locking via `If-Match: <updated_at_unix>` is a reasonable V1 add.

4. **LinkedIn scraper enable is server-blocked, not just UI-hidden.** Research memo explicitly calls out the hiQ legal situation. The `PATCH /api/scrapers/:id { enabled: true }` must reject with 422 for the LinkedIn scraper, regardless of admin role. Never trust the UI to gate this.

5. **Integration `disconnect` doesn't delete leads.** If an admin connects HubSpot, pulls 500 leads, then disconnects, those 500 leads stay in our DB with `source="hubspot"` and stale `source_ref`s. If they reconnect, the next sync upserts by `source_external_id` and refreshes. This is intentional — losing a connection shouldn't lose data. Document in the UI copy.

6. **`rescore` with no enrichment is a 409, not a 422.** Semantically the request is valid; the *resource state* isn't ready. 409 is the correct code and the UI gets an actionable error (`details.reason="needs_enrichment_first"`).

7. **`oauth_elicitation_url` is short-lived.** 10-minute TTL on the state token. If the admin starts a connect flow, walks away for lunch, then clicks the popup — the OAuth callback fails with a generic provider error. Frontend should detect that the elicitation is stale (compare `expires_at_unix` on refresh of `/api/integrations`) and re-initiate.

8. **Stage dictionary mapping is per-integration, not global.** Each `Integration` row has a `stage_mapping JSONB` column (not exposed in REST yet; read-only in V0, populated from sane defaults per provider). HubSpot's "salesqualifiedlead" → our "Qualified"; Zoho's "Proposal/Quotation" → our "Proposal". Changing the mapping mid-sync causes stage churn — don't.

9. **Inngest job IDs leak in 202 responses.** They're meant for ops debugging (find-the-run in the Inngest UI), not for client logic. The client should never depend on a specific `job_id` format.

10. **Pydantic lives only at the FastAPI edge.** These dataclasses are the domain truth. When FastAPI receives a `CreateLeadRequest`, it's parsed by a derived Pydantic model and immediately converted to the stdlib dataclass before entering the service layer. Same for responses — dataclass → Pydantic for serialization, never the reverse direction in service code.

11. **`tenant_id` is never accepted from a client.** Every write path sets it to `DEFAULT_TENANT_ID` server-side. An incoming request body that includes a `tenant_id` field gets silently dropped (not even logged — reduces noise).

12. **Demo sessions never touch these endpoints.** If a demo cookie somehow reaches `/api/leads`, the response is `401 unauthenticated` (NOT 403 — we don't leak the existence of an admin surface). Lara's `crm__search_leads` tool enforces its own demo/admin gating inside the MCP server, not here.

---

## Next contracts to write

- **M3 Automation** — timelines, templates, runs, channel registry. Consumes `lead.created` / `lead.stage_changed` / `lead.scored` events emitted by M2. ~8 endpoints.
- **M6 Reports** — list, detail, generate-on-demand, compare. Rolls up M2 (leads funnel) and M7 (fintech) into exec summaries. ~5 endpoints.
- **M7 Fintech** — invoices CRUD, spend analytics, anomalies. Pulls from Tally integration (same MCP layer as M2 but different tools). ~7 endpoints.

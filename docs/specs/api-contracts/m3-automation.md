# M3 Automation Engine — API Contracts

**Date:** 2026-04-19
**Status:** Draft for team review.
**Depends on:** `docs/specs/api-contracts/foundation.md` (conventions, auth, error shapes), `docs/specs/api-contracts/m2-sales-intel.md` (lead source).
**Research:** `docs/research/modules/m3-automation.md`.

M3 is the **workflow framework** that makes seeded lead data feel alive. Every run is a `trigger → action → wait → check → next-action` sequence durably executed by **Inngest** (Python SDK), projected into `automation_runs` + `automation_events` for fast UI reads, and rendered as a visual per-lead timeline. V0 ships one live channel (email via Resend) and a **ChannelAdapter registry** with honest stubs for WhatsApp / LinkedIn / SMS — "pluggable" is demonstrably real, not slideware.

---

## Scope

**In this module:**
- Run management: list, detail (timeline), pause, cancel, start.
- Template catalog: list + read-only detail for three pre-seeded nurtures (`cold_outbound_v1`, `welcome_v1`, `reengagement_v1`).
- Channel registry introspection: which adapters are live vs stubbed.
- Timeline UI backing queries — served from `automation_events` projection, never Inngest's state directly.

**Out of scope (handled elsewhere):**
- **Tool surface for Lara** lives in M1's MCP gateway. Automation exposes `automation.*` tools (start/pause/cancel/list/timeline) — those are MCP tools, not REST endpoints. Demo users reach automations only via Lara.
- **Provider webhook handlers** (`POST /api/webhooks/resend`) — part of the integrations ingestion surface, not admin API. Webhooks translate into canonical `email.opened`/`email.clicked` events and fan out to Inngest. Documented in the integrations contract, not here.
- **Inngest deep diagnostics** — exposed as MCP tool `automation.inngest_diagnostics(run_id, tool, args)` for Lara. Not a REST endpoint. See "Notes on Inngest diagnostics" below.
- **Template editing UI** — V0 is code-as-template (Python dataclass). A template editor is V1+. All template endpoints are read-only.
- **Per-tenant isolation** — V0 is single-tenant (see Foundation); `tenant_id` column exists but is always `DEFAULT_TENANT_ID`.

---

## Pages

| Page | Route (frontend) | Purpose |
|---|---|---|
| Runs list | `/admin/automations` | Active + completed runs, filter by template / status / lead |
| Run detail | `/admin/automations/:run_id` | Visual per-lead timeline with events, lead context, pause/cancel controls |
| Templates list | `/admin/templates` | Pre-seeded nurture sequences (cold_outbound_v1, welcome_v1, reengagement_v1) |
| Template detail | `/admin/templates/:id` | Read-only view of step definition + placeholder surface |
| Channels registry | `/admin/channels` | Email (active) + WhatsApp/LinkedIn/SMS stubs marked "plug-in ready" |

All five pages are **admin-only**. Demo users cannot access them directly; they interact with automations through Lara tool calls which hit the same backend services but via MCP, not REST.

---

## Per-page needs & actions

### Runs list (`/admin/automations`)

**On load:**
- `GET /api/automations/runs?limit=25&cursor=...` — first page.
- Optional filter params: `status`, `template_id`, `lead_id`.

**Actions:**
- Filter pill → same endpoint with new query params.
- Open row → navigate to `/admin/automations/:run_id`.
- "Start new run" (from detail of a lead, or from this page's modal) → `POST /api/automations/runs { lead_id, template_id }`.

### Run detail (`/admin/automations/:run_id`)

**On load:**
- `GET /api/automations/runs/:id` — returns run header + full ordered `events` list + lead snapshot + template summary. One roundtrip so the timeline renders without waterfalls.

**Actions:**
- Pause → `POST /api/automations/runs/:id/pause`. Optimistic UI flips status to `paused`; backend writes a `run_paused` event and calls Inngest pause.
- Cancel → `POST /api/automations/runs/:id/cancel`. Confirmation modal (destructive). Writes `run_cancelled` event and calls Inngest cancel.
- "View raw Inngest state" (admin power tool) → opens Lara dock with a pre-filled prompt invoking `automation.inngest_diagnostics`. Not a REST call from this page.

**Auto-refresh:** page polls `GET /api/automations/runs/:id` every 5s while `status == "running"`. Stops polling on any terminal state. Webhook → Inngest → DB projection latency is typically < 2s so 5s is comfortable.

### Templates list (`/admin/templates`)

**On load:**
- `GET /api/automations/templates` — returns all three pre-seeded templates. No pagination in V0 (count is small and fixed).

**Actions:**
- Open row → `/admin/templates/:id`.
- "Start run with this template" → opens a lead-picker modal; confirms via `POST /api/automations/runs`.

### Template detail (`/admin/templates/:id`)

**On load:**
- `GET /api/automations/templates/:id` — step-by-step definition, channels used, the email body previews for each `send` step (rendered with a placeholder lead context so admins can eyeball copy).

**Actions:** none. V0 is read-only. Edits go through code review + deploy.

### Channels registry (`/admin/channels`)

**On load:**
- `GET /api/automations/channels` — list of registered adapters with status and provider.

**Actions:** none. Informational surface — answers "is WhatsApp live yet?" without code-spelunking.

---

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/automations/runs` | admin | List runs, filter by status/template/lead, paginated |
| `POST` | `/api/automations/runs` | admin | Start a new run: emits `lead.nurture.start` Inngest event |
| `GET` | `/api/automations/runs/{id}` | admin | Run header + full ordered event timeline + lead + template |
| `POST` | `/api/automations/runs/{id}/pause` | admin | Pause an in-flight run (calls Inngest pause API, logs event) |
| `POST` | `/api/automations/runs/{id}/cancel` | admin | Cancel an in-flight run (calls Inngest cancel API, logs event) |
| `GET` | `/api/automations/templates` | admin | List the three pre-seeded templates |
| `GET` | `/api/automations/templates/{id}` | admin | Template detail: steps, channels, placeholder schema, previews |
| `GET` | `/api/automations/channels` | admin | Channel adapter registry with live/stub status |

Eight endpoints. Matches the research memo's "~8 endpoints" estimate exactly.

**Note on Inngest diagnostics passthrough.** Deep Inngest introspection (retry history, step-level state, raw function logs) is **not a REST endpoint**. It's an MCP tool called `automation.inngest_diagnostics(run_id, tool, args)` that Lara invokes on the admin's behalf. The tool proxies to Inngest's official MCP server (framed as dev-server today; prod posture is an open question). Correlation key is the `inngest_run_id` column we store on `automation_runs` — one value links our projection to Inngest's authoritative state. If the admin wants the raw truth, they ask Lara; they don't get a dashboard tab for it. Keeps the REST surface small and the advanced tooling composable.

---

## Contracts

### Shared types

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class AutomationRun:
    id: str                            # UUID
    lead_id: str                       # UUID — FK to leads.id (M2)
    template_id: str                   # UUID — FK to automation_templates.id
    template_key: str                  # denormalized for list rendering: "cold_outbound_v1"
    inngest_run_id: str | None         # correlation key for diagnostics; None if not yet reported back
    status: str                        # "running" | "paused" | "completed" | "failed" | "cancelled"
    started_at_unix: int
    completed_at_unix: int | None      # populated on terminal states
    current_step_name: str | None      # last step we logged; None if just enqueued
    next_fire_at_unix: int | None      # when the current wait resolves; None if not waiting
    created_by: str                    # "admin:<uid>" | "lara:demo:<session_id>" | "lara:admin:<uid>" | "system"

@dataclass
class AutomationEvent:
    id: str                            # UUID
    run_id: str                        # UUID
    step_name: str                     # "email_sent" | "wait_completed" | "branch_taken" | ...
    channel: str | None                # "email" | "whatsapp" | None for control events (run_started, run_paused)
    outcome: str                       # "sent" | "opened" | "clicked" | "no_response" | "failed" | "wait_completed" | "branch_taken" | "breakup_sent"
    occurred_at_unix: int
    payload: dict                      # JSONB passthrough: {message_id, subject, provider_raw, error, branch, ...}

@dataclass
class AutomationTemplate:
    id: str                            # UUID
    key: str                           # stable string: "cold_outbound_v1" | "welcome_v1" | "reengagement_v1"
    name: str                          # human-readable: "Cold outbound (5-step with breakup)"
    description: str                   # one-paragraph pitch for the templates list
    step_count: int
    channels_used: list[str]           # e.g., ["email"]
    status: str                        # "active" | "draft" — V0 all three are "active"
    version: str                       # "v1" — bumped when step order changes in a new deploy
    created_at_unix: int

@dataclass
class ChannelAdapter:
    name: str                          # "email" | "whatsapp" | "linkedin" | "sms"
    status: str                        # "active" | "stub"
    provider: str                      # "resend" | "stub" | future: "twilio" | "meta_cloud_api" | "phantombuster"
    capabilities: list[str]            # e.g., ["send", "track_opens", "track_clicks"] for email; ["send_stub"] for stubs
    note: str | None                   # optional pitch copy: "WhatsApp live via Meta Cloud API — contact team"

@dataclass
class TemplateStep:
    order: int                         # 0-indexed
    kind: str                          # "send" | "wait" | "check" | "branch"
    channel: str | None                # populated for "send" steps
    wait_duration_seconds: int | None  # populated for "wait" steps
    template_key: str | None           # populated for "send" steps — which body+subject to render, e.g. "cold_v1_day0"
    branch_on: str | None              # populated for "branch" steps — the event name gated on, e.g. "email.opened"
    description: str                   # human-readable: "Wait 3 days for open" / "Send breakup email"
```

### Run-scoped detail types

```python
@dataclass
class LeadSnapshot:
    # Denormalized slice of the lead at run-detail load time.
    # Full lead record lives in M2; this is the minimum the timeline UI needs.
    id: str
    first_name: str
    last_name: str
    email: str
    company: str | None
    segment: str | None

@dataclass
class TemplateSummary:
    # Slim view embedded in run detail — avoids a second roundtrip.
    id: str
    key: str
    name: str
    step_count: int
    channels_used: list[str]
```

### GET `/api/automations/runs`

List active + completed automation runs.

**Request:** query params
- `cursor: str | None`
- `limit: int = 25` (max 100)
- `status: str | None` — `"running" | "paused" | "completed" | "failed" | "cancelled"`
- `template_id: str | None`
- `lead_id: str | None`

**Auth:** admin only.

**Response 200:**
```python
@dataclass
class AutomationRunListResponse:
    items: list[AutomationRun]
    next_cursor: str | None
```

**Ordering:** `started_at_unix DESC` (most recent first). Index on `(tenant_id, started_at_unix DESC)` for fast scans.

**Errors:**
- `401 unauthenticated` / `403 forbidden` per Foundation.
- `422 validation_failed` on unknown `status` value.

### POST `/api/automations/runs`

Start a new automation run.

**Request:**
```python
@dataclass
class AutomationRunStartRequest:
    lead_id: str
    template_id: str
    created_by: str | None = None      # optional override; default "admin:<current_admin_uid>"
```

**Auth:** admin only. (Lara tool `automation.start` hits the same service layer, not this REST endpoint.)

**Response 201:**
```python
@dataclass
class AutomationRunStartResponse:
    run: AutomationRun
```

**Behavior:**
1. Validate `lead_id` exists and `template_id` is an active template.
2. Insert `automation_runs` row with `status="running"`, `started_at_unix=now()`, `inngest_run_id=None`.
3. Emit Inngest event: `await inngest_client.send(inngest.Event(name="lead.nurture.start", data={"lead_id": ..., "template_id": ..., "run_id": <our_uuid>}))`.
4. The nurture function's first `step.run("load_lead", ...)` logs a `run_started` event via our timeline API; Inngest's callback back-fills `inngest_run_id` on the row.
5. Return the freshly-inserted run. `current_step_name` is None; first poll will show `run_started`.

**Errors:**
- `404 not_found` — lead or template missing.
- `422 validation_failed` — malformed IDs, template in `status="draft"`.
- `409 conflict` (new code) — an active run already exists for `(lead_id, template_id)`. Prevents accidental dupes. Body carries `details.existing_run_id` so the UI can navigate.
- `502 upstream_failed` — Inngest event emit failed; the DB row is rolled back so we don't orphan a run.

### GET `/api/automations/runs/{id}`

Full run detail, including the ordered event timeline and the lead context.

**Auth:** admin only.

**Response 200:**
```python
@dataclass
class AutomationRunDetailResponse:
    run: AutomationRun
    events: list[AutomationEvent]       # ordered oldest-first by occurred_at_unix
    lead: LeadSnapshot
    template: TemplateSummary
```

**Behavior:**
- Single query pattern: one SELECT on `automation_runs` + one SELECT on `automation_events WHERE run_id = $1 ORDER BY occurred_at_unix ASC` + one SELECT on `leads` + one SELECT on `automation_templates`. Four round-trips, all primary-key or indexed, ~5ms total on demo data.
- `events` is complete and unbounded in V0 — a 5-step cold_outbound run produces 10–20 events including webhooks and retries. No pagination on events; if a single run ever exceeds ~500 events we'll revisit (not expected).
- Timeline is **read from the projection table, not Inngest state**. This is why pause/cancel status updates are eventually consistent — they write a projection event on the request-response path, then Inngest's own cancel confirmation catches up via a follow-up event.

**Errors:**
- `404 not_found` — run doesn't exist.

### POST `/api/automations/runs/{id}/pause`

Pause an in-flight run.

**Request:** empty body.
**Auth:** admin only.

**Response 200:** `AutomationRun` (with `status="paused"`).

**Behavior:**
1. Verify current `status == "running"`. Otherwise `422 validation_failed` with `details.reason = "not_pausable"`.
2. Call Inngest pause API for this run (via `inngest_run_id`). Inngest's pause is function-level, so we implement per-run pause as cancel-and-mark-resumable — we call Inngest's cancel endpoint and set our row's `status="paused"` with a flag for later resume. Resume is V1+ (research memo acknowledged this).
3. Insert `automation_events` row: `step_name="run_paused"`, `channel=None`, `outcome="wait_completed"` (control event), `payload={"actor": "admin:<uid>"}`.
4. Update `automation_runs.status = "paused"`.
5. Return the updated run.

**Errors:**
- `404 not_found` — run doesn't exist.
- `422 validation_failed` — run is already in a terminal state or already paused.
- `502 upstream_failed` — Inngest API call failed. We still write the `paused` event with `outcome="failed"` and `status` remains `running` so retries are safe.

### POST `/api/automations/runs/{id}/cancel`

Cancel an in-flight run. Terminal.

**Request:** empty body.
**Auth:** admin only.

**Response 200:** `AutomationRun` (with `status="cancelled"`).

**Behavior:**
1. Verify current `status in ("running", "paused")`. Otherwise `422 validation_failed`.
2. Call Inngest's `DELETE /v1/runs/{inngest_run_id}` (or `POST /v1/cancellations` for bulk).
3. Insert `automation_events` row: `step_name="run_cancelled"`, `outcome="wait_completed"`, `payload={"actor": "admin:<uid>"}`.
4. Update `automation_runs.status = "cancelled"`, `completed_at_unix=now()`.
5. Return the updated run.

**Errors:**
- `404 not_found` — run doesn't exist.
- `422 validation_failed` — already in a terminal state.
- `502 upstream_failed` — Inngest API unreachable; we do **not** mutate the row in this case. Idempotent retry safe.

### GET `/api/automations/templates`

List the pre-seeded templates.

**Auth:** admin only.
**Request:** no query params.

**Response 200:**
```python
@dataclass
class AutomationTemplateListResponse:
    items: list[AutomationTemplate]
```

**Notes:** V0 is a fixed-size list of three, so no pagination. When the template count crosses ~25 we'll switch to `Page[AutomationTemplate]` — additive change.

### GET `/api/automations/templates/{id}`

Template detail — read-only view of step definition + render previews.

**Auth:** admin only.

**Response 200:**
```python
@dataclass
class AutomationTemplateDetailResponse:
    template: AutomationTemplate
    steps: list[TemplateStep]
    placeholder_schema: list[str]       # e.g., ["lead.first_name", "lead.company", "sender.name"]
    previews: list[TemplatePreview]     # one preview per "send" step, rendered with a canned lead

@dataclass
class TemplatePreview:
    step_order: int
    template_key: str                   # e.g., "cold_v1_day0"
    channel: str                        # "email"
    subject: str | None                 # email subject — None for non-email channels
    body_html: str                      # rendered with the canned preview lead ("Example Inc / Alex Example")
    body_markdown: str                  # original markdown source, for admin copy-editing future work
```

**Behavior:**
- `previews` is computed on-demand (not cached) — the template source is the canonical truth and rendering is cheap.
- For stub channels (WhatsApp/LinkedIn/SMS once templates exist for them), `body_html` is the plain-text body and `subject` is None.

**Errors:**
- `404 not_found`.

### GET `/api/automations/channels`

Channel adapter registry introspection.

**Auth:** admin only.
**Request:** no query params.

**Response 200:**
```python
@dataclass
class ChannelListResponse:
    items: list[ChannelAdapter]
```

**V0 contents (illustrative):**
- `{name: "email", status: "active", provider: "resend", capabilities: ["send", "track_opens", "track_clicks", "webhook_inbound"], note: null}`
- `{name: "whatsapp", status: "stub", provider: "stub", capabilities: ["send_stub"], note: "WhatsApp Business Cloud API adapter scoped; contact team to enable"}`
- `{name: "linkedin", status: "stub", provider: "stub", capabilities: ["send_stub"], note: "PhantomBuster / HeyReach integration pitched; manual onboarding required"}`
- `{name: "sms", status: "stub", provider: "stub", capabilities: ["send_stub"], note: "Twilio adapter ready; plug in customer account SID to enable"}`

**Why this endpoint exists:** the pitch hinges on "pluggable framework." The channels page is the surface that makes the pitch auditable without code — an admin (or a prospect on a screenshare) can see that the stubs are registered at boot, not vaporware. The `note` field is where we put the "how to turn it on" pitch copy.

---

## Behavior notes

### Late-open idempotency

Concrete case: `wait_for_event("wait_open", timeout=3d)` times out, the run sends the breakup on day 3, and the lead opens the email on day 5. Inngest's `wait_for_event` has already resolved `None` and the function moved past that checkpoint — the late `email.opened` webhook **does not rewind the run**. But the webhook still reaches us, and the webhook handler still writes an `AutomationEvent` with `step_name="email_opened"`, `outcome="opened"`, `occurred_at_unix` set to the actual open time (day 5). The timeline renders honestly, in time order:
- day 0: email_sent
- day 3: wait_timed_out
- day 3: breakup_sent
- day 5: email_opened ← appended; status of run unchanged

No workflow rollback. No silent discard. This is the "idempotent opens" guarantee surfaced in both the research memo and the UI. Timeline code MUST sort by `occurred_at_unix ASC` and render every event — never filter out events that arrived after the run's terminal state.

### Pause / cancel event semantics

Pause and cancel both call Inngest's REST API internally (pause via our cancel-and-mark-resumable stopgap, cancel via `DELETE /v1/runs/{id}`). Both also write an `automation_events` row (`run_paused` or `run_cancelled`) on our side, transactionally. The UI reads from the projection, so admin clicks feel instant even if Inngest's own state converges a second later.

If Inngest returns a 5xx, we do **not** mutate the run row — the pause/cancel endpoint returns `502 upstream_failed` and the admin can retry. This preserves the invariant that our projection and Inngest's state are eventually consistent in the direction "admin intent was recorded → Inngest caught up".

### Demo access via Lara, not REST

Demo users (the default anonymous visitor) **cannot** hit any endpoint in this module directly. All admin endpoints return `401 unauthenticated` to demo sessions. Demo users can still *trigger* automations during a demo, but they do so by asking Lara: "start a welcome nurture for Alex at Acme." Lara's tool catalog includes `automation.start`, which calls the same service layer as `POST /api/automations/runs` (shared business logic, not cross-endpoint HTTP). The MCP tool enforces demo budget (tokens + wall clock) like every other Lara tool; it doesn't enforce admin role.

This is why the Channels registry exists as a read-only admin surface: the pitch ("pluggable framework") happens during a live demo where Lara is the interface, and the `/admin/channels` page is what the team opens on their own machine during prep to sanity-check adapter registration.

### Timeline reads from projection, not Inngest

Every `ctx.step.run` in the nurture function ends by calling back into our backend to append an `automation_events` row — the writer discipline. The GET `/runs/:id` endpoint reads that table directly, with zero Inngest roundtrips. This is deliberate:
- UI reads stay under 10ms even with 50+ events.
- The timeline survives an Inngest outage (users still see historical events).
- Event vocabulary stays ours — we're not coupled to Inngest's internal step IDs in the render path.

The only time we reach out to Inngest is for pause/cancel mutations and for the MCP diagnostics tool.

---

## Open questions

1. **Inngest production MCP framing.** The published MCP is positioned as a dev-server tool. Before wiring `automation.inngest_diagnostics` to our prod account, we need to confirm whether self-hosting the MCP against prod is supported or whether we build a thin REST-based proxy ourselves. Ticket for a week-2 spike.
2. **Pause-and-resume fidelity.** Our V0 "pause" is cancel-and-mark-resumable. True resume (reconstituting Inngest function state) is deferred. If the team wants real pause/resume in V0, scope grows by a week. Proposal: ship the stopgap, tell prospects pause is V1.
3. **Active-run uniqueness per (lead_id, template_id).** The `409 conflict` guard prevents accidentally starting two cold_outbound_v1 runs for the same lead. But a lead *might* legitimately receive `welcome_v1` then `cold_outbound_v1` later — we only dedupe within a template. Confirm with the team that the dedupe scope is right.
4. **Preview rendering cost.** `GET /templates/:id` renders every "send" step's email on each call. Cheap today (three templates, one canned lead), but if we add more templates or add a user-selectable preview-lead param, we'll want to cache. Add Redis cache with a 5-minute TTL keyed on `(template_id, preview_lead_id)` if it ever feels slow.
5. **Webhook-triggered event write-through.** When Resend's webhook arrives, we emit an Inngest event (to resolve `wait_for_event`) *and* write an `automation_events` row immediately. Could the Inngest-driven path write a duplicate row later? Mitigation: the writer has an upsert-on-(run_id, step_name, `payload.provider_message_id`) idempotency key. Confirm the idempotency key matches the projection's unique constraint during the M3 build.
6. **Frontend polling vs SSE.** The run detail page polls every 5s. If the timeline feels laggy in demos we can switch to SSE on `/api/stream/automations/:run_id`. Not worth building in V0 — polling is fine for demo-scale traffic.

---

## Gotchas

1. **`inngest_run_id` is populated asynchronously.** When `POST /api/automations/runs` returns, the row exists but `inngest_run_id` is still `None`. A pause/cancel call in the first ~1s may race. Mitigation: the pause/cancel endpoints block up to 2s waiting for `inngest_run_id` to materialize (with a SELECT-poll on the row) before calling Inngest; if it never appears, return `422 validation_failed` with `details.reason = "run_not_ready"`.
2. **Inngest bills per execution, not per step.** Don't optimize step count for cost. Retry count matters — a `send_email` step failing transiently costs more than a 20-step happy-path run. The `EmailAdapter` uses `inngest.NonRetriableError` for 4xx responses so permanent failures don't burn retries.
3. **`wait_for_event` CEL filter must scope by `message_id`.** A bare `event == "email.opened"` filter resolves on *any* email open across the system. Always scope: `if_exp=f'async.data.message_id == "{message_id}"'`. The message_id must be minted inside `step.run` to survive replay.
4. **UUIDs and timestamps outside `step.run` break replay.** Inngest re-invokes the function from the top on every boundary. Any `uuid4()` / `datetime.now()` outside a step produces a different value on replay and breaks memoization. Lint rule in CI: grep the nurture module for unguarded `uuid4|datetime\.now|random\.`.
5. **Timeline must sort by `occurred_at_unix`, not insertion order.** Late webhooks insert rows out-of-sequence. The timeline read already `ORDER BY occurred_at_unix ASC` — don't "optimize" by trusting insert order.
6. **Pause/cancel are not idempotent across state transitions.** Calling `cancel` on an already-cancelled run returns `422`, not 200. The UI must disable the button after a successful cancel; if the admin double-clicks, the second call is expected to fail. Don't "silently succeed" — a later cancel of a *new* run with the same UUID (impossible today, but future race) would be silently swallowed.
7. **Demo time-compression flag is a footgun.** `AUTOMATION_TIME_SCALE=0.001` makes a 3-day wait complete in 4 minutes. Staging and prod MUST assert this is unset at startup. A misconfigured customer pilot would send the entire nurture in one minute.
8. **Cold-outbound ToS warning belongs in the template detail response.** When an admin views `cold_outbound_v1`, the `description` field should include the honest caveat: "Resend's ToS requires recipient opt-in. For true scraped-list outreach, swap in Smartlead or Instantly via the ChannelAdapter registry." Surfacing it here prevents a sales conversation from accidentally pitching cold outbound on our default adapter.
9. **Stub channels return `SendResult(status="stubbed")`.** The timeline's `AutomationEvent` for a stubbed send has `outcome="sent"` with `payload.stubbed = true` and `payload.would_send = {...}`. The UI renders these with a visible "stub channel" badge so a demo viewer is never misled — the framework is real, the channel is not.

---

## Next contracts to write

- **M2 Sales Intel** (if not already drafted) — leads CRUD, kanban, integrations, scraper runs, enrichment. M3 depends on `leads.id` as the lead source.
- **Integrations webhook surface** — `POST /api/webhooks/resend` et al. Not admin API, but M3's timeline correctness depends on webhook handlers writing `automation_events` promptly.
- **M6 Reports** — reads `automation_runs` + `automation_events` for the "nurture performance" dashboard. Fully downstream of M3 contracts.
- **M7 Fintech** — invoices, spend analytics, anomalies. Orthogonal to M3.

# M6 Reports — API Contracts

**Date:** 2026-04-19
**Status:** Draft for team review.
**Depends on:** `docs/specs/api-contracts/foundation.md` (conventions, auth, error shapes, pagination).
**Research:** `docs/research/modules/m6-reports.md`.

M6 is deliberately the **simplest module in the stack**. It is not a BI tool, not a dashboarding framework, not an analytics engine. It is a cron-driven aggregator: once a week an Inngest function runs SQL aggregates across M2/M3/M7, pipes the resulting JSON through Haiku 4.5 for a 2–3 paragraph narrative, and writes one row to `reports`. The admin dashboard reads that table. Lara reads it via `reports__*` MCP tools. That is the whole module.

The contracts below match that simplicity. Five endpoints, four small dataclasses, one deliberately free-form JSONB field, and a handful of behavioral notes pulled forward from the research memo.

---

## Scope

**In this module:**
- List past reports (paginated, filterable by kind + period range).
- Fetch a single report's full payload (stats + narrative + metadata).
- Trigger on-demand generation via an Inngest event, returning a job id.
- Fetch two reports side-by-side for comparison views.
- "Give me the latest weekly" shortcut endpoint.

**Out of scope (handled elsewhere or deferred):**
- The generation pipeline itself — single Inngest function with five `step.run` checkpoints (`resolve_period → aggregate_stats → generate_narrative → embed_narrative → persist_report`). Not an API concern; see research memo.
- Module-specific aggregate functions (`aggregate_leads`, `aggregate_automations`, `aggregate_invoices`). Owned by M2/M3/M7, imported by M6's orchestrator.
- Narrative comparison synthesis — the `compare` endpoint returns two blobs; Lara (LLM) does the diffing. No backend diff structure.
- PDF / CSV export — deferred post-V0 (WeasyPrint is the noted path).
- Slack / email notifications — a future `step.run("notify")` on the Inngest function, no API surface.
- Shareable public-link routes (`/r/shared/:token`) — deferred.

---

## Pages

| Page | Route (frontend) | Purpose |
|---|---|---|
| Reports list | `/admin/reports` | Admin-only. Paginated list of past reports with filters (kind, date range). Each row shows period, kind, headline stats snippet, narrative excerpt. |
| Report detail | `/admin/reports/:id` | Full narrative, Recharts-rendered charts drawn from `stats`, raw-JSON stats inspector, "compare to previous period" toggle that links to the compare view. |
| Report comparison | `/admin/reports/compare?a=:id&b=:id` | Side-by-side stats and narratives. If the admin flips the "synthesize comparison" toggle, the frontend feeds both payloads into Lara for a natural-language diff — backend is not involved. |

All three pages are **admin-only**. Demo users never hit the REST endpoints directly. They can still ask Lara about reports (e.g., "how was last week?") because Lara's `reports__*` MCP tools run server-side with admin-equivalent scope.

---

## Per-page needs & actions

### Reports list (`/admin/reports`)

**On load:**
- `GET /api/reports?limit=25&cursor=...` — paginated list, newest first.
- Optional query: `kind=weekly|daily|monthly|custom`, `period_start_after=<unix>`, `period_end_before=<unix>`.

**Actions:**
- Filter by kind → re-fetch with `kind=` param.
- Filter by date range → re-fetch with `period_start_after` / `period_end_before`.
- Click row → navigate to `/admin/reports/:id`.
- "Generate report now" button → opens a small modal (pick kind + period), then `POST /api/reports/generate`. Modal shows a "Queued — should be ready in 10–30s" state and polls `GET /api/reports/:id` (path built from the newly-created report id once the job completes; see tradeoff note below).

### Report detail (`/admin/reports/:id`)

**On load:**
- `GET /api/reports/:id` — full payload (stats + narrative + metadata).
- For the trend-line charts, optionally `GET /api/reports?kind=<same-kind>&limit=8` to fetch the last N of the same kind — Recharts needs multiple reports to draw a trend line.

**Actions:**
- "Compare to previous period" → resolves the prior report id (via the already-fetched list) and navigates to `/admin/reports/compare?a=<this>&b=<prev>`.
- "View raw stats JSON" → client-side expand of the `stats` dict in a collapsible viewer. No network call.

### Report comparison (`/admin/reports/compare`)

**On load:**
- `GET /api/reports/compare?a=:id&b=:id` — returns both full `Report` payloads in one round trip.
- Alternatively the frontend can call `GET /api/reports/:id` twice in parallel. Both approaches are supported; the compare endpoint exists purely as a convenience + a clean hook for future server-side caching. See the tradeoff note under the endpoint contract.

**Actions:**
- "Ask Lara to synthesize" → feeds both payloads into a Lara chat turn (via `POST /api/stream/chat` from M1) with a system prompt that asks for a comparison narrative. The M6 backend stays out of it.

---

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/reports` | admin | Paginated list with filters (`kind`, `period_start_after`, `period_end_before`) |
| `GET` | `/api/reports/{id}` | admin | Full report detail (stats JSONB + narrative + metadata) |
| `GET` | `/api/reports/latest` | admin | Shortcut for "most recent report of kind X" — avoids list-then-pick round trip |
| `GET` | `/api/reports/compare` | admin | Returns two reports in a single payload for the compare view |
| `POST` | `/api/reports/generate` | admin | Enqueue an on-demand generation; returns `job_id` and fires an Inngest event |

Five endpoints. Matches the research memo's target. Note that **all five are admin-only** — demo users reach the module through Lara's MCP tools, not the REST surface.

---

## Contracts

### Shared types

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class Report:
    id: str                          # UUID
    tenant_id: str                   # UUID; DEFAULT_TENANT_ID in V0 (see Foundation)
    kind: str                        # "weekly" | "daily" | "monthly" | "custom"
    period_start_unix: int           # UTC Unix seconds (V0 policy; see below)
    period_end_unix: int             # UTC Unix seconds; exclusive-end convention
    stats: dict                      # intentionally free-form; see note
    narrative: str                   # 2–3 paragraph LLM-generated prose, <220 words
    prompt_version: str              # e.g., "v1" — rolled into input_hash
    input_hash: str                  # sha256(model_id + prompt_version + stats + prior_stats)
    model: str                       # e.g., "claude-haiku-4.5"
    generated_at_unix: int           # when persist_report step ran
    has_embedding: bool              # True if the pgvector column is populated (embedding itself is not returned)

@dataclass
class ReportGenerateJob:
    id: str                          # UUID; internal job handle
    kind: str                        # "weekly" | "daily" | "monthly" | "custom"
    period_start_unix: int
    period_end_unix: int
    inngest_event_id: str            # returned by inngest_client.send(); lets us correlate for debugging
    status: str                      # "queued" | "running" | "completed" | "failed"
    report_id: str | None            # populated once the persist_report step finishes
    created_at_unix: int

@dataclass
class ReportComparisonResponse:
    a: Report
    b: Report
    # Deliberate non-field: there is no `diff` or `delta` key here.
    # Narrative synthesis of the comparison is Lara's job (LLM on the
    # frontend side, via POST /api/stream/chat). This endpoint is a
    # convenience round-trip saver, not a comparator.
```

**On `stats` being a `dict`.** This is deliberate. Each contributing module (`aggregate_leads`, `aggregate_automations`, `aggregate_invoices`) owns the shape of its slice. A single `aggregate_stats` step merges them under per-module keys (`stats["leads"]`, `stats["automations"]`, `stats["invoices"]`, `stats["prior"]`). Typing this as a strict Pydantic/dataclass model would push every downstream schema change through a breaking contract bump — the whole point of JSONB is forward-compatible module additions. Dashboard code that renders charts reads known keys and no-ops on unknown ones. If any single module's stats shape ever stabilizes to the point of being worth typing, that's a local concern inside `m2/aggregates.py`, not this contract.

**On timestamps.** Foundation's convention is Unix seconds `int`. The research memo floated ISO strings for `period_start` / `period_end` because tenant-local timezone boundaries are a real trap. For **V0 we use UTC Unix seconds** across the board — one timezone, one type, one less edge case. Rendering in the admin's browser timezone is a client concern. When V1 introduces per-tenant schedules, we'll add an optional `period_start_iso` / `period_end_iso` field alongside the Unix ints (additive, non-breaking); we will not swap the int fields out.

---

### GET `/api/reports`

List past reports, newest first, paginated.

**Request:** query params.
- `cursor: str | None` — pagination cursor (opaque; Foundation convention).
- `limit: int = 25` — max 100.
- `kind: str | None` — filter to one of `"weekly" | "daily" | "monthly" | "custom"`.
- `period_start_after: int | None` — Unix seconds; only return reports whose `period_start >=` this value.
- `period_end_before: int | None` — Unix seconds; only return reports whose `period_end <=` this value.

**Auth:** admin only.

**Response 200:**
```python
@dataclass
class ReportListResponse:
    items: list[Report]
    next_cursor: str | None
```

**Behavior:**
- Ordered by `period_start DESC, generated_at_unix DESC`. Tiebreaker matters only during re-seeds.
- Backed by the `(tenant_id, period_start DESC)` index; the `kind` filter hits `(tenant_id, kind, period_start DESC)`.
- Returns the full `Report` shape including `stats`. The list view displays only a handful of keys (`stats["leads"]["new_leads_count"]`, etc.) plus a narrative excerpt, but the full payload is returned because (a) stats is ~2 KB so even 25 rows is ~50 KB, well under a reasonable response budget; (b) it lets the frontend render the detail view instantly when a row is clicked, no round trip.

**Errors:** `401 unauthenticated`, `403 forbidden` (demo cookie hit an admin route), `422 validation_failed` (bad `kind`, malformed Unix seconds).

---

### GET `/api/reports/{id}`

Single report, full payload.

**Request:** path param `id` (UUID).
**Auth:** admin only.

**Response 200:** `Report`.

**Behavior:**
- Plain primary-key lookup, scoped by `tenant_id`.
- The `embedding` vector column is **not** serialized — `has_embedding: bool` tells the frontend whether Lara's `reports__search` MCP tool will find this report, which is the only thing the admin UI cares about. The vector itself is large, opaque, and useless on the frontend.

**Errors:**
- `404 not_found` if id is unknown or belongs to another tenant.
- `401 unauthenticated` / `403 forbidden` as usual.

---

### GET `/api/reports/latest`

"Give me the most recent weekly report" — a one-hop shortcut to avoid a list-then-pick round trip. Used by the admin shell's "what's new" widget and mirrors Lara's `reports__get_latest` MCP tool.

**Request:** query params.
- `kind: str = "weekly"` — one of `"weekly" | "daily" | "monthly" | "custom"`.

**Auth:** admin only.

**Response 200:** `Report`.

**Behavior:**
- Query is `SELECT ... FROM reports WHERE tenant_id = $1 AND kind = $2 ORDER BY period_start DESC LIMIT 1`. Hits the `(tenant_id, kind, period_start DESC)` index.
- Exists as a dedicated endpoint (rather than `GET /api/reports?kind=weekly&limit=1`) for two reasons: (1) it mirrors the MCP tool shape so the backend can share the handler; (2) a `404` on this endpoint is semantically meaningful ("no weekly report exists yet"), whereas the list endpoint returns `{items: [], next_cursor: null}` which the frontend has to disambiguate.

**Errors:**
- `404 not_found` if there are zero reports of that kind.
- `422 validation_failed` if `kind` is outside the allowed set.

---

### GET `/api/reports/compare`

Returns two reports in one payload for the side-by-side compare view.

**Request:** query params.
- `a: str` — first report id (UUID).
- `b: str` — second report id (UUID).

**Auth:** admin only.

**Response 200:** `ReportComparisonResponse`.

**Behavior:**
- Two parallel primary-key lookups, both scoped by `tenant_id`. Either missing → `404`.
- **Deliberately does not compute a diff.** The response is two full `Report` payloads and nothing else. Comparison narrative synthesis happens in Lara — the admin hits a "Synthesize" button, the frontend feeds both payloads into `POST /api/stream/chat` (M1), and Lara's LLM writes the comparison. Pre-computing a diff structure on the backend would be extra code for less flexibility, and an LLM is better at "the lead gen dip came from the holiday, not the campaign change" than any `jsonpatch` output.

**Tradeoff: is this endpoint even necessary?** The alternative is the frontend calling `GET /api/reports/:id` twice in parallel. Arguments for each:

- **Keep the compare endpoint (what we're doing):** one round trip, one obvious place to add server-side caching later (if the same `(a, b)` pair gets hit repeatedly), matches the MCP tool's `reports__compare` shape. Costs: one extra endpoint to document and test.
- **Drop it and let the frontend fan out:** fewer endpoints, frontend is already comfortable with parallel fetches. Costs: two round trips (minor over HTTP/2), no single place to add comparison-specific behavior later.

**Call:** keep the endpoint. It's cheap to implement and cheap to test, and we want the MCP tool's surface to mirror the REST surface for consistency.

**Errors:**
- `404 not_found` if either id is unknown. The response specifies which one in `details.missing_id`.
- `422 validation_failed` if either param is missing or malformed.

---

### POST `/api/reports/generate`

Trigger on-demand generation. Returns a job handle immediately; the actual report appears in `GET /api/reports` once the Inngest pipeline finishes (typically 10–30s end-to-end: SQL aggregates ≈1s, Haiku narrative call ≈8–20s, embedding ≈1s, persist ≈100ms).

**Request:**
```python
@dataclass
class ReportGenerateRequest:
    kind: str                        # "weekly" | "daily" | "monthly" | "custom"
    period_start_unix: int
    period_end_unix: int
```

**Auth:** admin only.

**Response 202 Accepted:** `ReportGenerateJob` with `status == "queued"`.

**Behavior:**
- Validates `kind` and that `period_start_unix < period_end_unix`.
- Computes the would-be `input_hash` up front (same way the Inngest function will) and checks if a row already exists. If yes, returns `ReportGenerateJob` with `status == "completed"` and `report_id` pointing to the existing row — **no LLM call, no Inngest event fired**. This is the caching path that makes re-seeds free.
- If no cached row: publishes `inngest_client.send(Event(name="reports/generate.requested", data={tenant_id, kind, period_start, period_end, job_id}))` and writes a `report_generate_jobs` row with `status = "queued"`. Returns the job.

**Job-status polling vs streaming — open question, documented.**
The frontend needs to know when the job finishes so it can render the new report. Two patterns:

- **Polling (V0 default):** frontend polls `GET /api/reports?kind=<kind>&limit=1` every 3s, compares `period_start_unix` to the requested one, stops when it matches. Simple. Works through any proxy. No new endpoints.
- **SSE stream:** add `GET /api/stream/reports/jobs/{job_id}` that yields `status` transitions. Cleaner UX, fewer round trips, but it's the only streaming endpoint in M6 and we'd be maintaining SSE plumbing for one use case.

Defer the decision. Polling is fine for V0 given the 10–30s end-to-end time; the same `GET /api/reports` endpoint powers the list page anyway, so the polling load is effectively free. If someone builds a live "generation progress bar" that wants per-step visibility (`aggregate_stats` ✓ → `generate_narrative` ✓ → ...), that's the moment to add SSE. Not before.

**Errors:**
- `422 validation_failed` — invalid `kind`, `period_start_unix >= period_end_unix`, or the period is more than 1 year in the past (sanity guard).
- `429 rate_limited` — more than 10 generation requests from one admin in 10 minutes. Prevents a runaway loop from one buggy client from burning a month of LLM budget. Uses `reports:generate:admin:{admin_id}` in Redis.
- `502 upstream_failed` — Inngest `send()` itself failed. Job row is not written in this case; the admin can retry safely.

---

## Open questions

1. **Generation-complete signaling — polling vs SSE.** Polling is the V0 default (as above). If the generation pipeline grows per-step UI (e.g., a live progress bar), switch to SSE. Decide at the moment of need.
2. **`/api/reports/compare` vs parallel `GET /api/reports/:id` calls.** Keeping the dedicated endpoint for MCP parity and future caching. Revisit if the endpoint never gets distinctive behavior.
3. **`has_embedding` in the response — do we also need to expose the embedding dimension or model?** Probably not; the admin UI never uses the vector. Leaving it out keeps the payload small. Lara's `reports__search` tool handles vector math server-side.
4. **Demo access.** Confirmed: demo users do **not** hit `/api/reports/*`. They can still ask Lara about reports via MCP tools (which run with admin-equivalent data scope because the demo is a single-tenant showcase). If we ever need "demo user can see a sanitized weekly report" we'll add a `GET /api/public/reports/sample` endpoint returning a frozen, hand-vetted payload. Not yet.
5. **`period_start_unix` vs ISO string.** V0 picks Unix seconds, matching Foundation. If a tenant-local timezone policy lands in V1, add `period_start_iso` alongside. Do not rename existing fields.
6. **Rate limit on `POST /api/reports/generate`.** Proposed 10/10min per admin. The research memo's caching via `input_hash` means most "generate now" presses on the same period cost zero LLM tokens anyway. The rate limit is belt-and-suspenders against a buggy retry loop, not a cost control. Could be looser.

---

## Gotchas

1. **`stats` is intentionally not typed.** Do not add a `ReportStats` dataclass. Each contributing module's aggregate output is the schema. Typing it centrally here means every M2/M3/M7 aggregate change becomes a breaking M6 contract bump. Keep it `dict`.
2. **`input_hash` must include `prompt_version`.** If we edit the narrative prompt template, bump `prompt_version` so the cache invalidates. Otherwise new prompts ship with old cached narratives. This is enforced server-side in the `generate_narrative` step, but the contract exposes `prompt_version` on every `Report` so debugging is trivial when the team wonders "why does this report still use the old phrasing".
3. **`has_embedding` can be `False` even for fresh reports.** The embedding step is a separate `step.run` and can fail independently (provider flakiness). A report without an embedding still displays fine; it just won't surface via `reports__search`. Admin UI should treat `has_embedding=False` as a soft state, not an error.
4. **`POST /api/reports/generate` short-circuits via `input_hash`.** If the admin clicks "generate now" with the same period twice, the second call returns a completed job with `report_id` pointing at the existing row — no Inngest event, no LLM call. The frontend should not assume a `status == "queued"` response; handle `"completed"` immediately.
5. **`UNIQUE(tenant_id, kind, period_start)` is a hard constraint.** If two Inngest invocations of the cron somehow run concurrently (network partition, retry storm), the second `persist_report` step errors out cleanly. The on-demand endpoint's `input_hash` check avoids the race in the happy path, but the unique constraint is the backstop. Don't swallow it silently — surface as `502 upstream_failed` with `details.reason = "duplicate_period"`.
6. **Demo-vs-admin scoping.** The REST endpoints are admin-only. Lara's MCP tools (`reports__get_latest`, `reports__list`, etc.) run with admin-equivalent scope even when triggered by a demo user — that's fine for V0 because the single-tenant seed data is the same data an admin would see. If the seed ever contains real customer data, this assumption needs a second look.
7. **Period boundaries are exclusive-end.** `period_end_unix` is the **start** of the first excluded second, matching Postgres `timestamptz` range conventions. A "week ending Sunday" has `period_end_unix = next_monday_00:00_utc`. Document this on every field and every aggregate — it's the kind of off-by-one that silently skews "this week vs last week" narratives.
8. **`generated_at_unix` vs `period_end_unix`.** They are not the same and admins will get confused. The weekly cron fires Monday 9am UTC for the week ending the previous Sunday at midnight UTC — so `generated_at_unix` is 33 hours after `period_end_unix`. List views should prefer `period_start_unix` as the primary date label; `generated_at_unix` is a metadata footnote.
9. **`compare` returns two independent payloads, no delta.** Any frontend code that expects `response.diff` is reading the wrong spec. Comparison synthesis is Lara's job.
10. **Do not expose `tenant_id` as a filter.** In V0 there is one tenant. If the endpoint accepted `tenant_id` as a query param, we'd start writing cross-tenant queries before we have cross-tenant auth. Scope via cookie, always.

---

## Next contracts to write

- **M2 Sales Intel** — leads CRUD, kanban moves, integrations OAuth, scraper runs, enrichment. Also owns `aggregate_leads`, which M6 imports.
- **M3 Automation** — timelines, templates, runs, channel registry. Owns `aggregate_automations`.
- **M7 Fintech** — invoices CRUD, spend analytics, anomalies. Owns `aggregate_invoices`.
- **MCP gateway surface** — the machine-readable equivalent of all the above, including `reports__*` tools that mirror these five REST endpoints. Likely a single cross-cutting spec rather than per-module.

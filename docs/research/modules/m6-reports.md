# M6 Reports — Research & Decisions

**Date:** 2026-04-19
**Status:** Research for team review.
**Depends on:** foundation.md, m2 (leads/scrapers), m3 (automations), m7 (invoices) — M6 is a pure consumer of their data.

---

## Summary

M6 is the **simplest module in the stack by design**. It is not a BI tool, not a dashboard framework, not an analytics engine. It is a cron-driven aggregator that:

1. Runs on a schedule (weekly Monday 9am UTC for V0) via the **same Inngest app** that powers M2 scrapers and M3 automations — one system, not a new one.
2. Runs a handful of plain SQL aggregates against M2/M3/M7 tables, producing a stats JSON blob.
3. Feeds that JSON to a **cheap LLM** (Haiku 4.5 or Gemini 2.5 Flash) with a fixed prompt template to produce a 2–3 paragraph narrative.
4. Inserts one row into a `reports` table with stats (JSONB), narrative (text), and an embedding of the narrative for Lara retrieval.

Dashboard reads from this table. Lara reads from this table through `reports.*` MCP tools. Nothing exotic. The demo value is **organic-looking 4–8 weeks of seeded report history** plus Lara being able to talk about trends in natural language — not a chart library flex.

Key decisions below are: narrative model = **Haiku 4.5** ($1/$5 per MTok), chart lib = **Recharts** (matches Vite+React, batteries-included), export = **deferred to post-V0**, PDF (if ever needed) = **WeasyPrint**.

---

## Report generation pipeline

Single Inngest scheduled function. Four sequential `step.run` checkpoints so retries don't duplicate work or re-burn LLM tokens.

```
┌─────────────────────────────────────────────────────────────┐
│ Inngest scheduled fn (cron: "0 9 * * 1" = Mon 9am UTC)      │
│ or TriggerEvent("reports/generate.requested") for on-demand │
└─────────────────────────────────────────────────────────────┘
   │
   ├─ step.run("resolve_period")       → (period_start, period_end, tenant_id)
   ├─ step.run("aggregate_stats")      → stats dict (plain SQL, server-side agg)
   ├─ step.run("generate_narrative")   → narrative text (cached by input hash)
   ├─ step.run("embed_narrative")      → pgvector embedding (1536d / 768d)
   └─ step.run("persist_report")       → INSERT into reports, return row id
```

Each step is a separate durable checkpoint. If `generate_narrative` times out we retry only that step — the aggregates aren't re-run, the LLM call has idempotency via input-hash cache, and the DB insert hasn't happened yet. This is exactly the Inngest pattern the Python SDK documents (`ctx.step.run("name", fn)`).

On-demand generation (Lara "generate a report for me") fires `inngest_client.send(Event(name="reports/generate.requested", data={tenant_id, kind, period}))` from the FastAPI route or MCP tool. Same function handles both triggers — `TriggerCron` and `TriggerEvent` can coexist on one function. Cleanest option is two functions sharing a helper: `weekly_report_cron` and `report_on_demand`, both calling `_generate(ctx, tenant_id, period, kind)`.

Step 4 "notify" is **out of scope for V0**. When we want it, it's another `step.run` at the end posting to Slack / email / Lara push — no architectural change.

---

## Data model

```python
class Report(Base, MappedAsDataclass):
    __tablename__ = "reports"

    id:           Mapped[UUID]       = mapped_column(primary_key=True, insert_default=uuid4)
    tenant_id:    Mapped[UUID]       = mapped_column(ForeignKey("tenants.id"), index=True)
    kind:         Mapped[str]        = mapped_column(String(16))  # "weekly"|"daily"|"monthly"|"custom"
    period_start: Mapped[datetime]   = mapped_column(index=True)
    period_end:   Mapped[datetime]
    stats:        Mapped[dict]       = mapped_column(JSONB(none_as_null=True), default_factory=dict)
    narrative:    Mapped[str]        = mapped_column(Text)
    embedding:    Mapped[list[float] | None] = mapped_column(Vector(1536), default=None)
    input_hash:   Mapped[str]        = mapped_column(String(64), index=True)  # dedup / caching
    generated_at: Mapped[datetime]   = mapped_column(insert_default=datetime.utcnow)
```

**Why stats in JSONB separate from narrative:** the dashboard re-renders charts from `stats` without re-running the LLM. If we only stored narrative, every chart change would require a re-gen. If we only stored charts, Lara would have to re-narrate. Storing both is cheap (narrative is ~300 words, stats is ~2 KB).

**Indexes:**
- `(tenant_id, period_start DESC)` — covers the dashboard list view.
- `(tenant_id, kind, period_start DESC)` — covers "latest weekly".
- `input_hash` — used to short-circuit re-generation during re-seeds.
- pgvector IVFFlat on `embedding` with `vector_cosine_ops` for Lara `compare`/`search` semantics.

**Unique constraint:** `UNIQUE (tenant_id, kind, period_start)` prevents accidental duplicate weekly reports if the cron fires twice.

**Multi-tenancy:** tenant_id is a hard column, every query is scoped. Row-level security optional later; for demo, enforce in app layer.

---

## Aggregation queries

All aggregates are **plain SQL** via SQLAlchemy `text()` or `select()`, not ORM object-graph traversal. Aggregation happens in Postgres, not Python. Python receives rows of scalars and puts them in a dict.

**Per module contribution (V0):**

- **M2 — Leads & scrapers**
  - `new_leads_count`, `new_leads_by_source` (group by source)
  - `avg_lead_score`, `leads_scored_over_threshold`
  - `conversion_rate = converted / new_leads`
  - Scraper runs summary (success/fail counts) — optional
- **M3 — Automations**
  - `automations_run`, `emails_sent`
  - `open_rate`, `reply_rate`, `breakup_count`
  - `top_performing_sequence` (name + metric)
- **M7 — Invoices / finance**
  - `invoices_processed`, `invoices_overdue`
  - `total_spend_this_period`, `spend_delta_vs_last_period`
  - `cash_in` / `cash_out` (if both tracked)
- **M6 self-referential**
  - Prior period's `stats` pulled in so the LLM can write "vs last week" lines without us hand-diffing.

Each module exposes a pure function `def aggregate_<module>(session, tenant_id, start, end) -> dict`. The orchestrator calls each, merges into `stats`. That keeps M6 from knowing table internals — M2/M3/M7 own their own aggregate functions and M6 just imports them. Prevents M6 from becoming a god-module.

**Timezone:** period boundaries are a real trap. V0 policy: store `period_start` / `period_end` as UTC `timestamptz`, render in the tenant's timezone in the dashboard, and make the cron schedule `"0 9 * * 1"` in UTC for demo. Tenant-local cron schedules are post-V0 — Inngest supports per-function cron only, not per-invocation, so multi-tenant local timezones would mean per-tenant functions or a dispatcher that fans out by timezone. Not worth it for V0.

---

## LLM narrative generation

**Model:** **Claude Haiku 4.5** is the V0 default. $1/M input, $5/M output. Per-report cost: ~2 KB input (stats JSON + prior stats) + ~400 token output = well under ₹0.5. At weekly cadence × single tenant × 8 weeks of backfill = rounding error. Fallback = **Gemini 2.5 Flash** ($0.30/$2.50) if we want it cheaper, or route via LiteLLM/OpenRouter per foundation's provider-agnostic posture.

**Prompt template (pinned, versioned):**

```
You are writing a weekly business report for {tenant_name}.

Period: {period_start} to {period_end} ({kind}).
Current stats (JSON): {stats_json}
Previous period stats (JSON, for comparison): {prior_stats_json}

Write exactly three short paragraphs, in this order:
1. What happened — the headline numbers this week, in plain English.
2. What changed vs last week — deltas that matter, not noise. Call out any dip.
3. What to watch — one or two things the operator should pay attention to next week.

Rules: no bullet points, no headings, no emojis, no markdown. Third person, declarative.
If a number is zero or missing, say so honestly — do not fabricate.
Total output under 220 words.
```

**Caching:** compute `input_hash = sha256(model_id + prompt_version + stats_json + prior_stats_json)`. If a row with the same `input_hash` exists for the tenant, reuse its narrative. This matters most during **seed-data re-runs** — every re-seed should not burn LLM tokens re-generating identical narratives.

**Streaming:** not needed. Narratives are short and generated in a cron step. Synchronous call, store the full string, done.

**Guardrails:** the "do not fabricate" line is not a substitute for only passing factual stats. We never pass raw tables — only aggregated numbers. LLM literally cannot hallucinate leads it never saw.

---

## Dashboard rendering

Frontend stack is Vite + React per foundation. Pick: **Recharts** for charts.

Why Recharts:
- Declarative React components (`<LineChart><Line dataKey="leads" />`) — matches the team's React model.
- Built on D3 but hides D3. No imperative chart wrangling.
- Responsive container, tooltips, legends, accessible keyboard nav out of the box in v3.
- 94+ code snippets on Context7, huge community, shadcn charts ship on top of it — no risk of stack mismatch.
- Alternatives considered: Apache ECharts (more powerful, heavier, imperative config), visx (lower-level, more code), Chart.js (canvas-based, less React-native). Recharts wins on fit.

**Views:**

- **List view** (`/reports`): paginated table / cards. Each row shows `period_start → period_end`, `kind` badge, 3–4 headline stats (sparkline optional), first sentence of narrative. Click through to detail.
- **Detail view** (`/reports/:id`): full narrative up top, then `<LineChart>` for lead volume over recent weeks, `<BarChart>` for open-rate-by-sequence, stat cards for headline numbers. All data sourced from the `stats` JSON of this report + last N reports for trend lines.
- **Filter:** time-range chips (last 4 weeks / 3 months / all), kind filter.

**Export:** V0 skips. When it comes in:
- **CSV** = trivial, server-side serialize `stats` flat.
- **PDF** = **WeasyPrint** (HTML→PDF) over ReportLab. WeasyPrint fits because we already have the React/HTML detail view — render it server-side (or clone the layout in a Jinja template) and WeasyPrint spits out a polished PDF with CSS. ReportLab is more powerful but requires coding layouts by hand. For "take the existing report detail page and make it a PDF", WeasyPrint wins. System deps (Pango, Cairo) are fine on the Python worker host.

---

## Lara MCP surface

FastMCP server exposes `reports.*` tools. All tenant-scoped via context (auth middleware injects `tenant_id`, tool handler reads from context, never from args).

| Tool | Args | Returns | Demo line |
|---|---|---|---|
| `reports.get_latest` | `kind?: str` | full report row | "What's the latest weekly report?" |
| `reports.get_by_period` | `start: date, end: date` | report row or null | "Show me the report for March 2–8." |
| `reports.list` | `limit: int = 10, kind?: str` | array of `{id, period, headline_stats, narrative_excerpt}` | "Show me the last month of reports." |
| `reports.compare` | `period1: date, period2: date` | `{report1, report2}` — both full payloads | "Compare this week to the week before." |
| `reports.generate_now` | `kind: str = "weekly"`, `period?: {start, end}` | `{job_id, status: "queued"}` | "Generate a report right now." |
| `reports.search` | `query: str, limit: int = 5` | reports ranked by embedding cosine | "When did we have our best open rate?" |

`reports.compare` deliberately returns both payloads rather than pre-diffing. Lara is an LLM — it's great at synthesizing two report blobs into a comparison narrative. Pre-computing a diff structure is extra code for less flexibility.

`reports.generate_now` publishes an Inngest event and returns immediately. The actual report appears in the list when the cron function finishes. This keeps MCP tool latency low and avoids MCP-over-long-running-job ugliness.

**Demo moment:**
> "How was last week?" → `get_latest` → narrative in voice.
> "Compare to the week before." → `compare` → LLM synthesizes.
> "Generate a report for me." → `generate_now` → "I've kicked it off, should be ready in a moment." (20s later the dashboard updates live.)

---

## Seed data strategy

For the demo to land, we need **4–8 weeks of credible history**, not one report.

**Approach:**
1. Hand-author a 6-week "storyline" — not numbers yet, narrative arcs: "slow start week 1, lead gen picks up week 3, dip in week 4 because of a holiday, recovery week 5, strong close week 6". Organic trends, not monotonic-up hockey-stick. This is 20 minutes with a notebook.
2. Generate stats from that storyline — small Python script seeds plausible ranges for each metric with the arc baked in (`numpy.random.normal` around a target, clamp to zero). Include at least one flat week and one dip week.
3. Run `generate_narrative` against each week's stats (Haiku 4.5). Total cost: ~₹5.
4. **Hand-review every narrative** before demo day — no surprises, no awkward phrasing. If one is bad, tweak the stats or re-roll.
5. Persist via the normal `persist_report` step so the `input_hash` and embeddings are produced the same way real reports are. Re-seeds with the same inputs hit the cache and cost nothing.

**Dates:** backfill with `period_start` = last 6 Mondays before demo day. Always re-run the script before demo to roll the window forward.

**Multi-kind seed:** also seed daily reports for the last 7 days and one monthly. Gives Lara material for all three `kind` values.

---

## Export / sharing (V0 deferred)

Noted here so we don't forget. When the time comes:

- **Shareable link:** signed JWT with `tenant_id + report_id + expiry` as a query param. Route `/r/shared/:token` bypasses auth but scopes strictly to the one report.
- **PDF:** WeasyPrint on the Python worker. Render a Jinja template that mirrors the detail view. Ship as `/reports/:id/pdf` returning `application/pdf`. Cache the bytes on disk keyed by `report_id + updated_at` so regenerating is free.
- **CSV:** server-side flatten of `stats` JSON, one row per metric, expose as `/reports/:id/csv`.
- Email / Slack push: post-generation `step.run("notify")` chaining to M3-style senders.

None of this is on the critical path for a credible demo.

---

## Cron configuration

**V0 (demo):**
- One function `weekly_report_cron`, trigger = `inngest.TriggerCron(cron="0 9 * * 1")` → Monday 9am UTC.
- One function `report_on_demand`, trigger = `inngest.TriggerEvent(event="reports/generate.requested")`.
- Single tenant, single timezone, single schedule.

**Post-V0 options:**
- Per-tenant schedule: store `tenant.report_schedule` (cron string) and `tenant.timezone`. A dispatcher function runs every 15 minutes, reads which tenants are due, fans out events. Don't build this until we have >1 tenant that cares.
- Daily and monthly: another `TriggerCron` per cadence. Cheap to add.

---

## Open questions

1. **Embedding dimension.** 1536 (OpenAI ada-002-style) vs 768 (gte-small / bge-small). If we're already using 1536 for M1 memory, match it. If foundation picks 768 for cost, match that. Decide during Foundation spec.
2. **Tenant timezone for period boundaries.** Easy trap. V0 answer is UTC. Confirm no stakeholder will read a weekly report on Monday morning IST and be confused that it's "only up to Sunday 2:30pm IST". Probably fine for demo audiences.
3. **Should `stats` schema be typed?** Pydantic model for `stats` vs free-form `dict[str, Any]`? Leaning free-form for V0 — module-owned aggregate functions are the schema in practice. Typed schema is a post-V0 refactor if it becomes painful.
4. **Embedding the narrative only, or narrative + stats?** Narrative-only seems enough — `reports.search` is a semantic query over prose. If Lara wants numeric filters ("months where overdue invoices > 5"), that's a SQL query over `stats->>`, not a vector search. Keep narrative-only.
5. **LLM provider for V0.** Haiku 4.5 unless foundation locks Gemini. Either is fine.

---

## Gotchas

- **Don't re-aggregate inside the narrative step.** If `generate_narrative` re-queries the DB, retries become non-deterministic and caching breaks. Stats dict in, narrative out. Pure function.
- **JSONB default.** With `MappedAsDataclass` use `default_factory=dict` not `default=dict` to avoid the SQLAlchemy/dataclass default collision, and pair with `JSONB(none_as_null=True)` so absent sub-keys don't surface as SQL NULL unexpectedly.
- **Input hash must include prompt version.** If we change the prompt template later, bump `prompt_version` so cached narratives invalidate. Otherwise we ship new prompts with old narratives from cache.
- **Cron and DST.** UTC avoids it. Don't put local-time cron into Inngest triggers.
- **Re-seed idempotency.** Seed script must UPSERT on `(tenant_id, kind, period_start)` or DELETE-then-INSERT, not blind INSERT. Otherwise re-seeds blow the unique constraint.
- **Embedding failures.** Embedding provider can be flaky. Wrap in its own `step.run` so retries are cheap, and make the column nullable — a report without an embedding still displays, it just won't appear in `reports.search`.
- **Lara "last month" ambiguity.** LLM will interpret vague periods. `reports.get_by_period` takes explicit dates; Lara is responsible for resolving "last month" → dates before calling. Document that in the tool description.
- **Dashboard charts need multiple reports.** A single report detail page that shows a line chart has to fetch the last N reports' `stats` to plot the trend. Cheap query, but don't forget the endpoint.

---

## Sources

- [Inngest Python SDK — scheduled cron + FastAPI integration](https://context7.com/inngest/inngest-py/llms.txt) (via context7 `/inngest/inngest-py`)
- [Recharts v3 — LineChart / BarChart React patterns](https://context7.com/recharts/recharts/llms.txt) (via context7 `/recharts/recharts`)
- [Anthropic Claude Haiku 4.5 pricing ($1/$5 per MTok)](https://www.anthropic.com/news/claude-haiku-4-5)
- [Claude API pricing docs](https://platform.claude.com/docs/en/about-claude/pricing)
- [Gemini 2.5 Flash pricing ($0.30/$2.50 per MTok)](https://ai.google.dev/gemini-api/docs/pricing)
- [SQLAlchemy 2.0 — MappedAsDataclass & JSONB patterns](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html)
- [SQLAlchemy discussion — JSONB with MappedAsDataclass (insert_default)](https://github.com/sqlalchemy/sqlalchemy/discussions/9575)
- [WeasyPrint vs ReportLab comparison — 2026](https://www.nutrient.io/blog/top-10-ways-to-generate-pdfs-in-python/)
- [pgvector — cosine similarity indexing for narrative embeddings](https://github.com/pgvector/pgvector)
- Internal: [SmartBiz OS technical research — stack decisions](../2026-04-19-tech-research.md)

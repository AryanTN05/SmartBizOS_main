# SmartBiz OS — Technical Research

**Date:** 2026-04-19
**Status:** Research + decisions. Stack committed; module specs still to come.
**Purpose:** Surface architectural options, tradeoffs, and record what the team chose.

---

## Decisions (2026-04-19)

The team chose **Option B (Python-centric)** over the research lean. Reasoning: Python is easier to "connect things" for this team, V0 is not scale-bound, and frontend flexibility matters more than framework integration.

| Layer | Choice |
|---|---|
| Backend | **Python + FastAPI** |
| Frontend | **Vite + React** (separate app, not Next.js) |
| Transport | **SSE for LLM streaming + REST**; WebSockets only for voice realtime |
| Agent framework | **Raw SDK + custom tool loop pattern** — provider-agnostic client (httpx / LiteLLM / OpenRouter) |
| LLM provider | **TBD** — not locked to any one vendor; flexibility preferred |
| Python style | **Stdlib `@dataclass` first.** Pydantic only at FastAPI request/response boundary. SQLAlchemy 2.x `MappedAsDataclass` for ORM. |
| MCP | **FastMCP** per-module servers + **in-house gateway** (~100 lines) — NOT MetaMCP/ContextForge |
| Workflows + cron | **Inngest** (Python SDK) |
| Data | **Postgres + pgvector + Redis** (Upstash / Neon / self-hosted TBD) |
| Doc extraction | **PyMuPDF + Nanonets** (confirmed) |
| Voice | **Cartesia TTS + Whisper STT + MiniMax (Hindi)** — STT→LLM→TTS sandwich, not bidirectional |
| Deploy | **Backend on Google Cloud Run (free, scale-to-zero) + Workers on Cloud Run Jobs + Frontend on Vercel + Object storage on Cloudflare R2** — full V0 = $0/month. Railway/Fly.io rejected (both charge $5+/mo minimum). |
| Auth | **Custom JWT + bcrypt admin-only** (Clerk dropped during API contracts). Demo-session anon + 1-3 admin accounts bootstrapped from env. No sign-up, no tenant isolation. |

**What this changes vs research lean:**
- No Next.js — frontend is plain React + Vite. AI SDK used as a client library (React hooks for streaming), not as a framework.
- Backend emits AI-SDK data-stream protocol so frontend gets chat helpers for free.
- All MCP servers live in FastAPI, no Next.js route handlers. Cleaner ownership.
- Two deploy targets from day one, not a "Vercel-only" fantasy.

**Still open (see §6):**
- LLM provider — Anthropic vs OpenAI vs Gemini vs provider-agnostic (LiteLLM/OpenRouter) — decide before or during M1 spec
- Postgres host: Neon vs Supabase vs self-hosted — decide in Foundation spec
- Redis host: Upstash vs Railway Redis vs self-hosted — decide in Foundation spec
- Backend host: Railway vs Fly.io vs Hetzner — decide in Foundation spec
- Frontend chat UI: AI SDK React hooks + shadcn, or build from scratch, or a library — decide in M1 spec
- Does FastMCP accept dataclasses for tool schemas, or force Pydantic? — verify during Foundation spec; if Pydantic-only, isolate at registration boundary

---

## TL;DR (original research finding — for historical context)

The original assumption was **Django/Flask**. Research says that's wrong — not because Python is bad, but because the *orchestration layer and UI* are what the demo is judged on, and TypeScript/Next.js + Vercel AI SDK is meaningfully ahead there. Python still earns its place, but as **specialized MCP servers** (scrapers, PDF extraction, OCR), not as the spine.

**Recommended architecture (with one open fork):**

- **Spine:** Next.js 16 App Router on Vercel. Vercel AI SDK v6 drives Lara. shadcn/ui + Tailwind for dashboards.
- **Workflows + cron:** Inngest. One system for M3 nurture sequences and the shared cron layer (scrapers, re-scoring, weekly reports).
- **Data:** Neon Postgres (Vercel Marketplace) + pgvector for memory + Upstash Redis for demo-session limits.
- **Python workers:** FastAPI + FastMCP for PyMuPDF/Nanonets doc extraction and Playwright/Scrapy scrapers. Exposed as MCP servers. Deployed off-Vercel (Fly.io / Railway / Hetzner).
- **Auth:** Clerk (Vercel Marketplace, swap later for client deploys).
- **Voice:** Cartesia TTS + Whisper STT. MiniMax for Hindi (Accept-Language routing). Voice is STT → LLM → TTS sandwich, not true bidirectional realtime.
- **MCP topology:** per-module MCP servers + a thin gateway for auth/namespacing/fan-out.

**The open fork:** How much of the AI work lives on the Python side vs the TypeScript side. Described in §2.

---

## 1. What the original plan got right and wrong

### Right
- V0 discipline (demo-worthy, not production) — all three research streams independently agreed this reshapes every tool choice.
- MCP-first architecture — aligns with 2026 ecosystem maturity. FastMCP on Python side, `@ai-sdk/mcp` on TS side, both production-usable.
- PyMuPDF + Nanonets + Cartesia + Whisper + MiniMax picks — all confirmed as right tools for the job.
- Redis-backed demo session gating is correctly specified.

### Wrong or needs revision
- **Django/Flask as default.** Neither is wrong, but both are weaker than FastAPI for this use case, and the *orchestration* layer — the part that actually defines the demo — belongs in TypeScript, not Python. Pushing Django/Flask forces us to rebuild UI credibility Next.js + shadcn already give us.
- **"n8n" as the M3 workflow engine** (from the build guide) — doesn't survive scrutiny. Inngest is a clean fit that also handles the cron layer with zero extra system.
- **Single-deploy mental model.** The "all on Vercel" dream breaks the moment M1 ingests a PDF (Vercel Python runtime is 300s Fluid Compute max and Beta). Accept two deploy targets from day one: Vercel for the Next.js spine, a cheap box for Python workers + long-running jobs.

---

## 2. The open architectural fork

Two honest answers came out of the research:

### Option A — **TS-centric** (my leaning)
Next.js + Vercel AI SDK is the orchestrator. Python exists only as MCP servers for capabilities TS can't do well (PDF extraction, scrapers).
- **Pro:** dashboard-sync is trivial (Server Actions + streaming RSC re-render the same page that ran the tool). Voice via AI Elements is a weekend. Prompt caching, model routing (Haiku→Sonnet), demo-mode middleware — all one-liners.
- **Con:** agent loops, state graphs, and any serious prompt-optimization work are awkward in TS. If the "cross-module reasoning" demo needs sophisticated agent planning (multi-hop tool use with branching), LangGraph-in-Python is a better engine. TS MCP client (`experimental_createMCPClient`) is stable but still carries the `experimental_` prefix.

### Option B — **Python-centric**
FastAPI + PydanticAI owns the agent brain. Next.js becomes a rendering shell that talks to FastAPI via the AI SDK data-stream protocol.
- **Pro:** PydanticAI benchmarks 44% faster P95 with 2.7× lower token use vs LangGraph. Python has the full scraping + ML ecosystem natively. If later we need LangGraph's state-machine explicitness, it's a swap-in.
- **Con:** dashboard-sync now requires round-tripping through FastAPI on every tool call. Voice, model routing, caching — all need extra glue. Two-deploy architecture from day zero. More moving parts = slower V0.

**My lean:** Option A. The demo is 80% UI + conversation feel, 20% agent sophistication. Optimize for the 80%. If a client later needs serious agent work, we pull PydanticAI in as a Python MCP server behind the same gateway and Lara just sees it as more tools.

**Discussion needed:** is that tradeoff acceptable? The cost of being wrong is lower on Option A (add Python later) than on Option B (rebuild the UI/voice layer we'd have gotten for free).

---

## 3. Recommended component map (assuming Option A)

### Core stack
| Concern | Pick | Why |
|---|---|---|
| Frontend framework | Next.js 16 App Router | Vercel-native, RSC + Server Actions pair naturally with AI SDK tool calls |
| UI lib | shadcn/ui + Tailwind | Sharp, customizable, matches fintech credibility requirement |
| Agent framework | Vercel AI SDK v6 | MCP client, streaming, generative UI, Anthropic prompt caching, model routing all first-class |
| Runtime | Vercel Functions (Fluid Compute) | Node 20+, streaming SSE, 300s limit OK for chat turns |
| Auth | Clerk (via Vercel Marketplace) | Fastest V0. Swap for self-hosted on client deploys |
| DB | Neon Postgres (Vercel Marketplace) | One-click, branching, generous free tier |
| Vector | pgvector on Neon | No separate vector DB for V0. RAG over docs + long-term memory both live here |
| Cache + session | Upstash Redis (Vercel Marketplace) | Demo UUID tracking, token counters, rate limits |
| Blob storage | Vercel Blob | Doc uploads for M1 |

### AI / orchestration (Lara / M1)
| Concern | Pick | Notes |
|---|---|---|
| LLM — demo mode | Claude Haiku 4.5 via AI Gateway | ~₹2–8 per session target |
| LLM — authenticated | Claude Sonnet 4.6 or Opus | Routed by session-type middleware |
| MCP client | `@ai-sdk/mcp` | Streamable HTTP transport only. No stdio in serverless. |
| Memory — working | AI SDK message buffer | In-turn only |
| Memory — session | Redis `lara:session:{uuid}` | 1-hour TTL, token counters |
| Memory — long-term | Postgres `lara_memory(kind, content, embedding, source_ref)` | 3 kinds: `fact`, `doc_chunk`, `conversation_summary`. Retrieval via an MCP `recall` tool the model decides when to use — not blind RAG. |
| Voice TTS | Cartesia Sonic-3 (40ms TTFB) | Route `Accept-Language: hi` → MiniMax |
| Voice STT | Whisper (already in stack) | Via AI Elements SpeechInput |
| Voice architecture | STT → LLM → TTS sandwich | NOT bidirectional realtime. Good enough, don't promise sub-500ms barge-in |
| Demo guardrails | Next.js middleware + abort controller on `fullStream` | Pre-emptive token cap must watch deltas mid-stream, not `onFinish` |
| Prompt caching | Anthropic `cacheControl: ephemeral` on system+tools | **Load full tool catalog once at session start. Any mid-session tool change busts the cache and spikes cost.** |

### Workflow + cron (M3 + M6 + M2 scrapers)
| Concern | Pick | Notes |
|---|---|---|
| Engine | Inngest | `step.run` / `step.sleep` / `step.waitForEvent` map 1:1 to nurture pipelines. Crons are first-class. Python + TS SDKs. Official MCP server — Lara sees it as tools. |
| Projection DB | Postgres `automation_runs` + `automation_events` | Source of truth for the visual timeline. Inngest's run state is not queried directly by the dashboard. |
| Channels | Adapter registry (`channels.send(channel, lead, template)`) | Email (Resend) live in V0. WhatsApp/LinkedIn/SMS pluggable. **Build the registry day 1** — retrofitting after WhatsApp lands is painful. |
| MCP surface | `automation.*` tools (wrappers over the projection tables) + passthrough to Inngest's MCP for deep diagnostics | Lara answers "what's running" via wrappers; drills into "why did run 42 fail" via passthrough |

### Python workers (off-Vercel)
| Service | Stack | Why off-Vercel |
|---|---|---|
| Doc extraction | FastAPI + FastMCP + PyMuPDF + Nanonets OCR | PyMuPDF is Python-native, batch extraction is long-running |
| Scrapers | FastAPI + FastMCP + Playwright/Scrapy/Firecrawl | LinkedIn / directory / Product Hunt each need a different tool; Python ecosystem is richer |
| Enrichment | Same worker pod | Multi-step LLM + web fetch, runs async |
| Hosting | Fly.io or Railway or Hetzner $5 box | Avoid Vercel Python Beta limits |
| Queue | ARQ (async-native, FastAPI-idiomatic) | Only for jobs Inngest isn't orchestrating |

### MCP topology
```
Lara (Next.js)
       │
       ▼
[MCP Gateway] ── single endpoint, handles auth + namespacing + fan-out
       │
       ├── /mcp/crm         (Next.js route handlers — native)
       ├── /mcp/automation  (Next.js route handlers — wraps Inngest)
       ├── /mcp/reports     (Next.js route handlers — native)
       ├── /mcp/docs        (Python worker — FastMCP over HTTP)
       ├── /mcp/scrape      (Python worker — FastMCP over HTTP)
       ├── /mcp/hubspot     (third-party MCP server — OAuth)
       ├── /mcp/sheets      (third-party MCP server — OAuth)
       └── /mcp/inngest     (Inngest's official MCP server)
```
Tool names get namespaced (`crm__add_lead`, `docs__search`). Lara sees one catalog. Gateway enforces session UUID → tenant → tool allow-list.

---

## 4. Repo shape (proposed)

Turborepo monorepo:
```
apps/
  web/          # Next.js 16 — Lara, dashboards, MCP gateway + per-module servers
  workers/      # FastAPI + FastMCP — docs, scrapers, enrichment
packages/
  types/        # Generated from FastAPI's OpenAPI (openapi-typescript)
  db/           # Drizzle or Prisma schema shared by web + workers (read-only from workers)
  ui/           # shadcn component registry
docs/
  specs/        # Brainstorming → spec → plan outputs
  research/     # This doc
```

Two deploy targets:
- `apps/web` → Vercel (auto)
- `apps/workers` → Fly.io / Railway (one Dockerfile)

---

## 5. Gotchas to know going in

1. **Vercel Python runtime is a trap for this workload.** 300s Fluid Compute max, 500MB bundle, Beta. Scrapers and OCR batches **will** exceed this. Plan for off-Vercel Python from day one.
2. **SSE through Vercel edge can stutter.** If Lara streaming misbehaves, bypass the edge for `/api/lara-smartbiz/*` or route through AI Gateway.
3. **MCP prompt caching footgun.** Tools come first in Anthropic's cache prefix. Any hot-add of a tool mid-session → cache miss → 10× cost spike. Load the full catalog at session start. Keep it static for the session's 5-minute cache TTL.
4. **`experimental_createMCPClient` naming.** API is stable, name is not. Pin versions. Expect one migration before EOY.
5. **Inngest step determinism.** Code between `step.run` blocks re-runs on replay. Random IDs, timestamps, external reads must live **inside** steps. #1 Inngest footgun.
6. **Voice is not bidirectional.** STT → LLM → TTS. Don't pitch sub-500ms barge-in. Sonic-3's 40ms TTFB still makes it feel realtime.
7. **Token gating is post-hoc by default.** AI SDK gives you usage in `onFinish`. Pre-emptive 2000-token cut needs a counter watching `fullStream` deltas + abort controller. Otherwise the UI timer and actual cutoff will diverge.
8. **MCP stdio doesn't work in serverless.** All module servers must be HTTP/SSE transport.
9. **Channel adapters day 1.** If email is hardcoded into M3 steps, adding WhatsApp later is painful. Registry pattern upfront.
10. **Two env-var surfaces.** Next.js and Python workers each have their own secrets. Use Vercel Marketplace Neon/Upstash from Vercel side, mirror `DATABASE_URL` + `REDIS_URL` into the worker env. Drift will silently break cron.

---

## 6. Open questions for discussion

**Architecture-level:**
1. **Option A vs Option B** (§2). Do we commit to TS-centric, or is there a reason to lean Python-centric?
2. **Do we need LangGraph-class agent planning at V0?** If yes, Option B or Python-as-MCP-server.
3. **MCP gateway — build or buy?** MetaMCP / agentgateway / IBM ContextForge are Q1 2026 options. Or is a 100-line gateway enough for V0?

**Module-specific:**
4. **M2 integrations for V0 — which 2-3?** HubSpot + Sheets + Tally was proposed. Confirm.
5. **M2 scraper scope for V0 — live or mostly seeded?** "Scrape LinkedIn live in a demo" is legally and technically dicey. Seed most, run one live as proof.
6. **M3 — how many nurture templates pre-seeded?** 1 rich template + 2 simple is probably right.
7. **M6 Reports — cron cadence for demo?** Daily or weekly? Seed how many weeks of history?
8. **M7 Fintech — in or out for first demo?** Scope decision affects timeline by ~1 week.

**Infra:**
9. **Auth provider — Clerk or roll our own (NextAuth)?** Clerk is faster; NextAuth is cheaper. Clerk probably wins for V0.
10. **Worker hosting — Fly.io vs Railway vs Hetzner?** Lowest ops preference?
11. **Observability — Logfire for agents, Vercel for frontend. Anything else we need for demo debugging?**

**Demo-mode:**
12. **Per-session cost cap — hard stop at ~₹8 or allow overrun with alerting?**
13. **Seed data generator — LLM-generated or hand-curated?** Hand-curated gives better demo moments but takes a week.

---

## 7. Next steps (suggested)

1. **Decide Option A vs B.** Everything downstream depends on this.
2. **Spec the Foundation module** (auth + DB + deploy + demo session layer + MCP gateway skeleton). Brainstorm → spec → plan.
3. **Pick the 2-3 MCP integrations for M2** and confirm scraper scope.
4. **Decide on M7.**
5. Then spec each module in sequence (M1 → M2 → M3 → M6 → M7?).

---

## Appendix A — Backend stack research (full memo)

### Top Recommendation — Hybrid: Next.js 16 (App Router) on Vercel + FastAPI backend on Vercel Python Runtime + dedicated worker host

**Verdict.** Split deployment. Next.js handles the UI, Lara chat UX via Vercel AI SDK v5, streaming SSE, auth, and marketing surface. FastAPI owns the AI/agent brain, MCP servers, document extraction, scrapers, and cron. Both sit under `demo.zerotoprod.tech` via Vercel rewrites; workers (Celery/ARQ) run on a cheap Fly.io or Railway box.

**Why this wins the V0 demo race:**
- **MCP-first is a Python bet.** MCP's reference implementation, FastMCP (now powering ~70% of MCP servers globally), and `fastapi-mcp` / `django-ninja-mcp` make tool-exposure trivial. PydanticAI is MCP-native, type-safe, and benchmarks 44% faster P95 than LangGraph with 2.7× lower token use.
- **Document + scraping stacks are Python-first.** PyMuPDF, Nanonets OCR, Playwright-Python, Scrapy, ScrapeGraphAI, and Firecrawl's SDK all land cleanly.
- **The demo UI has to look sharp.** Vercel AI SDK v5's `useChat`, streaming UI, generative UI, and shadcn registry give you a polished Lara shell in days, not weeks.
- **Type bridge is solved.** FastAPI's OpenAPI schema → `openapi-typescript` → shared types in the monorepo.
- **Production path is clean.** When you land a real client, peel the FastAPI container onto ECS/Fly, keep Next.js on Vercel.

**Runner-Up:** Pure Next.js + Vercel AI SDK v5. Fastest Lara shell, cleanest single-deploy. But PyMuPDF, Nanonets, Python scraping ecosystem force microservices anyway — "single deploy" breaks on first PDF.

**Losers:**
- **Django + DRF/Ninja.** Admin/ORM/auth optimized for CRUD; you'd fight Django's opinions.
- **Flask.** Sync-first, no competitive async. Dead on arrival for MCP + streaming.
- **Pure FastAPI (no Next.js).** Can't credibly deliver fintech-grade UI.

**Key Gotchas:** Vercel Python Beta 300s / 500MB limit; SSE edge stuttering; `experimental_createMCPClient` risk; two env-var surfaces; Redis demo-gating must be server-checked in both stacks.

**Library picks:** Next.js 16 + shadcn + Tailwind · AI SDK v5/v6 · FastAPI + Uvicorn · PydanticAI + LangGraph (only if needed) · FastMCP + `fastapi-mcp` · SQLModel/Prisma · Neon · Upstash Redis · ARQ (→ Celery later) · Vercel Cron + ARQ scheduler · Playwright/Scrapy/Firecrawl/ScrapeGraphAI · Clerk · Turborepo · Logfire.

### Full sources
- FastMCP, fastapi-mcp, django-ninja-mcp, Vercel AI SDK 5/6 release notes, AI SDK 4→5 migration, Vercel FastAPI docs, Vercel Python runtime limits, Neon+Next+FastAPI 2026 guide, Async Django 2026, PydanticAI vs LangGraph 2026, Speakeasy framework comparison, ARQ vs Celery, Next.js background jobs, Playwright Python vs Node, Firecrawl vs Playwright, Vercel SSE thread, Python AI SDK port.

---

## Appendix B — Workflow engine research (full memo)

### Top Recommendation: Inngest

**Use Inngest as both the workflow engine for M3 and the cron layer for cross-module scheduled jobs.** Primitives (`step.run`, `step.sleep`, `step.sleepUntil`, `step.waitForEvent`) map 1:1 onto M3's nurture pattern. A 3-day sleep consumes zero compute while suspended — true durable execution. Crons are first-class. Python SDK went GA mid-2025; TS battle-tested. Free Hobby tier (50k executions/mo) covers demo at zero cost. **Official Inngest MCP server** — Lara sees workflow state as tools. No stack lock-in.

**Runner-up:** Vercel Workflow DevKit (WDK). GA early 2026, TS + Python-beta. Clean step-based, deterministic replay. Tradeoffs: tighter Vercel coupling + metered billing; no MCP server yet; cron is a separate product (two systems).

**Losers:**
- **Temporal** — over-engineered for V0. $200/mo+ cloud, complex self-host.
- **Celery / BullMQ** — queue libs, not workflow engines. No durable pause/resume.
- **Vercel Cron + rolled-own** / **Postgres + cron + custom** — undifferentiated work.
- **Trigger.dev** — TS-first, Python is subprocess. 5k runs/mo free.

**Data model:** Inngest owns workflow state. Your DB holds the business projection:
- `leads` — canonical FK target
- `automation_runs(id, lead_id, template_id, inngest_run_id, status, started_at, completed_at)`
- `automation_events(run_id, step_name, channel, outcome, occurred_at, payload JSONB)` — append-only, dashboard reads from here
- `channel_adapters` — pluggable channel registry
- `scheduled_jobs` — UI-facing cron descriptors

**Lara integration (2 layers):**
1. `automation.*` MCP tools over your DB: `list_running`, `get_timeline`, `pause`, `cancel`
2. Inngest's official MCP as passthrough for diagnostics: `get_run`, `rerun`, `get_function_logs`

**Gotchas:**
1. Executions-metered, not runs-metered. 5-step × 1000 leads = 5000 executions.
2. Step determinism — code between steps re-runs on replay. Put IDs/timestamps inside `step.run`.
3. Local dev needs `npx inngest-cli dev`. Document it.
4. `step.waitForEvent` timeout returns `null` — must handle explicitly.
5. Channel adapter pattern is your code, not Inngest's. Build day 1.

### Full sources
- Vercel Workflow docs, WDK intro blog, new durable-execution model, WDK pricing
- Inngest pricing, Python SDK, Python quickstart, durable workflows, waitForEvent, crons, fetch run status, Insights, MCP integration
- Trigger.dev v4 GA, Hatchet vs Trigger vs Inngest 2026, Temporal pricing 2026, Temporal self-host benchmark
- Vercel Cron docs, Next.js background-jobs comparison

---

## Appendix C — AI orchestration research (full memo)

### Top Recommendation: Vercel AI SDK v6 on Next.js

**Lock-in: TypeScript / Next.js for the orchestration layer.** Python remains for module-level services (PyMuPDF ingest, scrapers) exposed back to Lara over MCP.

AI SDK v6 (GA Feb 2026) covers every V0 requirement natively:
- Stable `@ai-sdk/mcp` client with stdio, Streamable HTTP, SSE transports + OAuth/elicitation
- `ToolLoopAgent` with `stopWhen` / `stepCountIs` for multi-step reasoning
- Anthropic provider with `cacheControl` (5-min + 1-hr TTL)
- AI Elements SpeechInput/AudioPlayer already wired to Whisper + Cartesia Sonic-3 (40ms TTFB)
- Dual-interface requirement trivially solved: Server Actions + streaming RSC re-render the module that just ran the tool
- Model routing (Haiku→Sonnet) is a provider-registry one-liner
- Demo guardrails plug into Next.js middleware and `onFinish` hooks

**Runner-up:** Claude Agent SDK (TS). Strongest "Lara as Claude Code clone" option. Ships production memory tool, automatic prompt caching, native MCP server hosting (`create_sdk_mcp_server` in-process), hooks, session resume. **Tradeoff:** Anthropic-only (no Haiku→other fallback), voice not in SDK, streaming tool calls to web needs more glue.

**Losers:**
- **LangGraph** — Python, forces two-process architecture, overkill for V0.
- **Raw SDK + DIY MCP** — reinventing tool loops / caching / SSE wrong for timeline.
- **DSPy** — optimization-first, no eval set.
- **Pydantic AI** — Python-only, immature TS port, same dashboard penalty.
- **Instructor** — structured output only, not orchestration.

**Memory architecture (3 tiers):**
- **Working (in-turn):** `messages[]` in `streamText`. Not persisted.
- **Short-term session:** Redis `lara:session:{uuid}`, last N turns + token counters, TTL 1hr, session_id for resume.
- **Long-term (per tenant, authed):** Postgres `lara_memory(tenant_id, kind, content, embedding, source_ref, created_at)`. 3 kinds: `fact`, `doc_chunk`, `conversation_summary`.
- **Retrieval:** not blind RAG. Lara calls `recall(query, kind?, k?)` as an MCP tool — model decides relevance. Mirrors Anthropic memory-tool pattern, keeps system prompt static (cache-friendly).
- **Write path:** session-end background function summarizes transcript, extracts facts via Haiku + Zod validation, upserts.

**MCP topology: per-module servers + gateway.** Each module ships `/api/mcp/{module}` route handlers (Streamable HTTP). Gateway fans out `tools/list`, namespaces (`crm__add_lead`), enforces auth. Third-party MCP (HubSpot, Sheets, Tally, Vercel MCP) mount into same gateway with OAuth at registration.

**Gotchas:**
1. **MCP tool-list changes invalidate cache.** Tools come first in Anthropic's cache prefix. Load full catalog at session start, keep static for 5-min cache TTL.
2. **`@ai-sdk/mcp` still `experimental_`.** API stable, name not. Pin versions, expect one migration.
3. **Voice is sandwich, not realtime.** STT → LLM → TTS. Don't promise sub-500ms barge-in.
4. **Serverless + stdio MCP don't mix.** HTTP/SSE transport only.
5. **Token gating is post-hoc.** `onFinish` returns counts. For pre-emptive 2000-token cap, watch `fullStream` deltas + abort controller. Test that UI timer matches actual cutoff.

### Full sources
- AI SDK 6 (Vercel), AI SDK MCP docs, Agents loop control, Anthropic provider + cacheControl
- Swift template (Groq+Cartesia+VAD+AI SDK), AI Voice Elements changelog, Cartesia Sonic-3
- Claude Agent SDK overview, memory tool docs, claude-agent-sdk-python, prompt caching docs
- LangGraph overview, MongoDB long-term memory, Pydantic AI MCP
- Q1 2026 MCP gateway survey, Composio top-10 gateways, Speakeasy framework comparison, 2026 agent framework decision guide

---

## Update — 2026-04-30 — Hosting re-research (no-credit-card path)

The 2026-04-19 deploy decision (Cloud Run + Neon + Vercel + R2) is technically still correct — Cloud Run free tier is real, the limits haven't moved (2M req/mo, 180k vCPU-sec, 360k GiB-sec). But Cloud Run **requires a credit card on file** for identity verification (a $1 hold, not a charge) and the team flagged that as a real blocker. Re-ran the survey for no-CC alternatives.

**Verified-killed since 2026-04-19:**
- **Koyeb** — acquired by Mistral AI on 2026-02-17. Free tier closed to new signups (existing users grandfathered). Would have failed on 100s timeout anyway.
- **Fly.io** — no free tier for new orgs (removed 2024, no reinstatement). 2-hour or 7-day trial then paid.
- **Hugging Face Spaces (Docker SDK)** — no CC required, but the HF infra proxy enforces a **~60-second hard timeout** on every request that isn't user-configurable on free CPU Basic. Kills LLM agent loops and SSE chat.
- **Railway** — no permanent free tier, $5 one-time credit then $5/mo minimum.
- **Modal Labs** — $30/mo recurring credits but designed for serverless functions, not persistent WebSocket servers. Wrong shape.

**Verified-alive and viable:**

| Stack | CC required | Long requests | WebSocket | Sleep | Custom domain on free | Verdict |
|---|---|---|---|---|---|---|
| **Cloud Run + Neon** | yes | 60min | yes | cold start | yes | original pick — best with CC |
| **Render + Neon** | **no** | 100min | yes | 15-min idle | **no** (`*.onrender.com` only) | **best no-CC pick** |
| Oracle ARM + Neon | yes (idiosyncratic) | unlimited (bare VM) | yes | none | yes | capacity-lottery + CC + setup heavy |
| Aiven (Postgres only) | no | n/a | n/a | none | n/a | sleeper Postgres pick if Neon limits bite |

**New recommendation:**
- **No-CC path (default if any team member lacks a card):** Render free + Neon free + Vercel hobby + Cloudflare R2. Wakes from sleep in ~30s; UptimeRobot free tier ping every 14 min keeps it warm during demo windows. Custom domain (`demo.zerotoprod.tech`) requires Render's $7/mo Starter — accept the `*.onrender.com` URL until the demo books revenue, then upgrade.
- **With-CC path:** Cloud Run + Neon (unchanged from 2026-04-19).

`backend/Dockerfile` works on both targets unchanged. `render.yaml` (added 2026-04-30) lets `git push` deploy. `make deploy-render` and `make deploy-backend` (Cloud Run) are both wired.

**Keep watching:**
- Render cold-start trend — if 30s creeps up, switch to UptimeRobot ping or accept the $7/mo for paid tier.
- Neon 0.5GB ceiling — current seed + production demo data fits comfortably; scrape-heavy workloads may push it.
- Aiven Postgres free tier as a Neon backup if Neon ever pauses or tightens limits.

**Sources (2026-04-30 re-verification):**
- [Cloud Run pricing](https://cloud.google.com/run/pricing), [GCP Free Program](https://cloud.google.com/free/docs/free-cloud-features), [GCP signup CC FAQ](https://cloud.google.com/signup-faqs)
- [Render free docs](https://render.com/docs/free), [Render Docker docs](https://render.com/docs/docker), [Render WebSockets](https://render.com/docs/websocket)
- [Neon plans](https://neon.com/docs/introduction/plans), [Aiven free tier](https://aiven.io/free-tier)
- [Koyeb-Mistral acquisition](https://www.koyeb.com/blog/koyeb-is-joining-mistral-ai-to-build-the-future-of-ai-infrastructure), [Fly.io pricing](https://fly.io/docs/about/pricing/)
- [HF Spaces 60s timeout thread](https://discuss.huggingface.co/t/504-gateway-timeout-with-http-request/24018)

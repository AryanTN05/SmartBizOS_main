# M0 Foundation — Research & Decisions

**Date:** 2026-04-19
**Status:** Research for team review. Not final spec.
**Depends on:** `docs/research/2026-04-19-tech-research.md` (stack-level decisions)

> **⚠️ Auth revised after this research was written.** Clerk was the original V0 pick; during API contract work the team simplified to custom JWT + bcrypt with 1–3 admin accounts bootstrapped from env (no public sign-up, no multi-tenant, no session-adoption). See `docs/specs/api-contracts/foundation.md` for the authoritative auth model. The hosting picks below still stand.

---

## Summary

- **Monorepo** with `apps/api` (FastAPI), `apps/web` (Vite + React), `packages/shared-types` (generated). Single repo, two deploy targets.
- **uv** for Python dependency + venv + Python-version management. It is the 2026 default; Poetry is the only serious alternative, and its only win (publishing polish) does not apply to a non-library repo.
- **Hosting pick:** Neon Postgres (free tier, pgvector, branching) + Upstash Redis (free tier) + **Google Cloud Run** (free, scale-to-zero) + Vercel frontend (free) + **Cloudflare R2** (free, zero-egress object storage). Total cost at demo scale: **$0/mo**. LLM cost handled via free-tier providers (Groq, OpenRouter free models) or team-provided keys.
- **Auth: Clerk** stays. It works fine with Vite + React on the frontend and FastAPI on the backend (JWT bearer + JWKS). Demo-mode anonymous sessions live outside Clerk in Redis; upgrade path copies demo data to Clerk `user_id` at sign-up.
- **MCP gateway:** ~100-line FastAPI router using the FastMCP `create_proxy(mcpServers=...)` composite-proxy primitive. Namespacing and `tools/list` fan-out come for free in FastMCP 3.0.
- **Demo session middleware:** FastAPI `BaseHTTPMiddleware` sets a UUID cookie, tracks `{started_at, tokens_used, last_message_at, ip}` in Redis with 1h TTL, enforces 5-min / 2000-token / 1-per-IP-per-hour. Token accounting is pre-emptive via abort pattern wired into the streaming layer.

---

## Recommended hosts

| Component | Pick | Cost at V0 | Why |
|---|---|---|---|
| Postgres + pgvector | **Neon** free tier | $0 | Serverless, pgvector native, scale-to-zero, instant copy-on-write branching. 0.5GB storage + 190 compute hours free. |
| Redis | **Upstash** free tier | $0 | 10K commands/day. REST client (no VPC needed between Cloud Run and Vercel). Sliding-window rate-limit lib. |
| Backend (FastAPI + MCP servers + Inngest serve endpoint) | **Google Cloud Run** free tier | $0 | Scales to zero. 2M requests + 360K vCPU-seconds + 180K GiB-seconds free/mo. Accepts Docker (heavy deps OK for PyMuPDF/Playwright). 60min request cap handles SSE + long agent loops. |
| Workers (scrapers, doc extraction) | **Cloud Run Jobs** triggered by Inngest | $0 | Same free pool as the web service. Batch-oriented; no always-on cost. |
| Frontend | **Vercel** Hobby | $0 | Vite preset, preview deploys per-PR, global CDN (matters for ME/India). |
| Object storage (docs, uploaded files) | **Cloudflare R2** free tier | $0 | 10GB storage + **zero egress fees anywhere**. S3-compatible API via `boto3`. Beats Vercel Blob and GCS for a globally-served demo. |

**Why Cloud Run beats Railway at V0.** Railway's Hobby plan starts at $5/mo flat (no free tier since 2023). Cloud Run is genuinely $0 until demo scale ~2M requests/mo — orders of magnitude beyond what a live-for-the-team demo burns. Cloud Run accepts Docker (so PyMuPDF, Playwright binaries, Nanonets client ship in the same image), handles SSE up to 60 minutes, and scales to zero when nobody's testing. The only real cost is **cold starts** (2–10s on a cold container) — mitigated with a free Inngest cron pinging `/healthz` every 10 minutes to keep one warm instance around during demo hours.

**Why not Fly.io:** Fly killed its free tier in 2024. Minimum production setup is ~$10–20/mo always-on. No longer viable for a "don't pay a penny" V0.

**Why not Hetzner for V0:** Cost winner at scale (CPX22 at €7.99/mo), but someone has to run Traefik/Caddy, manage TLS, patch the OS. For a demo that must be up in weeks, the ops tax isn't worth it. Revisit when a paying client has sustained traffic.

**Why not Render:** Free tier exists (750 hrs/mo) but spins down after 15 min inactivity and the cold-start path is clunkier than Cloud Run's. Also no job-style batch primitive comparable to Cloud Run Jobs.

**Why not Supabase:** Full-platform bet (auth + storage + realtime + Postgres) and we chose Clerk. Supabase Postgres is fine but branching is slower than Neon's CoW clones and the $25/mo floor triggers sooner. Neon is cleaner as database-only.

**Why Cloudflare R2 over Vercel Blob / GCS:** R2 is 10GB free (2× GCS) with **zero egress fees globally** — big deal when the demo serves files to US/EU/ME/India. GCS is 5GB + US-regions-only for the always-free tier, and egress to non-US backends is billed. Vercel Blob is fine but limited and costs add up past the free allotment. R2 via `boto3` is drop-in.

---

## Monorepo & tooling

**Layout:**

```
apps/
  api/                     # FastAPI + FastMCP servers + Inngest functions
    pyproject.toml         # uv-managed
    src/smartbiz/
      config.py            # dataclass config read from os.environ
      app.py               # FastAPI factory
      db.py                # SQLAlchemy 2.x engine + session
      middleware/          # demo_session, rate_limit, logging
      mcp/                 # gateway + per-module FastMCP servers
      modules/             # crm/, docs/, automation/, reports/
      inngest_app.py       # Inngest function registry
  web/                     # Vite + React + TS
    package.json
    src/
      client/              # generated from OpenAPI — gitignored
      components/
      routes/
packages/
  shared-types/            # OpenAPI JSON + generated d.ts (committed for easy diff review)
docs/
  specs/
  research/
docker-compose.yml         # Postgres + Redis + Inngest dev server
.github/workflows/         # ci.yml, deploy.yml
```

**Python package manager: uv.** Non-negotiable pick. Benchmarks show 10–100× faster than pip, 3× faster than Poetry on realistic dependency sets. uv replaces pip, pip-tools, pipx, poetry, pyenv, virtualenv, and twine in a single tool — meaning a new contributor runs `uv sync` and has the right Python version, the venv, and the lockfile-resolved deps in one command. Poetry's only remaining advantage is publish-to-PyPI polish, which we don't need. pip-tools is viable but is two tools (`pip-compile` + `pip-sync`) for what uv does in one, with no Python version management. Rye is effectively deprecated (merged into uv). This is the 2026 default.

We avoid **Poetry's Pydantic-style plugins** and anything that nudges us toward Pydantic-Settings (stack says no). `pyproject.toml` stays minimal: `[project]` metadata, `[tool.uv]` dev-dep groups, `[tool.ruff]`, `[tool.mypy]`.

**Type sharing (Python → TypeScript):** FastAPI already emits OpenAPI at `/openapi.json`. On the frontend side we use **@hey-api/openapi-ts** with `@hey-api/vite-plugin`. Hey API is the current 2026 leader (used by Vercel, OpenCode, PayPal), successor to `openapi-typescript-codegen`, supports Zod schemas, TanStack Query hook generation, and direct Vite integration.

- Dev flow: `vite dev` hits the Vite plugin, which reads `http://localhost:8000/openapi.json` and regenerates `apps/web/src/client/` on change.
- CI flow: pre-commit runs `hey-api generate` against a committed `packages/shared-types/openapi.json` (snapshot from last known-good backend). Drift shows up as a diff in the PR. This pattern catches "backend shipped, frontend didn't" at review time.
- We do **not** hand-write TypeScript types that shadow Python dataclasses. If a type is used by both, it lives in FastAPI's Pydantic response model (the one place Pydantic is allowed), gets exported via OpenAPI, and flows to TS automatically.

---

## Auth

**Pick: Clerk.** Confirmed the V0 pick from the stack research.

**Why Clerk survives scrutiny against a Vite + FastAPI stack:**

- Clerk's `@clerk/clerk-react` works identically in Vite and Next.js — it is a React library, not a Next.js framework plugin. Netlify's guide for Vite + Clerk + React is well-trafficked and there's nothing in it that requires Next.
- Frontend flow: `<ClerkProvider>` at the root, `useAuth()` gives `getToken()`, that token goes in `Authorization: Bearer <jwt>` headers to FastAPI.
- Backend flow: FastAPI dependency validates the JWT against Clerk's JWKS endpoint (networkless after first fetch). `fastapi-clerk-auth` (or a 20-line custom dep using `httpx` + `python-jose`) extracts `user_id`, `org_id`, and session claims.
- Cost: Clerk's free tier covers 10K MAU — we will not approach this at V0.

**Alternatives considered and rejected for V0:**

- **Rolling our own (FastAPI + cookies + bcrypt + email verification).** Cheap, no lock-in, but costs ~1 week of build time we don't have. Revisit for first paying client if Clerk becomes an issue.
- **Supabase Auth.** Couples us to Supabase Postgres. We picked Neon.
- **NextAuth / Auth.js.** Next.js-flavored. Works with any backend in theory, but we'd be fighting the docs and the examples for a Vite setup. Not worth the drag.
- **Authelia.** SSO / IdP-flavored, overkill.

**Anonymous demo sessions — the interesting part.** Clerk does not natively support anonymous-to-authenticated upgrade flows the way Firebase Anonymous Auth does (Clerk has a "guest users" beta but it's 2-legged OAuth flavored, not "unauthenticated visitor"). We treat demo sessions as entirely separate from Clerk:

1. **Demo session** = a UUID cookie, lives in Redis, no Clerk involvement. Routes requiring a demo session use a FastAPI dependency that reads the cookie and hydrates from Redis.
2. **Authenticated session** = a Clerk JWT. Routes requiring auth use the Clerk dep.
3. **Both deps available on a route**: some endpoints (like the Lara chat endpoint) accept either, and dispatch logic chooses which rate-limit / token-cap policy applies.
4. **Upgrade path**: when an anonymous user signs up, frontend sends `X-Demo-Session-UUID` alongside the new Clerk token on their next request. Backend checks "do we have a Redis entry for this UUID and is it ours to adopt?" → if yes, copy any `leads`, `uploaded_docs`, `conversation_transcripts` from the demo namespace into the Clerk-user namespace, then delete the Redis entry. If no, nothing to do.

This keeps Clerk's model clean (every Clerk user is a real user) and gives us the demo → account conversion path for free, implemented in roughly 40 lines of Python in one place.

---

## MCP gateway sketch

**What's in the ~100 lines.** Single FastAPI router mounted at `/mcp`. The router holds a singleton `FastMCP` composite proxy built at startup from `create_proxy(mcpServers={...})`, where `mcpServers` comes from our module registry (`settings.mcp_modules`). FastMCP 3.0 handles the hard parts: namespace-prefixing tool names (`crm__add_lead`, `docs__search`), aggregating `tools/list`, routing `tools/call` to the right downstream server, and session management for per-module clients.

**Routes (prose):**

- `POST /mcp` — primary MCP endpoint. Streamable HTTP transport. The gateway's job before delegating to the FastMCP proxy: (a) extract session (Clerk JWT OR demo UUID), (b) resolve `tenant_id`, `role`, and `allow_list` from Postgres / Redis, (c) stuff these into a `ContextVar` so per-module handlers can read them without threading kwargs, (d) pass the request through to `FastMCPProxy.handle_request()`.
- `GET /mcp/tools` (debug-only) — calls the proxy's `list_tools()` directly, returns the namespaced catalog. Useful for checking which tools Lara sees in a given session.
- `GET /mcp/health` — pings each downstream module server in parallel with a 2s timeout. Used by CI and uptime checks.

**Data shape of a gateway request** (conceptual, not wire format): `{session: {uuid | user_id, tenant_id, role, allow_list}, mcp_request: {method, params}}`. The session half gets set in middleware; the MCP half is whatever Lara's client sends. When a request reaches the downstream FastMCP server, our module code reads session via `ContextVar` rather than trusting any field the client sent.

**Allow-list enforcement.** FastMCP 3.0's "Transforms" let you wrap a proxy with a filter that mutates `tools/list` and rejects `tools/call`. We apply one transform per request based on the session's role (e.g., demo sessions see only `crm__*`, `docs__*`, `reports__*` — no `automation__*` or `hubspot__*` because those could send real emails or mutate live systems).

**FastMCP verification (via context7):** Confirmed — `fastmcp.server.create_proxy()` accepts either a URL or a `{"mcpServers": {...}}` config dict and returns a composite server with automatic namespacing. This is the exact primitive we need; we are not writing 100 lines of HTTP fan-out code ourselves, we are writing 100 lines of **glue** (session extraction, role-based transforms, FastAPI integration). FastMCP takes the protocol.

**Does FastMCP force Pydantic for tool schemas?** Open question from the stack doc. Verified: FastMCP uses Python type hints for schema inference — plain stdlib types, `@dataclass`, Pydantic models, and `TypedDict` all work. No Pydantic lock-in. Our CRM tools can use `@dataclass` arguments; FastMCP will schema-generate correctly.

---

## Demo session middleware

**Shape.** Single `BaseHTTPMiddleware` subclass registered before the route layer. Short-circuits `/healthz`, `/openapi.json`, and authenticated routes (detected by presence of Clerk bearer token).

**Lifecycle per request:**

1. Read `demo_session` cookie. If missing, mint a new UUID, `SET` the cookie (HttpOnly, SameSite=Lax, 1h expiry), and write `demo:session:{uuid}` to Redis with `started_at=now(), ip=client.host, tokens_used=0, last_message_at=null`, TTL 3600s.
2. Rate-limit check (new sessions only): `INCR demo:ratelimit:ip:{ip}`; if result > 1 within the 3600s window, return 429 with `Retry-After` header. Key TTL set only on creation with `SET NX EX 3600`.
3. Wall-clock check (existing sessions): if `now - started_at > 300s`, return 402 `{"error": "demo_expired"}`. Frontend shows "sign up to continue" CTA.
4. Token check: if `tokens_used >= 2000`, same 402 flow with a different error code so UI can message differently.
5. Attach session dict to `request.state.demo_session` and proceed.

**Data shape in Redis** (`demo:session:{uuid}` is a hash):
```
started_at        → ISO8601 timestamp (int unix ts is simpler; use that)
tokens_used       → int, incremented as chunks stream
last_message_at   → unix ts
ip                → string
transcript_keys   → JSON array of s3/blob keys for uploaded docs, for cleanup
```

**Pre-emptive token accounting under streaming.** This is the subtle part.

The LLM provider will stream chunks. We do **not** wait for `on_finish` — by then we have already burned the tokens we're trying to prevent. The pattern:

1. The Lara chat endpoint wraps the provider stream. On each delta, it calls the provider's token-counter (or a rough char-count approximation for providers that don't stream token counts; acceptable for V0) and increments `tokens_used` in Redis (`HINCRBY`).
2. The streaming handler holds an `asyncio.Event` (`abort_event`). After each chunk, it checks `tokens_used >= 2000`. If true, it `abort_event.set()`, which the provider client library (LiteLLM, httpx) is passed as a cancellation token and which closes the upstream HTTP stream.
3. The SSE stream to the browser sends a final `event: demo_cutoff` frame, then closes. Frontend renders the "sign up to continue" state.

**Why this is correct for SSE + FastAPI.** FastAPI streaming responses support yielding until the generator returns. We use `asyncio.wait_for` around each provider delta with an `asyncio.shield` / abort-event pattern; standard async-Python, no exotic primitives.

**Why not just check in `on_finish`.** Because the point of the 2000-token cap is to **cap cost**, not cap reported usage. Post-hoc limiting means the tokens are already billed. A 10× prompt-injection attack ("write an essay of N pages") will steal $ before `on_finish` fires.

---

## Seed data pipeline

**Recommendation: hybrid, heavily Faker-weighted with LLM polish.**

- **Leads (~150 seed rows).** Use `Faker` with locale variation (`en_US`, `en_GB`, `hi_IN`, `ar_AE`) to match our target regions. Faker generates names, companies, emails, phones, addresses deterministically with a seed — reproducible across deploys. Score, status, source, and last-activity fields are sampled from hand-tuned distributions (70% "new/contacted", 20% "qualified", 10% "closed", etc.) so demo filtering looks realistic.
- **Document corpus (~8 docs).** Hand-curated. This is what Lara answers questions *about*. Can't be Faker'd. Four pitch decks, two contracts, one pricing sheet, one FAQ — all written specifically to have "interesting" Lara-findable facts (e.g., "notice period in the MSA is 60 days", "our MRR target is $50K"). Cost: ~4 hours of one person's time. Quality: makes or breaks the demo.
- **Automation histories (~30 runs).** Faker for lead_id + channel + timestamp, but the `payload` JSONB column uses a small hand-crafted library of ~6 realistic email copy snippets. Purely deterministic.
- **Report history (~8 weeks).** Fully generated by running the actual report aggregation against seeded leads. Tests the pipeline, produces real-looking charts.
- **Lara conversation starters (~5 example sessions).** LLM-generated once, hand-edited, committed as fixtures. These power the "here's what previous users asked" UI on the Lara home screen.

**Re-seedable.** Yes — `uv run python -m smartbiz.seed reset` wipes and re-seeds deterministically. Included in CI's preview-environment startup so every Neon branch gets the same data. Production seeds idempotently (only runs if the `seed_version` row in a `meta` table is older than the current code's version).

**Cost of LLM generation over Faker.** Faker is free and instant. LLM generation of 150 leads via Claude Haiku would cost ~$0.15 and take 30 seconds, but produces inconsistent output (Faker's `seed(42)` always gives the same Sarah Johnson from Acme Corp; LLMs drift). We reserve LLM for the 5 conversation starters where authenticity matters; everything else is Faker.

---

## Secret management

**Pattern:** `os.environ` + `python-dotenv` (loaded conditionally in dev only) + a plain `@dataclass` config object read at startup.

**Structure:**

- `apps/api/.env` — gitignored, loaded by `python-dotenv` only when `SMARTBIZ_ENV=dev`.
- `apps/api/.env.example` — committed, lists every key with a dummy value so a new dev knows what's needed.
- `apps/api/src/smartbiz/config.py` defines `@dataclass(frozen=True) class Settings` with typed fields (`database_url: str`, `redis_url: str`, `clerk_secret_key: str`, etc.). A `Settings.from_env()` classmethod reads `os.environ`, validates required keys present (raises on first missing), and returns the instance. Imported once at FastAPI startup, stashed on `app.state`.
- **Production:** Cloud Run env vars set via `gcloud run services update --set-env-vars` or the GCP console. For sensitive values (API keys), **Google Secret Manager** — mount secrets as env vars at deploy via `--update-secrets`. No `.env` file on the production filesystem. The same `Settings.from_env()` code reads `os.environ` directly. `python-dotenv` is a no-op in prod.
- **Vercel:** environment variables for the frontend (Clerk publishable key, API base URL, Inngest app ID if exposed).

**Zero Pydantic Settings.** Intentional per stack doc. The dataclass-with-from_env pattern is 30 lines, type-safe, and composable with `@property` for derived values (e.g., `is_dev = environ == "dev"`).

**Rotation.** Document which secrets are rotatable vs rebuild-required. Clerk keys roll from their dashboard with zero downtime. LLM provider keys rotate via `gcloud run services update --update-secrets` without a rebuild. Database URLs are stable; cycling Neon credentials is a Neon-console operation.

---

## CI/CD

**GitHub Actions, two workflows, no more:**

**`ci.yml` (runs on every PR):**
- `uv sync` → `uv run ruff check` → `uv run ruff format --check` → `uv run mypy apps/api/src` → `uv run pytest -q`
- `cd apps/web && pnpm install` → `pnpm typecheck` → `pnpm lint` → `pnpm test` (if we have any)
- `hey-api generate` against a committed `packages/shared-types/openapi.json`; fail if generated files differ from what's checked in (enforces openapi regeneration).
- Matrix: Python 3.12 only (we don't need multi-version), Node 20.

**`deploy.yml` (runs on push to `main`):**
- Backend: `gcloud builds submit` builds the Docker image in Cloud Build (free-tier 120 build-min/day), then `gcloud run deploy` to the service. Uses a Workload Identity-federated GitHub OIDC token — no long-lived service account keys. Post-deploy curl to `/healthz`.
- Frontend: Vercel's GitHub integration auto-deploys; GH Action is a post-deploy smoke check.
- Post-deploy: optional `seed:upsert` step runs our idempotent seed command against the Cloud Run service via a one-shot Cloud Run Job invocation.

**What we explicitly skip at V0:** Dependabot (revisit after first client), container scanning, performance regression tests, multi-environment promotion gates (staging → prod), release tagging automation. Each of those is a week of work that does not affect the demo.

---

## Local dev

**`docker-compose.yml`** at repo root:

- `postgres:17` image with pgvector (`pgvector/pgvector:pg17`), init SQL in `docker/init.sql` creates extension + empty schema.
- `redis:7-alpine`, no auth, port 6379.
- `inngest/inngest:latest` running `inngest dev -u http://host.docker.internal:8000/api/inngest`, exposed on 8288.

**`justfile` or `make` targets:**

- `just up` → `docker compose up -d`
- `just api` → `cd apps/api && uv run uvicorn smartbiz.app:app --reload`
- `just web` → `cd apps/web && pnpm dev`
- `just seed` → runs the idempotent seed
- `just reset` → drops + recreates Postgres schema + re-seeds

**Zero-to-running checklist** (target: under 15 minutes):

1. `git clone && cp apps/api/.env.example apps/api/.env` — fill in Clerk test keys, LLM provider key. (5 min)
2. `brew install uv pnpm docker` if missing. (3 min, or 0 if cached)
3. `just up && just seed` (2 min first time — images pull)
4. `just api` in one terminal, `just web` in another (1 min)
5. Visit http://localhost:5173 — demo mode Lara works immediately. (<1 min)

---

## Open questions

1. **LLM provider pick is still TBD** (from stack doc) but now cost-free options dominate: **Groq** free tier (Llama, Mixtral, Qwen — fast, generous limits), **OpenRouter** free models (`:free` suffix on `meta-llama/*`, `deepseek/*`, `qwen/*`), and/or team-provided provider keys. Token-counting shape still needs a concrete provider for the demo cutoff — pick before M1 spec.
2. **Clerk "Organizations" vs "Users" as tenant boundary.** Once we go from V0 to multi-tenant, does each paying client become an Organization in Clerk, or do we mint our own `tenant_id` table keyed by Clerk user? Defer to first-client spec, but the DB schema should include `tenant_id` columns from day one so it's not a migration.
3. **Where does the MCP gateway's `allow_list` live?** Postgres row per session? Static in code per role? Proposal: start static (demo_role / auth_role → hard-coded tool-name lists in Python), move to DB when we have >2 roles.
4. **Upstash 10k commands/day is tight.** Our middleware hits Redis on every request. At 100 sessions/day × 20 requests × 2 ops ≈ 4k commands, fits comfortably. But if a viral post drives a traffic spike, we'll exceed the daily cap and 429 starts happening. Monitor and upgrade to Upstash's pay-as-you-go ($0.20/100k commands) if it becomes an issue — still far below any always-on Redis hosting.
5. **Seed data ownership.** Who owns the ~8 hand-curated documents in the seed corpus? If they're tied to the Zerotoprod story (proposals, MSA templates), someone on the team writes them. Needs a 4-hour session with marketing/founder-facing input before we can seed.

---

## Gotchas

1. **FastAPI middleware ordering.** The demo-session middleware must run *after* any CORS middleware and *before* any auth dependency, otherwise CORS preflights get a UUID assigned to a non-browser (noisy Redis keys) or Clerk auth fires on demo-only routes. Register CORS first, demo middleware second, route layer third.
2. **SSE streams die silently when the client disconnects.** FastAPI's `StreamingResponse` does not by default notice a closed TCP connection until the next yield. Under abort-controller cutoff this is fine (we're closing on purpose), but for ordinary "user refreshed the tab" it means we keep burning tokens. Wire the stream to `request.is_disconnected()` checks on every delta.
3. **Cold starts — both Cloud Run AND Neon.** Cloud Run: first request after idle is 2–10s (Docker image pulled, Python process started). Neon: sleeping branch adds ~500ms. Stacked, a totally-cold first visit is ~5–10s of lag before the first SSE chunk — demo-killer. **Mitigation:** Inngest cron pings `/healthz` every 10 minutes during demo hours, which keeps one warm Cloud Run instance AND keeps the Neon branch active. Both are within free-tier quotas. Outside demo hours, accept the cold start — it's the cost of $0 hosting.
4. **uv lockfile (`uv.lock`) conflicts on team branches.** When two devs add different deps on parallel branches, `uv.lock` merges messily. Prescription: one PR per dependency change (don't batch deps with feature work), and `uv lock --upgrade-package <name>` + commit as the first step of the PR.
5. **`hey-api generate` must run in CI or drift will ship.** If a backend PR changes a response shape but the dev forgot to regenerate TS, frontend silently keeps compiling against stale types and the bug surfaces in prod. The CI diff check is the only thing enforcing this — don't disable it.

---

## Sources

### Python tooling
- [uv: 100x Faster Python Package Manager (2026 Benchmark)](https://www.reversebits.tech/blog/uv-python-package-manager/)
- [Best Python Package Managers 2026 — Scopir](https://scopir.com/posts/best-python-package-managers-2026/)
- [Python Dependency Management in 2026 — Cuttlesoft](https://cuttlesoft.com/blog/2026/01/27/python-dependency-management-in-2026/)
- [uv docs](https://docs.astral.sh/uv/)

### Type sharing
- [Hey API openapi-ts (GitHub)](https://github.com/hey-api/openapi-ts)
- [Typesafe API Code Generation for React in 2026 — Sascha Becker](https://www.saschb2b.com/blog/typesafe-api-codegen-2026)
- [Hey API Vite plugin — DeepWiki](https://deepwiki.com/hey-api/openapi-ts/8.5-vite-plugin)

### Hosting
- [Neon Serverless Postgres Pricing 2026](https://vela.simplyblock.io/articles/neon-serverless-postgres-pricing-2026/)
- [Neon vs Supabase — Vela](https://vela.simplyblock.io/neon-vs-supabase/)
- [Neon pgvector docs](https://neon.com/docs/extensions/pgvector)
- [Upstash Redis Pricing](https://upstash.com/pricing/redis)
- [Google Cloud Run free tier](https://cloud.google.com/run/pricing)
- [Cloud Run scale-to-zero + cold starts](https://cloud.google.com/run/docs/configuring/cpu-always-allocated)
- [Cloud Run Jobs](https://cloud.google.com/run/docs/create-jobs)
- [Cloudflare R2 pricing (10GB free + zero egress)](https://developers.cloudflare.com/r2/pricing/)
- [R2 S3-compatible API](https://developers.cloudflare.com/r2/api/s3/api/)
- [Google Cloud Storage pricing (5GB always-free, US-only)](https://cloud.google.com/storage/pricing)
- [Railway pricing (for comparison — now rejected)](https://docs.railway.com/pricing)
- [Groq pricing / free tier](https://groq.com/pricing/)
- [OpenRouter free models](https://openrouter.ai/models?q=free)

### Auth
- [Clerk FastAPI example (GitHub)](https://github.com/clerk/fastapi-example)
- [fastapi-clerk-auth (PyPI)](https://pypi.org/project/fastapi-clerk-auth/)
- [fastapi-clerk-middleware (GitHub)](https://github.com/OSSMafia/fastapi-clerk-middleware)
- [Clerk manual JWT verification](https://clerk.com/docs/guides/sessions/manual-jwt-verification)
- [Getting Started with React, Vite and Clerk — Netlify](https://developers.netlify.com/guides/getting-started-with-react-vite-and-clerk-auth-on-netlify/)

### MCP gateway
- [FastMCP — GitHub](https://github.com/jlowin/fastmcp)
- [FastMCP Proxy Servers docs](https://gofastmcp.com/v2/servers/proxy)
- [MCP Proxy Servers with FastMCP 2.0 — jlowin.dev](https://www.jlowin.dev/blog/fastmcp-proxy)
- [Multi-Server Configuration with MCPConfig — DeepWiki](https://deepwiki.com/jlowin/fastmcp/6.3-multi-server-configuration-with-mcpconfig)

### Rate limiting / middleware
- [Rate Limiting for FastAPI — Upstash](https://upstash.com/docs/redis/tutorials/python_rate_limiting)
- [fastapi-limiter — GitHub](https://github.com/long2ice/fastapi-limiter)
- [Build 5 Rate Limiters with Redis — redis.io](https://redis.io/tutorials/howtos/ratelimiting/)

### Seed data
- [Faker — GitHub](https://github.com/joke2k/faker)
- [Synthetic Dataset Generation with Faker — MLMastery](https://machinelearningmastery.com/synthetic-dataset-generation-with-faker/)

### Local dev & Inngest
- [Inngest Local Development docs](https://www.inngest.com/docs/local-development)
- [Inngest Python SDK (GitHub)](https://github.com/inngest/inngest-py)
- [pgvector Docker image](https://hub.docker.com/r/pgvector/pgvector)

# Foundation — API Contracts

**Date:** 2026-04-19
**Status:** Draft for team review. Contracts first — models/services derive from these.
**Scope:** Session (demo + admin), auth, health, config.

---

## Auth model (simplified for V0)

SmartBiz OS is a **capability demo**, not multi-tenant SaaS. Two auth states, period:

1. **Anonymous visitor (the default).** Demo session — UUID cookie, Redis-tracked, 5-min / 2000-token limits. No sign-up.
2. **Admin (the team).** 1–3 accounts, seeded at startup from env (`ADMIN_USERS_JSON`). Email + password (bcrypt). Login returns a self-issued JWT in an HttpOnly cookie. Used to manage seed data, inspect demos, run internal tools.

**What we consciously don't build for V0:** public sign-up, email verification, password reset flow, SSO, multi-tenant runtime isolation, role-gated endpoints. All of these can be added later without changing the auth model — the data model is forward-compatible.

**Forward-compat hooks (built in now, unused in V0):**
- `admin_users.role` column — populated as `"admin"` for V0, holds future values (`sales`, `engineer`, `readonly`). Endpoints that will become role-gated in V1.5 are noted in their respective module contracts.
- `admin_users.status` column — `active | disabled`. Lets us deactivate without deleting (audit retention).
- `tenant_id` column on every domain table (leads, docs, invoices, etc.) — populated with a single `DEFAULT_TENANT_ID` constant in V0. If we ever split instances, no migration.
- `last_login_at_unix` on `admin_users` — harmless in V0, useful the moment the team has >5 people.
- **Invite-admin endpoint** is deliberately deferred — V0 grows by env edits + redeploy. When the team passes 5 people, we add `POST /api/admin/invite` returning a one-time setup link. Same auth model, one new endpoint.

**Admin bootstrap:** On startup, `Settings.from_env()` reads `ADMIN_USERS_JSON` (a JSON array of `{email, bcrypt_hash}`). Any email in the env that's not in the `admin_users` table is inserted; any row in the table not in the env is ignored (no destructive sync — avoids accidental lockout if env is misconfigured). Rotating a password = generate new bcrypt hash, update env, redeploy.

---

## Conventions

All conventions apply to every module's contracts unless overridden.

### Transport & format
- **Base path:** `/api` for all JSON endpoints. SSE under `/api/stream/*`.
- **Content-Type:** `application/json` for request/response. SSE uses `text/event-stream`.
- **Auth:** two cookies, mutually exclusive on any given request:
  - `demo_session` — UUID, HttpOnly, SameSite=Lax, 1h TTL.
  - `admin_session` — JWT, HttpOnly, SameSite=Lax, 7-day TTL, rotated on each login.
- **Priority:** if both cookies exist on a request, `admin_session` wins. Admin routes ignore `demo_session`. Public routes read whichever is valid.
- **CORS:** allow frontend origin only.

### IDs and timestamps
- **IDs:** string UUIDs (v4). Never expose DB integer primary keys.
- **Timestamps:** Unix seconds as `int`. Exception: Reports module may use ISO for period boundaries.
- **Durations:** seconds as `int`.

### Error envelope

Every non-2xx response uses this shape:
```python
@dataclass
class ErrorResponse:
    error: ErrorBody

@dataclass
class ErrorBody:
    code: str
    message: str
    details: dict | None = None
```

**Standard error codes:**
| Code | HTTP | Meaning |
|---|---|---|
| `unauthenticated` | 401 | No valid session |
| `forbidden` | 403 | Not an admin |
| `not_found` | 404 | Resource doesn't exist |
| `demo_expired` | 402 | Demo session > 5min wall clock |
| `demo_tokens_exhausted` | 402 | Demo session hit 2000-token cap |
| `rate_limited` | 429 | Too many requests; `Retry-After` header set |
| `validation_failed` | 422 | Request body malformed |
| `bad_credentials` | 401 | Admin login failed (email/password mismatch) |
| `upstream_failed` | 502 | Downstream provider errored |
| `internal` | 500 | Unexpected error; opaque message |

### Pagination

Cursor-based, never offset:
```python
@dataclass
class PageRequest:
    cursor: str | None = None
    limit: int = 25

@dataclass
class Page[T]:
    items: list[T]
    next_cursor: str | None
```

---

## Pages

| Page | Route (frontend) | Purpose |
|---|---|---|
| Demo landing | `/` | Public entry. Mints demo session, shows "Try Lara" CTA + countdown |
| Demo-expired | `/expired` | Wall-clock or token cap hit. "Book a call" / "Email us" CTAs |
| Admin login | `/admin/login` | Email + password form |
| Admin shell | `/admin` | Root layout for authed admin. Left nav, top bar. Hosts admin module routes |
| Not found | `/404` | Static |

Additional admin routes (`/admin/leads`, `/admin/automations`, `/admin/reports`, etc.) are owned by their module contracts.

---

## Per-page needs & actions

### Demo landing (`/`)
**On load:**
- `POST /api/session/init` — mint/hydrate demo session, return countdown values.
- `GET /api/config` — feature flags (voice? M7 fintech? scraper live?).

**Actions:**
- "Start chatting with Lara" → `/lara` (M1 route; demo session carries).
- "Book a call" → external Cal.com link.

### Demo-expired (`/expired`)
**On load:** nothing backend-side. Reason from sessionStorage.

**Actions:**
- "Book a call" → external.
- "Back to start" → `/` (mints fresh session if IP rate-limit window is over).

### Admin login (`/admin/login`)
**On load:**
- `GET /api/session/me` — if already an admin, redirect to `/admin`. If demo or nothing, show form.

**On submit:**
- `POST /api/auth/login { email, password }` → sets `admin_session` cookie, returns admin profile.
- On success: navigate to `/admin`.

### Admin shell (`/admin`)
**On load:**
- `GET /api/session/me` — returns admin profile (or 401 → redirect to login).
- `GET /api/config` — feature flags.

**Actions:**
- "Sign out" → `POST /api/auth/logout` clears cookie, redirects to `/`.

### Healthz
Consumers: Inngest keep-alive cron, CI smoke test, Cloud Run uptime probe. Not user-facing.

---

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/session/init` | public (mints cookie) | Start or hydrate a demo session |
| `GET` | `/api/session/me` | any | Polymorphic session context (demo / admin / none) |
| `POST` | `/api/auth/login` | public | Admin email+password login; sets `admin_session` cookie |
| `POST` | `/api/auth/logout` | admin | Clear `admin_session` cookie |
| `GET` | `/api/config` | public | Runtime feature flags + demo limits |
| `GET` | `/api/healthz` | public | DB + Redis health probe |

Six endpoints. That's it for Foundation.

---

## Contracts

### Shared types

```python
from dataclasses import dataclass

@dataclass
class DemoLimits:
    session_seconds: int       # e.g., 300
    session_tokens: int        # e.g., 2000
    ip_rate_limit_per_hour: int

@dataclass
class FeatureFlags:
    voice_enabled: bool
    hindi_voice_enabled: bool
    m7_fintech_enabled: bool
    scraper_live_enabled: bool
    # Additive only — never rename or remove.

@dataclass
class AdminUser:
    id: str                    # UUID
    email: str
    name: str
    role: str                  # "admin" for V0. Forward-compat: add "sales" | "engineer" | "readonly" as the team grows. Never hardcode; always check against an enum.
    status: str                # "active" | "disabled" — lets us deactivate without deleting (audit trail)
    created_at_unix: int
    last_login_at_unix: int | None
```

### POST `/api/session/init`

**Request:** empty body.

**Response 200:**
```python
@dataclass
class SessionInitResponse:
    session_id: str
    kind: str                  # "demo"
    started_at_unix: int
    expires_at_unix: int
    seconds_remaining: int
    tokens_used: int
    tokens_remaining: int
```

**Behavior:**
- Reads `demo_session` cookie. If valid, returns existing state (idempotent). If absent/expired, mints new UUID, writes Redis `demo:session:{uuid}` hash, sets cookie, increments `demo:ratelimit:ip:{ip}` (TTL 3600s on first increment).
- **Errors:** `429 rate_limited` if creating a new session would violate IP rate limit.

### GET `/api/session/me`

**Request:** no body.

**Response 200 (demo):**
```python
@dataclass
class DemoMeResponse:
    kind: str                  # "demo"
    session_id: str
    started_at_unix: int
    expires_at_unix: int
    seconds_remaining: int
    tokens_used: int
    tokens_remaining: int
```

**Response 200 (admin):**
```python
@dataclass
class AdminMeResponse:
    kind: str                  # "admin"
    admin: AdminUser
```

**Response 200 (none — no valid session):**
```python
@dataclass
class AnonMeResponse:
    kind: str                  # "anon"
```

**Notes:**
- Discriminated union on `kind`. Three variants total.
- Never returns 401 — it's a probe endpoint. The frontend uses the `kind` to decide what to render.

### POST `/api/auth/login`

**Request:**
```python
@dataclass
class LoginRequest:
    email: str
    password: str
```

**Response 200:**
```python
@dataclass
class LoginResponse:
    admin: AdminUser
```

**Behavior:**
- Looks up `admin_users` row by email. `bcrypt.checkpw(password, row.bcrypt_hash)` — constant-time comparison.
- On success: mint JWT (`{sub: user_id, iat, exp = now + 7d}`), set `admin_session` HttpOnly cookie, return admin profile.
- On failure: `401 bad_credentials` with a generic message (never reveal whether email exists).

**Errors:**
- `401 bad_credentials` — any auth failure (wrong email, wrong password, unknown email).
- `422 validation_failed` — missing/malformed fields.
- `429 rate_limited` — more than 5 failed attempts from an IP in a 10-min window. Redis key `auth:failures:ip:{ip}`.

### POST `/api/auth/logout`

**Request:** no body.
**Auth:** requires `admin_session`.

**Response 204:** No body. `Set-Cookie: admin_session=; Max-Age=0` clears the cookie client-side.

**Errors:**
- `401 unauthenticated` if no admin session (no-op would also be fine, but 401 is clearer).

### GET `/api/config`

**Request:** no body. Public.

**Response 200:**
```python
@dataclass
class ConfigResponse:
    version: str
    environment: str           # "dev" | "staging" | "prod"
    features: FeatureFlags
    demo_limits: DemoLimits
```

**Behavior:** cacheable (`Cache-Control: public, max-age=60`).

### GET `/api/healthz`

**Request:** no body. Public.

**Response 200:**
```python
@dataclass
class HealthResponse:
    status: str                # "ok" | "degraded"
    timestamp_unix: int
    checks: HealthChecks

@dataclass
class HealthChecks:
    db: str                    # "ok" | "degraded"
    redis: str                 # "ok" | "degraded"
    inngest: str               # "ok" | "unreachable"
```

**HTTP status:**
- `200` when `status == "ok"`.
- `503` when db or redis is degraded. Inngest unreachable doesn't flip the flag.

---

## Open questions

1. **Admin count.** Proposal: 1–3 admin accounts seeded via env. If it's always just one, the env shape simplifies to `ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH`. Needs a team call.
2. **JWT secret rotation.** If we rotate the signing secret, all admin sessions invalidate. Acceptable for a 1–3-user system. Keep the secret in Google Secret Manager.
3. **Failed-login rate limit scope.** Per-IP vs per-email? Per-IP is safer (brute-force on one email via many IPs is blocked at the Cloud Run level). Keep per-IP for V0.
4. **`/api/config` is hot.** Loaded on every page mount. Keep lean — flags + limits, nothing dynamic.
5. **Do we need CSRF protection?** Cookie-based auth means yes in principle. Double-submit token pattern (`X-CSRF-Token` header echoing a cookie) is 30 lines. Proposal: add for admin-write routes (login, logout, and all `/admin` mutations in later modules), skip for public GETs and for demo reads.

---

## Gotchas

1. **HttpOnly cookie means frontend can't read `admin_session` JWT.** That's the point. If the frontend needs to display "logged in as X," call `/api/session/me` — never decode the JWT client-side.
2. **`me` endpoint is polymorphic with 3 variants (demo / admin / anon).** Frontend dispatches on `kind` via a type guard.
3. **Rate-limit off-by-one.** `INCR` before check vs after. Use `INCR` then compare; `SET NX EX` for TTL. TTL only on the key's first creation.
4. **Admin bootstrap is additive, not destructive.** If the env is misconfigured (typo in `ADMIN_USERS_JSON`), we never delete existing admin rows — just skip. Avoids accidental lockout.
5. **Cookie priority.** When both demo and admin cookies exist (e.g., admin signed in after browsing as demo), admin wins. Don't return demo session state on admin routes.
6. **CSRF is cookie-auth's cost.** Not needed for V0 public endpoints, but any admin mutation route (including logout) should check the CSRF token. Adding it after the fact is easy — just enforce from day one on `/admin/*` write paths.

---

## Next contracts to write

- **M1 Lara** — chat (SSE), conversation history, doc upload, memory recall, voice. 8–10 endpoints, demo headline.
- **M2 Sales Intel** — leads CRUD, kanban, integrations, scraper runs, enrichment. ~12 endpoints.
- **M3 Automation** — timelines, templates, runs, channel registry. ~8 endpoints.
- **M6 Reports** — list, detail, generate-on-demand, compare. ~5 endpoints.
- **M7 Fintech** — invoices CRUD, spend analytics, anomalies. ~7 endpoints.

Total estimate: ~45 endpoints. Foundation's 6 is the warm-up.

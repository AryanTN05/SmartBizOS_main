# M7 Fintech — API Contracts

**Date:** 2026-04-19
**Status:** Draft for team review. **Optional module** — build only if bandwidth or a fintech-prospect is booked.
**Depends on:** `docs/specs/api-contracts/foundation.md` (conventions, auth, error shapes, pagination). `docs/specs/api-contracts/m1-lara.md` (document upload pipeline — M7 reuses it entirely).
**Research:** `docs/research/modules/m7-fintech.md`.

M7 is a **vertical showcase** — invoice ingestion → spend dashboard → anomaly flags → Lara Q&A. The bar is "sharp dashboard + three believable Lara prompts," not accounts-payable replacement. This is the narrowest set of contracts in SmartBiz OS: ~7 endpoints, four admin pages, zero demo write endpoints.

---

## Scope

**In this module:**
- Invoices list + detail + re-categorize + delete (admin-only REST).
- Spend analytics: by-category aggregation, monthly trend series, overdue report.
- Anomaly browser (rule-based + qualitative LLM flags).

**Out of scope (handled elsewhere):**
- **Invoice upload.** No `POST /api/invoices` endpoint exists. Uploads go through M1's `POST /api/documents/upload`. M7 materializes rows only after M1 marks `extraction_status == "ready"` **and** classification routes `doc_kind == "invoice"`. Any temptation to add a dedicated invoice uploader must be rejected — the research memo calls this out explicitly.
- **Payment workflow.** V0 is read-only. No pay button, no approval chain, no vendor payout rails.
- **Invoice create/update mutations beyond category.** PATCH is scoped to `category_id` only. Editing extracted fields (vendor, total, dates) is V2 — the source of truth is the extracted document.
- **MCP tools.** The `fintech.*` tool surface lives on the FastMCP server Lara talks to. Tool contracts live with M1 / the MCP gateway spec. What lives here is the HTTP surface the admin UI calls.
- **FX refresh cron.** `fintech.fx.refresh` is an Inngest scheduled function, not an HTTP endpoint. Populates `fx_rates` daily at 17:00 UTC off Frankfurter (primary) / ExchangeRate-API (failover).

**Demo-mode access:** demo users **cannot hit M7 REST endpoints directly** — every endpoint below is admin-only. Demo users ask Lara ("What did we spend on SaaS last quarter?") and Lara uses MCP tools against the seeded tenant. Demo sees pre-seeded invoice data (~50–100 invoices, 6 months, 3 currencies, planted anomalies); the seed lives in `scripts/seed_fintech.py`. This is the single biggest auth difference between M7 and M1/M2: no `demo` badge in the auth column below.

---

## Pages

| Page | Route (frontend) | Purpose |
|---|---|---|
| Invoices list | `/admin/invoices` | Filterable, paginated table. Status, currency, category, vendor, overdue flag, anomaly flag |
| Invoice detail | `/admin/invoices/:id` | Parsed fields + line items + linked document preview + anomaly flags + re-categorize action |
| Spend dashboard | `/admin/fintech` | Four Recharts regions: category breakdown, monthly trend, vendor leaderboard, overdue tracker. Native/reporting currency toggle |
| Anomalies | `/admin/anomalies` | Detected anomalies with severity. Jump-to-invoice |

---

## Per-page needs & actions

### Invoices list (`/admin/invoices`)

**On load:** `GET /api/invoices?limit=50&cursor=...` with filters `status`, `currency`, `category`, `vendor`, `due_before`, `is_overdue`, `is_anomaly`. Also `GET /api/config` — hide the route entirely if `m7_fintech_enabled=false`.

**Actions:** filter (query updates, URL-deep-linkable) · row click → `/admin/invoices/:id` · native/reporting toggle (client-side, both totals come back in the row).

### Invoice detail (`/admin/invoices/:id`)

**On load:** `GET /api/invoices/:id` for parsed fields + line items + anomaly flags + linked document id. In parallel: `GET /api/documents/:id` (M1) for PDF preview metadata.

**Actions:**
- Recategorize → `PATCH /api/invoices/:id { category_id }`. UI toasts that the vendor's default is now set for future invoices (server side-effect, see PATCH spec).
- Delete → `DELETE /api/invoices/:id` behind a confirm modal.
- View source doc → inline PDF preview via M1's document detail.

### Spend dashboard (`/admin/fintech`)

**On load (parallel):** `GET /api/fintech/spend-by-category`, `/spend-trend`, `/overdue`, `/anomalies?period=this_month` (counter tile).

**Actions:** period selector refetches all four · currency toggle switches reporting-side conversion (native mode returns `dict[currency, amount]`) · category bar click → filtered `/admin/invoices` deep link · overdue row click → invoice detail.

### Anomalies (`/admin/anomalies`)

**On load:** `GET /api/fintech/anomalies?severity=...&period=...&cursor=...`. Row click jumps to the invoice with the anomaly tab pre-expanded.

---

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/invoices` | admin | List invoices with filters + pagination |
| `GET` | `/api/invoices/{id}` | admin | Full detail, line items, anomaly flags |
| `PATCH` | `/api/invoices/{id}` | admin | Re-categorize (category only in V0) |
| `DELETE` | `/api/invoices/{id}` | admin | Hard delete (cascades to line items) |
| `GET` | `/api/fintech/spend-by-category` | admin | Aggregated for pie/bar chart |
| `GET` | `/api/fintech/spend-trend` | admin | Time series for trend chart |
| `GET` | `/api/fintech/overdue` | admin | Overdue invoices + totals |
| `GET` | `/api/fintech/anomalies` | admin | Anomaly list |

Eight endpoints. Matches the research memo's ~7 estimate; the extra is splitting anomalies out from detail so the anomalies page doesn't need to hydrate full invoices.

**No invoice-create endpoint.** M7 rows materialize via the Inngest pipeline described in "Ingest flow" below.

---

## Ingest flow (why there is no POST)

```
User uploads PDF → POST /api/documents/upload                  (M1)
   └── R2 put, documents row, extraction_status="pending"
       Inngest: document.uploaded
          ├── M1 worker: PyMuPDF text / Nanonets OCR
          ├── M1 worker: doc-type classification (LLM on first 500 tokens)
          ├── documents.kind_detected = "invoice" | "contract" | "report" | ...
          └── extraction_status="ready"
              Inngest: document.extracted { document_id, kind }
                 └── if kind=="invoice": invoice.extract fires
                        ├── Tier 1: vendor-template regex on raw_text
                        ├── Tier 2: LLM structured output (Gemini 2.5 Flash, JSON-schema)
                        ├── Tier 3: (scans) Nanonets OCR → LLM
                        ├── Vendor resolution (trigram → embedding)
                        ├── Category inference (vendor cache → line-item cache → LLM)
                        ├── INSERT invoices (+ invoice_line_items)
                        └── Anomaly detection:
                              ├── Stage 1 sync: 7 rule checks → anomaly_flags JSONB
                              └── Stage 2 async: invoice.anomaly.qualitative
                                    └── LLM on raw_text for unusual clauses → append flags
```

**Why reuse M1 completely:** one ingest surface = one bug-fix locus, one progress UI, one audit trail. A forked uploader would duplicate chunking, embedding, OCR fallback, error states, rate limits, demo-session rules. M1's classifier already has `"invoice"` in its enum.

**User-visible:** on `/admin/documents`, invoice-kind docs link to `/admin/invoices/:id` once extraction completes. The invoices list only shows rows after the full pipeline (category + anomaly pass) finishes. Between `document.extracted` and invoice insert there's a brief window — the document detail page shows "Invoice extraction in progress…"

---

## Contracts

### Shared types

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class Invoice:
    id: str                            # UUID
    tenant_id: str
    document_id: str                   # FK → M1 documents.id
    vendor_id: str | None              # resolved post-extraction; None if unresolved
    vendor: str                        # display name; canonical_name or vendor_name_raw fallback
    invoice_number: str | None
    issue_date: str | None             # ISO "YYYY-MM-DD" — see Date carve-out
    due_date: str | None               # ISO "YYYY-MM-DD"
    total_amount: str                  # decimal-stringified, e.g. "12345.67"
    subtotal_amount: str | None
    tax_amount: str | None
    currency: str                      # ISO 4217, uppercase
    status: str                        # "draft" | "open" | "paid" | "overdue" | "void"
    category_id: str | None            # FK → spend_categories
    category_name: str | None          # denormalized for list rendering
    raw_text: str                      # omitted from list responses (can be 10s of KB)
    structured_data: dict              # full LLM output + per-field confidences, bank details, PO refs
    extraction_confidence: str | None  # decimal-stringified 0.00–1.00
    needs_review: bool                 # true when confidence < 0.70 on key fields
    anomaly_flags: list["AnomalyFlag"]
    reporting_total: str | None        # converted at issue_date; None when no FX rate
    reporting_currency: str | None     # tenant's reporting ccy at read time
    created_at_unix: int
    updated_at_unix: int

@dataclass
class InvoiceLineItem:
    id: str                            # UUID
    invoice_id: str                    # UUID
    order: int                         # line_no, 1-indexed
    description: str
    quantity: str | None               # decimal-stringified (e.g., "3.000")
    unit_price: str | None             # decimal-stringified (e.g., "99.9900")
    total: str                         # decimal-stringified, required
    category_id: str | None            # per-line override; null means inherits invoice's category

@dataclass
class AnomalyFlag:
    code: str
    # One of:
    # "duplicate" | "near_duplicate" | "amount_outlier" | "new_vendor_high"
    # | "odd_terms" | "off_pattern_date" | "round_number" | "llm_qualitative"
    severity: str                      # "low" | "med" | "high"
    message: str                       # human-readable, shown on badge tooltip
    details: dict                      # rule-specific evidence (see per-rule shapes in Gotchas)
    detected_at_unix: int

@dataclass
class SpendCategory:
    id: str                            # UUID
    tenant_id: str                     # UUID
    name: str
    parent_id: str | None              # UUID — nested taxonomy
    budget_monthly: str | None         # decimal-stringified; null when unbudgeted
    budget_currency: str | None        # ISO 4217 for the budget

@dataclass
class FxRate:
    date: str                          # ISO "YYYY-MM-DD" — rate's as_of_date
    from_currency: str                 # ISO 4217
    to_currency: str                   # ISO 4217
    rate: str                          # decimal-stringified, e.g., "83.21450000"

@dataclass
class SpendByCategory:
    category_id: str | None            # null for the "uncategorized" bucket
    category_name: str
    total_native_by_currency: dict[str, str]  # {"USD": "12345.67", "EUR": "800.00"} — native-mode breakdown
    total_reporting: str               # decimal-stringified — converted sum in reporting_currency
    count: int                         # number of invoices rolled up

@dataclass
class SpendTrendPoint:
    period_start: str                  # ISO "YYYY-MM" — month bucket
    total_reporting: str               # decimal-stringified
    count: int
    # Stacked-bar breakdown when client requests category stacking:
    by_category: dict[str, str] | None # {category_id: reporting_total_str}

@dataclass
class OverdueSummary:
    total_reporting: str               # decimal-stringified — sum of all overdue totals, reporting ccy
    reporting_currency: str            # ISO 4217
    count: int
    invoices: list[Invoice]            # ordered by days_overdue desc
```

### Money is decimal-stringified, never float

Every monetary field on the wire is a `str` with a decimal representation, e.g., `"12345.67"`. Parsed server-side via `decimal.Decimal`, stored as `NUMERIC(14,2)` in Postgres.

**Why:** IEEE-754 floats can't exactly represent `0.1`. One accidental `float64` round-trip in a dashboard aggregation produces visible drift (`$12,345.67` → `$12,345.669999...`). Fatal for fintech credibility — the research memo's gotchas flag this first. JSON numbers default to `float64` in common parsers, so we opt out at the type level: the wire type is `str`, callers who need arithmetic parse to `Decimal` explicitly.

Applies to: `total_amount`, `subtotal_amount`, `tax_amount`, line-item `quantity`/`unit_price`/`total`, `budget_monthly`, `rate`, `reporting_total`, `total_reporting`, `extraction_confidence`.

### Date vs timestamp carve-out

Foundation's rule is "Unix-seconds `int` for timestamps." M7 carves out **invoice `issue_date` and `due_date`** (also `fx_rates.date` and spend-period boundaries), which are just-a-date concepts — no wall-clock time, no timezone. Those are ISO `"YYYY-MM-DD"` strings.

Rationale: an invoice issued on 2026-04-19 in Bangalore is also issued on 2026-04-19 in Berlin. Forcing a Unix timestamp introduces a false midnight anchor and breaks currency-conversion joins (which key on date-only `as_of_date`). `created_at_unix`, `updated_at_unix`, `detected_at_unix` remain Unix seconds per Foundation.

### Currency conversion happens at read time

Storage is native, always. `invoices.currency` + `invoices.total_amount` hold exactly what the extraction pipeline parsed.

Conversion happens when analytics endpoints aggregate. The query joins `fx_rates` on `(from_currency, to_currency, as_of_date = invoices.issue_date)`, falling back to the most recent rate ≤ `issue_date` via `LATERAL` (ECB doesn't publish weekends/holidays). If no rate exists for a pair, `reporting_total: null` for that line, dashboard aggregates exclude it, `unconverted_count` increments. Never silently substitute 1.0.

**Why read-time and not ingest:** rates drift. Aggregation uses the rate at `issue_date` (the invoice's natural FX anchor), not at ingest time. Converting at ingest bakes a stale rate in forever.

### Endpoint shapes

#### GET `/api/invoices`

**Request:** query params.
- `cursor: str | None`
- `limit: int = 50`
- `status: str | None` — `"draft" | "open" | "paid" | "overdue" | "void"`
- `currency: str | None` — ISO 4217 filter (e.g., only USD invoices)
- `category: str | None` — `category_id` UUID
- `vendor: str | None` — `vendor_id` UUID
- `due_before: str | None` — ISO "YYYY-MM-DD"
- `is_overdue: bool | None` — shorthand for `status == "overdue" OR (status == "open" AND due_date < today)`
- `is_anomaly: bool | None` — true = has at least one AnomalyFlag

**Auth:** admin.

**Response 200:**
```python
@dataclass
class InvoiceListResponse:
    items: list[Invoice]               # raw_text omitted; structured_data keys pruned to essentials
    next_cursor: str | None
    total_count: int | None            # populated only when cursor is None (first page)
    reporting_currency: str            # ISO 4217 — what Invoice.reporting_total is denominated in
```

**Notes:** list rows omit `raw_text` and trim `structured_data` to `{payment_terms, po_number, confidence_summary}`. `is_overdue` is computed against the request's wall clock, not a denormalized column.

#### GET `/api/invoices/{id}`

**Auth:** admin.

**Response 200:**
```python
@dataclass
class InvoiceDetailResponse:
    invoice: Invoice                   # full, including raw_text and complete structured_data
    line_items: list[InvoiceLineItem]
    document: "DocumentRef"            # thin ref to M1's documents row
    fx_rate_used: FxRate | None        # which rate was used for reporting_total; null if no conversion happened

@dataclass
class DocumentRef:
    id: str                            # FK to M1's documents.id — client fetches GET /api/documents/{id} for preview
    filename: str
    mime_type: str
    page_count: int | None
```

**Errors:** `404 not_found`.

#### PATCH `/api/invoices/{id}`

**Request:**
```python
@dataclass
class InvoiceUpdateRequest:
    category_id: str                   # UUID of target spend_category
```
**Auth:** admin.
**Response 200:** `Invoice` (updated).

**Behavior:** validates `category_id` is tenant-scoped (`422 validation_failed` otherwise). Sets `invoices.category_id`, flips `invoices.user_categorized = true` internally, and — call this out — **flips `vendors.default_category_id`** so subsequent invoices from this vendor inherit. Does not retroactively update past invoices; one-click "apply to all" is V2. Any other field update returns `422 {"code":"validation_failed","message":"Only category_id is updatable in V0"}`.

#### DELETE `/api/invoices/{id}`

**Auth:** admin only.
**Response 204.**

Cascades to `invoice_line_items`. The M1 document is **not** deleted — audit trail preserves the source. Admins clear the PDF via M1's endpoint separately.

#### GET `/api/fintech/spend-by-category`

**Request:** query params.
- `period_start: str` — ISO "YYYY-MM-DD", required
- `period_end: str` — ISO "YYYY-MM-DD", required
- `currency: str | None` — reporting currency override; defaults to `tenant.reporting_currency`
- `include_uncategorized: bool = true`

**Auth:** admin.

**Response 200:**
```python
@dataclass
class SpendByCategoryResponse:
    period_start: str
    period_end: str
    reporting_currency: str
    categories: list[SpendByCategory]  # ordered by total_reporting desc
    total_reporting: str               # grand total across all categories
    unconverted_count: int             # invoices excluded due to missing FX pair
```

#### GET `/api/fintech/spend-trend`

**Request:** query params.
- `period: str = "monthly"` — V0 supports only `"monthly"`. Reserved: `"weekly"`, `"quarterly"`.
- `months: int = 6` — lookback window, max 24
- `currency: str | None` — reporting currency override
- `stack_by_category: bool = false` — if true, populate `SpendTrendPoint.by_category`

**Auth:** admin.

**Response 200:**
```python
@dataclass
class SpendTrendResponse:
    period: str
    reporting_currency: str
    points: list[SpendTrendPoint]      # ordered oldest → newest
```

#### GET `/api/fintech/overdue`

**Request:** query params.
- `as_of_date: str | None` — ISO "YYYY-MM-DD"; defaults to today (server clock)
- `currency: str | None` — reporting currency override

**Auth:** admin.

**Response 200:** `OverdueSummary` (see shared types). `invoices` list contains full Invoice rows (with `raw_text` trimmed as in the list endpoint).

#### GET `/api/fintech/anomalies`

**Request:** query params.
- `cursor: str | None`
- `limit: int = 50`
- `severity: str | None` — `"low" | "med" | "high"`
- `period: str | None` — `"this_month" | "last_month" | "last_90d" | "ytd"`; OR pass `period_start` + `period_end`
- `period_start: str | None` — ISO "YYYY-MM-DD"
- `period_end: str | None` — ISO "YYYY-MM-DD"
- `code: str | None` — specific AnomalyFlag.code filter

**Auth:** admin.

**Response 200:**
```python
@dataclass
class AnomaliesResponse:
    items: list["AnomalyItem"]
    next_cursor: str | None
    counts_by_severity: dict[str, int] # {"low": 4, "med": 2, "high": 1} — for dashboard tile

@dataclass
class AnomalyItem:
    flag: AnomalyFlag
    invoice_id: str                    # jump-to target
    invoice_number: str | None
    vendor: str
    total_amount: str                  # decimal-stringified, native
    currency: str
    reporting_total: str | None
    issue_date: str | None
```

---

## Open questions

1. **Reporting total on list rows is O(n) FX joins.** Fine at 100/page, painful at 10k. Defer materialized view post-demo; meanwhile cap `limit` at 200.
2. **Missing FX pair behavior.** Current spec: `reporting_total = null`, aggregates exclude, dashboard shows "3 invoices excluded" banner. Alternative: fail the request loudly. Leaning silent-null.
3. **Anomaly dedup.** Stage-1 `amount_outlier` + Stage-2 LLM "unusually large spend" can double-flag the same fact. Dedup client-side by message similarity, or server-side by code priority? Leaning client-side.
4. **Category retroactive update on PATCH.** Propose: do not auto-update past invoices; UI prompts "Apply to 7 past invoices from this vendor?" opt-in. Protects audit trail.
5. **Invoice delete and M1 document lifecycle.** Currently decoupled. Storage accumulates unless admins also DELETE the doc via M1. Add V1.5 "archive & purge" admin action.
6. **Reporting currency per-tenant vs per-user.** V0: per-tenant. Multi-region CFO may need per-user; revisit after prospect conversation.
7. **Needs-review queue.** Add `is_needs_review` filter to `/api/invoices`; no dedicated page in V0.

---

## Gotchas

1. **No POST endpoint is a feature, not an oversight.** Reviewers will ask "where's the create?" It's M1's `POST /api/documents/upload`. Put on the team-review agenda — the whole design hinges on not forking ingest.
2. **`anomaly_flags` is a JSONB column, not a separate table.** Re-extraction + async qualitative pass do full-column replace (set-semantics on `code`). Race-safe via `UPDATE ... WHERE updated_at_unix = :expected`. The `AnomalyItem` response flattens JSONB for the UI.
3. **Per-rule `details` dict shapes** (opaque to callers, document in code): `duplicate` → `{existing_invoice_id, existing_invoice_number}`; `near_duplicate` → `{existing_invoice_id, total_delta_pct, issue_date_delta_days}`; `amount_outlier` → `{vendor_mean, vendor_stddev, z_score}`; `new_vendor_high` → `{threshold_reporting}`; `odd_terms` → `{payment_terms_days, reason}`; `off_pattern_date` → `{day_of_week | holiday_name}`; `round_number` → `{total, vendor_round_ratio}`; `llm_qualitative` → `{quote, clause_type, model_version}`.
4. **Demo users cannot reach M7.** Every endpoint is admin-only. Direct hits get `401 unauthenticated`. Lara demos fintech via MCP tools against the seeded tenant. Push back on any "demo should browse invoices" request — the demo value is Lara answering prompts, not a browseable table.
5. **Decimal precision on the wire is the client's problem.** Don't strip trailing zeros — `"10.00"` ≠ `"10"` for format logic. Unit prices use 4 decimals, totals use 2.
6. **FX fallback is not optional.** Every analytics query MUST include the "most recent ≤ issue_date" LATERAL fallback. Bake a helper; don't inline.
7. **Category PATCH cascade surprises admins.** Flipping `vendors.default_category_id` changes future behavior silently. UI must toast explicitly. Skip the flip when `vendor_id is null`.
8. **`structured_data` is unbounded.** Detail endpoint returns as-is; list endpoints prune aggressively. Query new fields via `GIN (jsonb_path_ops)`; don't add a column per one-off.
9. **Anomaly list can outrun invoice list.** One invoice → 3+ flags. Two anomaly rows can point to the same `invoice_id` — expected.
10. **Delete cascades to line items, not to the M1 document.** Audit trail preserved: "I accidentally deleted the invoice" must not mean "I accidentally deleted the PDF."
11. **`total_count` on list is expensive.** Populate only on first page (cursor=None); `null` thereafter. Standard cursor-pagination compromise.
12. **The feature flag is load-bearing.** `m7_fintech_enabled=false` must hide admin routes client-side AND make M7 endpoints return `404 not_found` server-side. Half-hidden modules are worse than cleanly off.

---

## Next contracts to write

- **M2 Sales Intel**, **M3 Automation**, **M5 Scraper**, **M6 Reports** — if not already authored.
- **MCP gateway contracts** — the `fintech.*` tool shapes (called by Lara, not by HTTP) ideally live in their own memo shared with M1 so all modules that register tools follow the same auto-schema conventions.

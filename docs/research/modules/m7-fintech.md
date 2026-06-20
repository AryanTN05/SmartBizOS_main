# M7 Fintech (Optional) — Research & Decisions

**Date:** 2026-04-19
**Status:** Research for team review. Optional module.
**Depends on:** foundation.md, m1-lara.md (doc pipeline reuse)

---

## Summary

M7 is a **vertical showcase**, not a core demo module. Its job is to prove Zerotoprod can operate in fintech: invoice → AI extraction → spend dashboard → anomaly flags → Lara Q&A. Fintech credibility lives in UI feel (precision, trust, polish) more than feature count, so the bar is "sharp dashboard + 3 believable Lara prompts," not "accounts-payable replacement."

**Recommendation: defer M7 past the first demo.** Build M1–M6 first. Pull M7 forward only if a fintech/finance prospect is on the calendar. Minimal credible M7 is ~**2.0–2.5 engineer-weeks** on top of a working M1 pipeline.

Core technical bets:

1. **Invoice extraction = hybrid:** PyMuPDF text → vendor-scoped template rules → LLM structured output → Nanonets OCR only for scans. Reuses M1 end-to-end; no second ingest path.
2. **Multi-currency: store native, convert at read time** using a daily `fx_rates` snapshot refreshed by Inngest. Primary Frankfurter (free, ECB), failover ExchangeRate-API.
3. **Anomaly detection: rules first, LLM second.** Rules cheap/deterministic/explainable (dashboard badges); LLM async for qualitative flags.
4. **Charts: Recharts** — already the SmartBiz OS default.
5. **MCP: six `fintech.*` tools** on the existing FastMCP server Lara uses, typed dataclass returns.

---

## Invoice extraction

**Decision: hybrid extraction, three tiers, fail cheap before fail expensive.**

```
PDF upload
  ├─ Tier 1: PyMuPDF text layer  (free, ~50ms)
  │   └─ If text present AND vendor template matches → regex rules → DONE
  ├─ Tier 2: LLM structured output on raw text  (cheap, ~1–2s, $0.001–0.005 per invoice)
  │   └─ Gemini 2.5 Flash or GPT-4o-mini with JSON schema → DONE
  └─ Tier 3: Nanonets OCR fallback  (only for image/scan PDFs, ~3–6s)
      └─ OCR'd text → feed back into Tier 2 LLM
```

**Why hybrid, not a single approach:**

- **Pure LLM vision** on every invoice runs $0.20–$1/doc — Mindee's 2026 analysis puts LLMs at ~5× the cost of OCR APIs for structured extraction. Text-layer PDFs (the B2B majority) don't need vision at all.
- **Pure template matching** (`invoice2data`-style) is cheap but the library is effectively inactive in 2026 and breaks on template redesigns. Keep the *idea* (vendor-scoped regex) but implement it ourselves, keyed off `vendor_id` in our DB rather than a YAML registry.
- **Donut / OCR-free transformers** are elegant but deployment-heavy (GPU, per-schema fine-tune). Revisit if this becomes a real product.
- **Commercial invoice APIs** (Mindee ~96.1%, Rossum ~98%+ at ~$18k/yr, Veryfi ~98.7%) are accurate but duplicate M1, cost real money, and hide the engineering story.

**V0 default LLM:** Gemini 2.5 Flash ($0.15/$0.60 per 1M tokens; matches GPT-4o-mini) with JSON-schema-constrained output. Swappable via our provider-agnostic wrapper. Claude 3.5 Sonnet — the 2026 accuracy leader — is reserved for Tier-2 escalation when Flash returns low-confidence fields.

**Extracted schema:** `vendor_name, vendor_tax_id?, invoice_number, issue_date, due_date, currency, subtotal, tax_total, total_amount, line_items[{description, quantity, unit_price, total, category_hint?}], payment_terms, notes` — plus a per-field confidence. Anything < 0.7 surfaces as "needs review" and does not feed analytics until confirmed.

---

## Reuse of M1 doc pipeline

**Hard rule: M7 does not re-implement PDF ingest.** M1 already owns: upload → object storage → `documents` row → PyMuPDF text extraction → Nanonets OCR fallback → chunk/embed → doc-level metadata (mime, page count, content hash).

M7 starts **after** `documents.extraction_status = 'ready'`. It subscribes to a `document.extracted` event and, for any doc classified as `kind = 'invoice'`, runs the invoice-specific structured-extraction layer above. The result writes an `invoices` row that FKs back to `documents.id`.

Classification ("is this an invoice?") is a cheap LLM call on the first 500 tokens of extracted text, done inside M1 — M1 needs doc-type routing anyway, so we just add `invoice` to its enum. **No new ingest infra, no separate invoice uploader widget.** Use the same upload surface as every other doc; call this out explicitly in team review because the temptation to fork will be real.

---

## Data model

```sql
-- Core invoice record. Native currency preserved.
CREATE TABLE invoices (
  id               UUID PRIMARY KEY,
  tenant_id        UUID NOT NULL REFERENCES tenants(id),
  document_id      UUID NOT NULL REFERENCES documents(id),
  vendor_id        UUID REFERENCES vendors(id),           -- resolved post-extraction
  vendor_name_raw  TEXT NOT NULL,                         -- as extracted, before resolution
  invoice_number   TEXT,
  issue_date       DATE,
  due_date         DATE,
  total_amount     NUMERIC(14,2) NOT NULL,
  subtotal_amount  NUMERIC(14,2),
  tax_amount       NUMERIC(14,2),
  currency         CHAR(3) NOT NULL,                      -- ISO 4217
  status           TEXT NOT NULL DEFAULT 'open',          -- open|paid|overdue|disputed|void
  category_id      UUID REFERENCES spend_categories(id),
  raw_text         TEXT,                                  -- from M1
  structured_data  JSONB NOT NULL,                        -- full LLM output + confidences
  extraction_confidence NUMERIC(3,2),
  needs_review     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_invoices_tenant_due    ON invoices(tenant_id, due_date)    WHERE status != 'paid';
CREATE INDEX idx_invoices_tenant_cat_is ON invoices(tenant_id, category_id, issue_date);
CREATE INDEX idx_invoices_tenant_vendor ON invoices(tenant_id, vendor_id, issue_date);
CREATE INDEX idx_invoices_structured    ON invoices USING GIN (structured_data jsonb_path_ops);

CREATE TABLE invoice_line_items (
  id           UUID PRIMARY KEY,
  invoice_id   UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  line_no      INT  NOT NULL,
  description  TEXT NOT NULL,
  quantity     NUMERIC(12,3),
  unit_price   NUMERIC(14,4),
  total        NUMERIC(14,2) NOT NULL,
  category_id  UUID REFERENCES spend_categories(id)
);

CREATE TABLE spend_categories (
  id              UUID PRIMARY KEY,
  tenant_id       UUID NOT NULL REFERENCES tenants(id),
  name            TEXT NOT NULL,
  parent_id       UUID REFERENCES spend_categories(id),
  budget_monthly  NUMERIC(14,2),                          -- optional
  currency        CHAR(3),                                -- for the budget
  UNIQUE (tenant_id, name)
);

CREATE TABLE vendors (
  id              UUID PRIMARY KEY,
  tenant_id       UUID NOT NULL REFERENCES tenants(id),
  canonical_name  TEXT NOT NULL,
  aliases         TEXT[] NOT NULL DEFAULT '{}',
  default_category_id UUID REFERENCES spend_categories(id),
  UNIQUE (tenant_id, canonical_name)
);

CREATE TABLE fx_rates (
  as_of_date   DATE NOT NULL,
  from_ccy     CHAR(3) NOT NULL,
  to_ccy       CHAR(3) NOT NULL,
  rate         NUMERIC(18,8) NOT NULL,
  source       TEXT NOT NULL,                             -- 'frankfurter_ecb' | 'exchangerate_api'
  PRIMARY KEY (as_of_date, from_ccy, to_ccy)
);
```

**Schema notes** (hybrid Postgres pattern per 2026 best practice): frequently-queried fields are typed columns, not JSONB keys. `structured_data JSONB` holds the long tail (payment terms, bank details, PO refs, per-field confidences) under a `GIN (jsonb_path_ops)` index so we can probe it ad hoc without adding a column for every quirk. Every table is tenant-scoped with `tenant_id` first in composite indexes.

---

## Multi-currency

**Storage rule: never convert at ingest.** An EUR invoice stores `currency='EUR'`, `total_amount=1200.00`. Conversion is a read-time concern.

**Conversion model.** Tenant has a `reporting_currency` (default INR for Zerotoprod; USD for most prospects). Aggregating queries join `fx_rates` on `(currency, reporting_currency, issue_date)`; on weekends/holidays fall back to the most recent rate ≤ `issue_date` via a `LATERAL` lookup. The dashboard has a native ↔ reporting toggle; native mode skips cross-currency aggregation and groups by currency instead.

**FX source stack.** Primary: **Frankfurter** (`frankfurter.dev`) — free, no key, ECB-backed, historical back to 1999, ~33 currencies. Failover: **ExchangeRate-API** — free tier 1,500 req/mo, 99.99% uptime, 170+ currencies (covers non-ECB pairs). Openexchangerates/Fixer are paid options we don't need at demo scale.

**Refresh cron.** One Inngest scheduled function, `fintech.fx.refresh`, runs daily at 17:00 UTC (after ECB publishes). Pulls only the pairs needed by active tenants' invoices, upserts into `fx_rates`, idempotent. Lara alert if the primary source fails two days running.

---

## Anomaly detection

Two-stage, rules first.

**Stage 1 — rule-based, synchronous.** Runs in the extraction worker right after the invoice persists. Each rule emits a typed `Anomaly(kind, severity, message, evidence)`.

- `DUPLICATE_INVOICE` — `(tenant_id, vendor_id, invoice_number)` collision.
- `NEAR_DUPLICATE` — same tenant+vendor, total ±1%, issue_date within 7 days (re-billing scam catch).
- `AMOUNT_OUTLIER` — > 3σ above vendor's trailing 12-month mean; skip below min sample 5.
- `NEW_VENDOR_HIGH_VALUE` — first invoice from a vendor AND total > tenant threshold (default ~$5k equiv).
- `UNUSUAL_PAYMENT_TERMS` — due_date − issue_date > 90 days or negative.
- `OFF_PATTERN_ISSUE_DATE` — issued weekend/holiday.
- `ROUND_NUMBER_INFLATION` — suspiciously round total from a non-round vendor; low severity.

**Stage 2 — LLM, async, qualitative.** An Inngest background job per new invoice prompts the LLM on `raw_text` for "unusual clauses, penalties, hidden fees, or terms that deviate from standard commercial invoicing." Returns 0-N `QualitativeAnomaly` items with severity and quoted evidence. Slower (~2–4s), budget-capped per tenant per day.

**Surface.** Anomaly badge on invoice cards (R/A/Y by severity). Dashboard tile counts recent ones. `fintech.anomalies(period)` powers the demo prompt "any anomalies this month?" with typed evidence.

---

## Spend dashboard

**Chart library: Recharts.** Same as the rest of SmartBiz OS — 3.6M weekly downloads, React-first, SVG, strong TS support, fine performance at hundreds-of-invoices scale. Visx gives more control at a learning-curve tax not worth paying for an optional module. Chart.js's canvas speed isn't needed and costs accessibility semantics.

**Layout — one page, four regions, ruthlessly clean:**
1. **Header strip** — total spend (reporting currency), MoM delta, native/reporting toggle, period selector.
2. **Category breakdown** — horizontal bar chart (not pie; pie is lazy past 5 slices). Click → filtered invoice list.
3. **Monthly trend** — stacked bar by category, 12 months. Hover = exact totals.
4. **Overdue + Vendor leaderboard** — side-by-side. Overdue sorted days-late desc; vendors by total-spent with a 6-mo sparkline.

**Visual register.** Monospace numerics (`tabular-nums`), muted palette with one accent red for overdue/anomaly, generous whitespace. Copy Ramp/Brex/Mercury in density, not in features. Anti-goals: 12-tile KPI grids, gauges, pie charts, "you saved $X!" confetti. Trustworthy-boring beats flashy.

---

## Categorization

LLM at ingest, with three cache layers to keep steady-state cost near zero.

1. **Vendor cache.** First invoice from a vendor sets `vendors.default_category_id`. Subsequent invoices inherit it and skip the LLM call. ~95% of invoices come from repeat vendors.
2. **Line-item cache.** Vendors that span categories (e.g. Amazon) use `(vendor_id, normalized_description) → category_id`; normalization is lowercase + strip SKU-shaped tokens.
3. **Cold path.** New vendor/new line → LLM call with the tenant's category taxonomy as an enum; prompt includes vendor name, top-3 line descriptions, the full list. Returns `category_id` + confidence.

**User override is source of truth.** Manual recategorize flips `vendors.default_category_id`, retroactively updates same-vendor invoices from the session, and marks the invoice `user_categorized=true` for future weighting. "Teaches the model" is V2.

**Default taxonomy** (tenant-editable): a 12-category cut from SaaS COA conventions — *Software & SaaS, Cloud & Infrastructure, Professional Services, Marketing, Travel, Office & Supplies, Hardware, Payroll Services, Insurance, Legal & Compliance, Taxes & Fees, Other*. Not GAAP-complete — that's a real AP product's problem, not ours.

---

## Lara MCP surface

All tools live on the existing FastMCP server Lara uses. Dataclass returns so Lara receives typed, structured content (FastMCP auto-generates the JSON schema from annotations).

```python
@mcp.tool
def list_invoices(
    tenant_id: str,
    status: Literal["open", "paid", "overdue", "disputed"] | None = None,
    category: str | None = None,
    due_before: date | None = None,
    limit: int = 50,
) -> list[InvoiceSummary]: ...

@mcp.tool
def get_invoice(tenant_id: str, invoice_id: str) -> InvoiceDetail: ...

@mcp.tool
def spend_by_category(
    tenant_id: str,
    period: Period,                        # {"from": date, "to": date}
    currency: str | None = None,           # default = tenant reporting currency
) -> list[CategorySpend]: ...

@mcp.tool
def overdue_invoices(
    tenant_id: str,
    as_of_date: date | None = None,
) -> OverdueReport: ...

@mcp.tool
def anomalies(tenant_id: str, period: Period | None = None) -> list[Anomaly]: ...

@mcp.tool
def compare_months(tenant_id: str, month1: str, month2: str) -> MonthComparison: ...
```

**Namespacing.** `fintech.*` per foundation doc. `tenant_id` is injected from Lara session context, not passed as a parameter the LLM can spoof.

**Three demo prompts that must work flawlessly:**
1. *"How much did we spend on SaaS last quarter?"* → `spend_by_category(period=last_quarter, category='Software & SaaS')`.
2. *"What invoices are overdue?"* → `overdue_invoices()`.
3. *"Any anomalies this month?"* → `anomalies(period=this_month)` with evidence snippets.

Rehearse these three until they are boring. The rest of the tool surface is for credibility.

---

## Seed data

Only if M7 ships in the demo. Generate with a committed, reproducible LLM script.

- **50–100 invoices over 6 months**, 4–6 fictional vendors (*Helix Cloud, Acme Print, Polaris Legal, Nimbus SaaS, Vertex Travel, Delta Supplies*).
- **3 currencies** — USD dominant, one EUR vendor, two INR vendors.
- **Planted anomalies:** one duplicate (same number, 3 days apart); one outlier (Helix usually $800/mo, spikes to $4,200); one unusual-terms (120-day net); one qualitative ("auto-renewal with 30% uplift" clause).
- **Planted overdues:** 3–4 invoices past due 5 / 22 / 41 days.
- **Realistic line items** — 2–8 per invoice, vendor-appropriate (Helix = compute SKUs, Polaris = hourly billing).

Script at `scripts/seed_fintech.py`, takes `--tenant-id` and `--months`, idempotent.

---

## Decision gate (ship vs defer)

**Timeline to minimal M7 on top of a working M1:**

| Scope chunk | Estimate |
|---|---|
| Invoice-specific extraction layer (hybrid tiers + LLM schema) | 3 days |
| Data model, migrations, vendor/category resolution | 2 days |
| FX refresh cron + conversion helpers | 1.5 days |
| Anomaly rules (stage 1) + LLM stage 2 job | 2 days |
| Dashboard (Recharts, 4 regions, native/reporting toggle) | 3–4 days |
| MCP tools + Lara prompts rehearsal | 1.5 days |
| Seed data + polish pass | 1.5 days |
| **Total** | **~2.0–2.5 eng-weeks** |

**Pitch-value read.** To a generic SMB prospect: low — M7 adds demo surface without conversion power. To a fintech/finance prospect: high — it's the difference between "we build AI tools" and "we build AI tools *for your domain*." Specifically unlocks AP-automation RFPs, finops consultancies, fractional-CFO firms.

**Recommendation: defer M7 past the first demo.** Ship M1–M6. Pull M7 forward only if a fintech-adjacent prospect is booked within ~3 weeks; in that case swap it into that one demo against the weakest core module (likely M5 or M6).

**If we defer, do two things now in M1:** (1) include `invoice` in the doc-type classifier enum so the data exists when M7 arrives; (2) verify the FastMCP server supports tool namespacing so `fintech.*` is a zero-refactor drop-in.

---

## Open questions

1. **Classification placement** — "is this an invoice?" as a hard field in M1's doc pipeline, or a lazy call when M7 asks? Leaning hard field; cheaper and gives Lara inbox filters for free.
2. **Vendor resolution** — trigram, embedding, or LLM-as-judge for fuzzy-matching `vendor_name_raw`? Start trigram, escalate to embedding when ambiguous. Revisit after 200+ seed invoices.
3. **Reporting currency — per-tenant or per-user?** Per-tenant in V0; global CFO vs regional controllers might need per-user later.
4. **Payment workflow** — M7 is read-only in V0 (no pay button, no approval chain). Commit publicly, don't hedge. Payment rails are a real-product problem.
5. **Audit storage** — should `structured_data` also store the LLM prompt/version for reproducibility of anomaly investigations? Probably yes; low cost, high debuggability.

---

## Gotchas

- **PyMuPDF tables ≠ structured line items.** PyMuPDF returns text with coordinates; mapping to `{description, qty, unit_price, total}` is engineering work. The LLM extracts line items from the *text* PyMuPDF produces. Most common misconception about the stack — don't let it land in marketing copy.
- **Confidence ≠ correctness.** LLM-reported confidence is miscalibrated, especially on edge fields (`tax_amount` under VAT/GST). Use it to prioritize human review, not as an accuracy signal.
- **FX weekends.** ECB doesn't publish on weekends or EU holidays. Queries must fall back to most-recent-≤-issue-date — bake this into the helper, not every call site.
- **Currency rounding.** Store as `NUMERIC(14,2)`; never cast to float. One accidental `float64` round-trip in a dashboard aggregation and numbers drift visibly — fatal for fintech credibility.
- **Duplicate detection is tenant-scoped.** Two tenants can legitimately share an `invoice_number` from the same vendor. The key that matters is `(tenant_id, vendor_id, invoice_number)`.
- **Taxonomy drift.** Renames are safe (FK, not string). Deletes must soft-delete with a reassignment prompt.
- **Seeded anomalies must be plausible.** Too-obvious duplicates kill demo credibility worse than no anomaly. Manually review seed output before each demo.
- **LLM model swaps change field quality silently.** Pin the extraction model version; gate swaps behind a golden-set regression (20 invoices, diff the structured output).
- **Nanonets cost.** Free first 100 invoices/mo; $499/mo beyond. Fine for demo, but flag before any tenant pilot — a runaway seed script will burn it.
- **FastMCP return types.** Return dataclasses or Pydantic models, never `dict[str, Any]`. Auto-schema from annotations is what makes Lara tool calls reliable; `dict` leaks the shape up to the LLM and costs accuracy.

---

## Sources

- [invoice2data (GitHub)](https://github.com/invoice-x/invoice2data) — effectively inactive in 2026.
- [Mindee: LLMs vs OCR APIs — Cost Comparison](https://www.mindee.com/blog/llm-vs-ocr-api-cost-comparison) — LLMs ~5× OCR APIs for structured extraction.
- [Vellum: Document Data Extraction in 2026](https://www.vellum.ai/blog/document-data-extraction-llms-vs-ocrs) — hybrid pattern.
- [AIMultiple: Invoice OCR Benchmark](https://research.aimultiple.com/invoice-ocr/) — Claude 3.5 Sonnet accuracy leader; Gemini Flash 2.0 ~6000 pages/$1.
- [Koncile: Claude vs GPT vs Gemini for Invoice Extraction](https://www.koncile.ai/en/ressources/claude-gpt-or-gemini-which-is-the-best-llm-for-invoice-extraction) — GPT 98 / Claude 97 / Gemini 96 on text PDFs.
- [Nanonets Pricing](https://nanonets.com/pricing) — free first 100; $499/mo onward.
- [Mindee Invoice OCR API](https://www.mindee.com/product/invoice-ocr-api) — ~96.1% accuracy.
- [Veryfi 2025 OCR Benchmark](https://www.veryfi.com/ai-insights/invoice-ocr-competitors-veryfi/) — Veryfi 98.7 / Mindee 96.1 / GCV 94.3.
- [ChatFin: Invoice Tools 2026](https://chatfin.ai/blog/invoice-processing-tools-comparison-best-ai-platforms-for-finance-teams-2026/) — Rossum ~$18k/yr, 98%+.
- [arXiv 2509.04469: Multi-Modal Vision vs Text-Based Parsing](https://arxiv.org/html/2509.04469v1) — OCR+LLM hybrid competitive with vision at fraction of cost.
- [Donut (clovaai)](https://github.com/clovaai/donut) — reference OCR-free transformer; deployment-heavy.
- [Frankfurter](https://frankfurter.dev/) — free ECB-backed FX, no key.
- [ExchangeRate-API](https://www.exchangerate-api.com/docs/free) — 1,500 req/mo free, 99.99% uptime, 170+ currencies.
- [ECB Data Portal API](https://data.ecb.europa.eu/help/api/data) — authoritative EUR rates.
- [Inngest Scheduled Functions](https://www.inngest.com/docs/guides/scheduled-functions) — timezone-aware cron.
- [LogRocket: Best React Chart Libraries 2025](https://blog.logrocket.com/best-react-chart-libraries-2025/) — Recharts TS-native, SVG.
- [FastMCP: Tools](https://gofastmcp.com/servers/tools) — auto-schema from typed returns.
- [PrefectHQ FastMCP](https://github.com/prefecthq/fastmcp) — structured `ToolResult` patterns.
- [Gemini Structured Output](https://ai.google.dev/gemini-api/docs/structured-output) — JSON-schema-constrained output.
- [AI Cost Check: Gemini 2026 Pricing](https://aicostcheck.com/blog/google-gemini-pricing-guide-2026) — Flash 2.5 at $0.15/$0.60 per 1M tokens.
- [Tiger Data: Indexing JSONB](https://www.tigerdata.com/learn/how-to-index-json-columns-in-postgresql) — GIN `jsonb_path_ops` for hybrid column+JSONB.
- [SitePoint: Postgres JSONB Performance](https://www.sitepoint.com/postgresql-jsonb-query-performance-indexing/) — multi-tenant hybrid pattern.
- [Gennai: Invoice Fraud Detection 2026](https://www.gennai.io/blog/invoice-fraud-detection-prevention-2026) — 79% of orgs saw fraud attempts in 2024 (AFP).
- [HouseBlend: NetSuite Vendor Bill Anomaly Detection](https://houseblend.io/articles/pdfs/netsuite-vendor-bill-anomaly-detection.pdf) — rule taxonomy.
- [Unstract: Python PDF Libraries 2026](https://unstract.com/blog/evaluating-python-pdf-to-text-libraries/) — PyMuPDF's real role.
- [Afternoon: SaaS Chart of Accounts 2026](https://www.afternoon.co/blog/chart-of-accounts) — default taxonomy reference.

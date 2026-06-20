# M2 AI Sales Intelligence — Research & Decisions

**Date:** 2026-04-19
**Status:** Research for team review.
**Depends on:** foundation.md, m1-lara.md

---

## Summary

M2 is the wedge that carries the whole SmartBiz pitch: **"Everyone has a CRM. Don't compete — sit on top and make it smarter."** The module is five cooperating layers — (1) a thin native CRM (so leads from any source have a home), (2) an MCP-based integration layer that pulls from HubSpot / Sheets / Tally / Zoho, (3) a scraper pack for LinkedIn / Product Hunt / directories / review sites, (4) an enrichment pipeline, and (5) an explainable LLM scorer. All five feed into Lara (M1) as MCP tools and into M3 Automation as triggers. Inngest runs the cron loop (scraper passes, re-scoring, stale-lead alerts, polling sync).

Strategic bets this memo locks in:

- **Native CRM is intentionally minimal.** Just enough to own the data model (`leads`, `activities`, `enrichment`, `scores`) so a HubSpot-connected lead and a LinkedIn-scraped lead get the same treatment. We don't try to replace HubSpot's UI.
- **Integration via MCP is the differentiator.** HubSpot shipped an official remote MCP server (GA in late 2025) and Zoho shipped one too. Sheets has strong community servers and a Google remote MCP endpoint. That means 70%+ of the Indian SMB CRM surface is reachable with zero custom OAuth code on our side — Lara connects, the user OAuths through elicitation, and the tools light up. Tally is the one we'll likely have to build.
- **Scraping is mostly seeded for the demo, with 2 live crawlers.** LinkedIn is legally a mine-field; we'll demo the *feature* with pre-scraped seed data and run Product Hunt + directory scrapers live (both legal and cheap).
- **Scoring is LLM-driven and explainable by design.** Output shape: `{value: 0-100, reasons: list[str], category: str}`. Rationale travels with the score, because the whole pitch collapses if Lara can't say *why*.
- **Proxycurl is dead, Clearbit is a HubSpot-only thing now.** Enrichment stack pivots to Apollo.io + PDL + LLM-on-website, with a DetectZeStack-style tech-stack fingerprinter.

---

## Native CRM schema

SQLAlchemy 2.x `MappedAsDataclass` style. Reserved word gotcha: in MappedAsDataclass, `default=` is a dataclass field; use `insert_default=` for DB defaults. ([SQLAlchemy 2.0 dataclasses guide](https://docs.sqlalchemy.org/en/20/orm/dataclasses.html))

**Tables**

- `leads` — core record. Columns: `id UUID`, `created_at`, `updated_at`, `source` (enum: `hubspot | sheets | tally | zoho | scraper_linkedin | scraper_producthunt | scraper_directory | scraper_review | manual | lara`), `source_external_id` (for idempotent upsert from MCP-pulled integrations), `full_name`, `email`, `phone`, `company_name`, `company_domain`, `role`, `stage` (enum — Kanban), `owner_user_id` (nullable), `latest_score_id` (nullable FK to `scores`), `latest_enrichment_id` (nullable FK), `embedding vector(1536)` for similarity/dedup via pgvector.
- `lead_sources` — one row per *ingestion event*, not per lead. Columns: `id`, `lead_id`, `source`, `mcp_server`, `raw_payload JSONB`, `imported_at`. Keeps provenance.
- `lead_activities` — timeline. `id`, `lead_id`, `kind` (email_sent | email_opened | call_logged | stage_changed | note_added | score_changed | enrichment_refreshed | mcp_sync), `payload JSONB`, `actor` (user|lara|cron|integration), `occurred_at`.
- `lead_tags` — N:N via `lead_tag_links`. Tags include system-assigned (`hot`, `cold`, `unhappy-competitor-customer`) and user-assigned.
- `lead_notes` — free-text, `author_id`, `body`, `created_at`.
- `enrichment_data` — 1:N over time (history kept for diff + explainability). Columns: `id`, `lead_id`, `company_summary`, `company_size`, `industry`, `funding_stage`, `recent_news JSONB`, `tech_stack JSONB`, `person_role`, `person_seniority`, `website_analysis_text`, `website_embedding vector(1536)`, `raw_sources JSONB`, `enriched_at`, `enricher_version`.
- `scores` — 1:N over time. Columns: `id`, `lead_id`, `value int`, `category str` (hot/warm/cold/unqualified), `reasons JSONB[]`, `rubric_version`, `model`, `scored_at`, `cost_cents`.

**Relationships**

- `lead → activities` 1:N
- `lead → tags` N:N
- `lead → enrichment_data` 1:N (keep history; `latest_enrichment_id` is a denormalized pointer for speed)
- `lead → scores` 1:N (same pattern)

**Kanban stages (V0)** — hardcoded: `New → Contacted → Qualified → Meeting → Proposal → Won → Lost`. Seven stages keeps the board readable at demo density. Making stages configurable is a reasonable V1 ask but adds migration + UI state machine complexity. Call-out: HubSpot / Zoho come with their *own* pipelines — on sync we map their stage string to ours via a simple dictionary, stored per-integration.

**Embeddings** — the `leads.embedding` and `enrichment_data.website_embedding` let us answer: (a) "find leads similar to this closed-won deal" and (b) soft dedup (two LinkedIn scrapes of the same person under slightly different names). pgvector is already in the stack; no new infra.

---

## Integration layer (MCP-first)

The pitch collapses if the first ten minutes aren't "connect HubSpot → ask Lara". Every integration is a FastMCP server (or a remote MCP endpoint we're a *client* of). Lara sees the tools via the gateway regardless of which side hosts the server.

### HubSpot

**Good news, and the biggest reason M2 is demo-able.** HubSpot ships an [official remote MCP server](https://developers.hubspot.com/mcp) (public beta 2025, [GA late 2025](https://developers.hubspot.com/changelog/remote-hubspot-mcp-server-is-now-generally-available)). Endpoint: `https://mcp.hubspot.com`. Auth is **OAuth 2.1 with PKCE**. Covers read/write for contacts, companies, deals, tickets, engagements, line items, products, plus read-only for invoices, quotes, subscriptions, segments/lists.

**Our integration = we're an MCP client**, not a server. Lara talks to the gateway; the gateway talks to `mcp.hubspot.com` on the user's behalf using tokens we hold. We don't write HubSpot tool definitions — we proxy.

### Google Sheets

Multiple paths. (a) Google announced [official remote MCP support for Google services](https://cloud.google.com/blog/products/ai-machine-learning/announcing-official-mcp-support-for-google-services) — enterprise-ready endpoint for Workspace. (b) Strong community Python servers (`mcp-google-sheets` by xing5, `mcp-gdrive`) are production-grade. **For V0, pick the community server** (`mcp-google-sheets`) — it's Python, installs cleanly, and we avoid waiting on Workspace admin consent screens during a demo. Use `ENABLED_TOOLS` env to trim the 19-tool surface down to ~5 to save context tokens.

### Tally

No public MCP server exists. Tally's "API" in 2026 is still a local XML/HTTP interface exposed by the TallyPrime process on the customer's machine, plus a set of [third-party API bridges](https://api2books.com) that wrap it. **We build a FastMCP server ourselves** that speaks to either (a) the local TallyPrime XML port or (b) the `api2books`-style cloud bridge. For a portfolio demo we can ship a seeded Tally integration (pretend the connection is live, pipe in a CSV export). For a real client we'd need their on-prem Tally port-forwarded or a cloud-bridge subscription. **Flag as V0-stub, V1-real.**

### Zoho

[Zoho MCP](https://www.zoho.com/mcp/) launched in 2025 and now exposes CRM, Books, Desk, Mail, Calendar, Projects, Cliq, Analytics. OAuth-based. Several community servers exist too (Junnai, Mgabr, CData). **V0: defer.** HubSpot + Sheets + Tally covers the pitch (international + DIY + Indian SMB). Zoho is a two-day follow-up once the first three are solid.

### OAuth + elicitation flow

The MCP spec added **URL-mode elicitation** in the draft basic authorization flow — a server can pause a tool call and hand the user a URL to complete OAuth out-of-band. Claude Code 2.1.76 (March 2026) was the first major client to support it widely. ([Cisco on MCP elicitation](https://blogs.cisco.com/developer/whats-new-in-mcp-elicitation-structured-content-and-oauth-enhancements); [MCP spec draft](https://modelcontextprotocol.io/specification/draft/basic/authorization))

Our flow for an integration like HubSpot:

1. User says "connect HubSpot" in Lara.
2. Lara calls `integration.connect(provider='hubspot')` on our gateway.
3. Gateway starts an OAuth 2.1 PKCE dance, returns a `url-elicitation` response with the authorize URL.
4. Frontend catches the elicitation, opens a popup / new tab.
5. User OAuths; HubSpot redirects to our callback; we persist the refresh token per-user per-provider.
6. Gateway resolves the paused call; Lara confirms "HubSpot connected."
7. Subsequent tool calls proxy to `mcp.hubspot.com` with a freshly-minted access token (we rotate refresh tokens per MCP OAuth 2.1 spec requirement).

**Token storage:** Postgres `integration_tokens(user_id, provider, access_token_encrypted, refresh_token_encrypted, scopes, expires_at)`. Encrypt at rest with a KMS-held key (call it out in Foundation).

### Sync pattern

**V0: polling via Inngest cron, every 60 min.** Polling is one-line cron logic, zero infra, works the same across providers. Webhooks are a better story for V1 (HubSpot has rich webhooks; Zoho does; Sheets has push notifications with a renewal dance; Tally has none). For V0 demo velocity the 1-hour sync window is a feature, not a bug — "Lara noticed 3 new HubSpot leads overnight" is a demo moment we *want*.

**Tagging:** every lead row gets `source` + a `lead_sources` provenance row. Scoring and enrichment must be source-agnostic (same rubric across a HubSpot lead and a LinkedIn-scraped lead) so "which should I call first" answers don't lie.

---

## Scraper architecture

### LinkedIn — legal realities

Short version: **scraping LinkedIn at any meaningful scale is hostile territory in 2026.** The hiQ v. LinkedIn case ultimately [settled in LinkedIn's favor in 2022](https://en.wikipedia.org/wiki/HiQ_Labs_v._LinkedIn) — the CFAA theory that made public scraping "criminal" was rejected, but LinkedIn won on breach-of-contract (their User Agreement forbids automated access). "Legal under CFAA" is **not** the same as "safe to run as a business." LinkedIn can and does sue, ban IPs, ban accounts, and demand downstream data destruction. ([nubela.co: "I was sued by LinkedIn"](https://nubela.co/blog/is-scraping-linkedin-legal-in-2026/))

Options, ranked:

1. **Simulated seed data for the demo.** 100 pre-scraped profiles baked into the demo dataset. The *feature* (Lara ingesting LinkedIn leads) is shown; the *pipeline* is not actually running. **This is the V0 pick.**
2. **Third-party aggregator API.** Apollo.io (the only remaining cheap option since Proxycurl shut down July 2025). Buys you licensed person+company data without touching LinkedIn directly. ~$49/user/mo starter. Recommended for V1 once we have paying clients.
3. **Sales Navigator partner API.** Official, expensive, requires enterprise motion.
4. **Self-hosted Playwright + rotating residential proxies.** Works, demonstrably risky, not a business foundation.

Decision: **V0 = option 1; V1 = option 2.** Do not run a LinkedIn crawler from our infrastructure during the demo.

### Product Hunt

Public GraphQL API at `https://api.producthunt.com/v2/api/graphql` with OAuth. Non-commercial by default, email `hello@producthunt.com` for commercial OK. For V0/portfolio use we're fine on the free tier. **This is a live scraper** — a daily Inngest cron pulls today's launches, filters by topic (AI, SaaS, fintech), enriches the maker's LinkedIn/Twitter, and creates a `lead` with `source=scraper_producthunt`. Cheap, fast, legal. Great demo moment.

### Directories (Clutch, G2 company pages)

Firecrawl for structured extraction. LLM-friendly markdown output, Pydantic-schema extraction (we'll wrap the Pydantic boundary at the Firecrawl edge only). ([firecrawl.dev](https://www.firecrawl.dev/blog/best-open-source-web-crawler)) Alternative: self-hosted Playwright + BeautifulSoup for the free route. **V0: use Firecrawl's hosted API** to avoid Playwright infra for the demo. Directory scrape runs weekly.

### Competitor reviews (G2, Trustpilot)

This is the narrative-rich one: *"This person left a 2-star review on Competitor X = warm lead."*

Stack: Firecrawl to pull review text → LLM sentiment + theme extraction → tag the reviewer (if identifiable) as `unhappy-competitor-customer`. G2 includes reviewer company + title on public reviews, which is enough to enrich into a full lead. ([Scrapfly guide](https://scrapfly.io/blog/posts/how-to-scrape-g2-company-data-and-reviews))

Ethical / ToS callout: G2 and Trustpilot both prohibit scraping in their ToS. Run this rarely, not aggressively. For demo, **seed** competitor review data and run a live scrape of *one* competitor page at demo time to show the mechanism.

### Recommended V0 scope (live vs seeded)

| Source | V0 mode | Why |
|---|---|---|
| HubSpot MCP sync | **Live** | Demo centerpiece |
| Sheets MCP sync | **Live** | Trivial to demo |
| Tally MCP | Stubbed (live FastMCP server, seeded data) | No real customer Tally during demo |
| Product Hunt | **Live** (daily cron) | Legal, cheap, demo-cool |
| Directory (one site, e.g. Clutch) | **Live** (weekly) | Shows scraper capability |
| G2/Trustpilot reviews | **Seeded + one live demo crawl** | ToS risk, narrative-critical |
| LinkedIn | **Seeded only** | Legal risk too high |

Two live scrapers (PH + directory) is enough signal; the rest are pre-loaded fixtures.

---

## Enrichment pipeline

**Trigger:** every new lead (any source) emits an Inngest event `lead.created`. The enrichment function fans out steps.

**Steps**

1. **Company lookup.** Domain → Apollo.io company endpoint OR our own cache. Returns industry, employee band, funding, HQ.
2. **Person lookup.** Name + company → Apollo.io contact OR People Data Labs (PDL). Returns current role, seniority, prior companies. ~$0.05–$0.10/lookup at Apollo starter tier.
3. **Recent company news.** NewsAPI or Google News RSS; last 30 days; LLM summarizes to 3 bullets.
4. **Website analysis (LLM-driven).** Firecrawl the homepage + /about + /pricing → single Sonnet prompt: *"Extract: what they do, ICP/customer type, product maturity stage, urgency signals."* Produces a short structured text + embedding.
5. **Tech stack detection.** DetectZeStack API ($15/mo at 25k req) or the open-source `wappalyzergo` engine self-hosted. ([Wappalyzer alternatives](https://seomator.com/blog/wappalyzer-alternatives)) The original Wappalyzer was acquired by Sindup in Aug 2023 and the open-source repo archived, so don't rely on the NPM package alone.

**Why not Clearbit or Proxycurl:** Clearbit is now "Breeze Intelligence" inside HubSpot and won't sell outside the HubSpot ecosystem. Proxycurl shut down July 2025 despite $10M ARR. ([crustdata on alternatives](https://crustdata.com/blog/people-data-labs-alternatives-b2b-data-providers)) Apollo + PDL + our own LLM website pass is the new default.

**Cost per enrichment at demo scale.** Rough math with Sonnet-class model + Apollo starter:

- Apollo person + company: ~$0.10
- Firecrawl 3 pages: ~$0.015
- LLM website analysis (3k in / 500 out tokens, Sonnet): ~$0.015
- News summary: ~$0.005
- Tech stack: ~$0.0006 (flat-rate API)
- **~$0.14 per enrichment, ~$14 for a 100-lead demo corpus.** Fine.

**Storage.** `enrichment_data` row per pass (history preserved). JSONB raw sources. `website_embedding` for "find me leads that look like our best closed-won customers."

---

## Lead scoring (explainable)

Scoring lives in one FastMCP tool: `crm.score_lead(lead_id)`. It returns and persists a structured result.

**Output shape (stdlib dataclass, not Pydantic — matches locked stack rule):**

```python
@dataclass
class LeadScore:
    value: int            # 0-100
    category: str         # "hot" | "warm" | "cold" | "unqualified"
    reasons: list[str]    # 3-5 short human-readable clauses
    rubric_version: str
    model: str
    scored_at: datetime
```

LLMs reliably return structured JSON in 2026 — OpenAI, Anthropic, and Gemini all support native structured output. ([techsy.io structured output guide](https://techsy.io/en/blog/llm-structured-outputs-guide)) We use the provider-agnostic AI client already chosen for M1; the schema is the dataclass above, serialized via `dataclasses.asdict`.

**Rubric prompt** (V0, one prompt, versioned):

> Given this lead's {enrichment, activities, source}, score buying intent 0–100 and classify hot/warm/cold/unqualified. Return 3–5 short reasons. Weigh: explicit buying language, employee count 20+, funding within 12mo, tech stack implying our ICP, recent role change, negative competitor sentiment. Penalize: generic email domain, no role, no website activity.

**Cross-source normalization.** The scorer sees `enrichment_data` + `lead_activities` only — never the original `source`. This guarantees a HubSpot lead and a LinkedIn-scraped lead get scored on the same rubric. The integration layer feeds activities into the same `lead_activities` table regardless of source.

**Caching / re-scoring.** Don't re-score on every read. Inngest re-scores every 48h per lead. The cron job also applies a **time-decay**: reasons referencing "recent" signals lose weight at a 30/60/90 day step function — full points in last 30 days, 75% to day 60, 50% to day 90, reset to baseline after 90 days of silence. ([Ortto lead scoring guide](https://ortto.com/learn/what-is-lead-scoring/); [DemandZen on score decay](https://demandzen.com/lead-scoring-best-practices-negative-signals/)) Implementation: half-life is computed against `lead_activities.occurred_at`, not by re-prompting the LLM — cheaper and more predictable.

**Score transparency is a sales weapon.** When Lara says *"Call this lead first — scored 85 because they left a 2-star review on Competitor X last week, head of ops at a 60-person fintech, visited pricing twice"*, that's the demo. The `reasons` field is the hero.

---

## Cron jobs (Inngest)

All scheduled work runs through Inngest Python SDK with FastAPI. ([inngest-py](https://github.com/inngest/inngest-py); [cron docs](https://www.inngest.com/docs/guides/scheduled-functions))

| Job | Cron | Purpose |
|---|---|---|
| `integrations.sync_hubspot` | `0 * * * *` (hourly) | Poll HubSpot MCP for new/changed records; upsert by `source_external_id` |
| `integrations.sync_sheets` | `0 * * * *` (hourly) | Same for connected sheets |
| `integrations.sync_tally` | `0 */6 * * *` (6h) | Pull Tally receivables → emit `tally.invoice.unpaid` events (feeds M6 not M2, but shares the cron) |
| `scrapers.producthunt_daily` | `0 6 * * *` | Scrape yesterday's launches |
| `scrapers.directory_weekly` | `0 2 * * 1` | One directory, Monday 2am |
| `scrapers.reviews_weekly` | `0 3 * * 1` | Competitor reviews, Monday 3am |
| `enrichment.refresh_stale` | `0 2 * * *` | Re-enrich leads with enrichment older than 30 days |
| `scoring.rescore_all` | `0 4 */2 * *` (every 48h) | Re-score + apply time-decay |
| `alerts.stale_leads` | `0 9 * * *` | Find leads with no follow-up in 7 days → Lara notification |
| `alerts.hot_leads_overnight` | `0 8 * * *` | "3 new high-score leads overnight" digest |

Inngest timezone gotcha: cron schedules have known DST edge cases in local TZ. Pin everything to UTC and display local TZ in the UI. ([Inngest cron docs](https://www.inngest.com/docs/guides/scheduled-functions))

**Failure semantics.** Inngest retries with exponential backoff. For integration sync jobs, a persistent failure surfaces as an in-app notice ("HubSpot token expired, reconnect?"), not a silent skip.

---

## Lara MCP tool surface

M2 ships a `crm.*` FastMCP server. Tools exposed via the gateway:

- `crm.add_lead(data) -> Lead` — manual / Lara-created
- `crm.update_lead(id, patch) -> Lead`
- `crm.list_leads(filter) -> list[Lead]` — filter supports stage, tag, score range, source, owner
- `crm.get_lead(id) -> LeadDetail` — includes activities, latest enrichment, latest score
- `crm.score_lead(id, force=False) -> LeadScore` — idempotent per 48h window unless `force`
- `crm.enrich_lead(id) -> EnrichmentData`
- `crm.get_activity_timeline(id, limit=50) -> list[Activity]`
- `crm.search_leads(natural_query) -> list[Lead]` — embeds query, cosine against `leads.embedding` and `enrichment_data.website_embedding`; LLM re-ranks top 20
- `crm.add_note(lead_id, body)`
- `crm.change_stage(lead_id, stage)`
- `integrations.connect(provider)` — triggers OAuth URL-elicitation (see §2)
- `integrations.status() -> list[ConnectedProvider]`

**Demo flow:** *"Connect HubSpot" → OAuth elicitation popup → "done" → "Lara, who should I call first today?"* → Lara calls `crm.list_leads(filter={min_score:80, stage:'Qualified'})`, gets ranked list with reasons, streams to UI. Total clicks: 3.

---

## Legal/compliance callouts

- **LinkedIn scraping.** Do not run live LinkedIn scrapers from our infra. hiQ-settlement means "public profiles" is not a safe harbor against LinkedIn's User Agreement claims. Use Apollo/PDL in V1.
- **G2 / Trustpilot.** ToS forbids scraping. Limit to occasional, low-volume pulls. Do not resell the extracted data. The *derived* insight ("competitor has unhappy customers") is fine; the raw review corpus is not.
- **DPDP Act (India).** Full substantive compliance mandatory by **May 13, 2027**; Consent Manager registration opens Nov 13, 2026. ([Secure Privacy on DPDP Phase 1](https://secureprivacy.ai/blog/india-dpdp-act-phase-1)) For V0 portfolio demo with seed / test data, we're not a "Data Fiduciary" in the legal sense yet. For any paying client, we need: (a) purpose-specific consent collection, (b) data flow mapping, (c) breach protocol, (d) data subject rights API (access/erase). Penalties up to INR 250 crore. **Call out in the demo narrative: "built DPDP-aware" — data subject endpoints are already in the schema (soft delete, tombstone markers), consent flows plug in on the onboarding side."**
- **GDPR.** Same shape as DPDP for EU-located leads; our enrichment pulling EU person data needs a lawful basis. V0 demo is fine; EU-facing client work needs DPIA.
- **Secrets.** Integration tokens encrypted at rest. Encryption key rotation policy deferred to Foundation.

---

## Open questions

1. **Which directory do we actually scrape live for the demo?** Clutch (dev shops), G2 (software), Product Hunt Makers, or something India-local like YourStory? Picking one narrows the seed corpus design.
2. **Tally: local port vs cloud bridge.** For a real client deployment, do we require them to expose their TallyPrime XML port via a tunneled agent, or do we require an `api2books`-style paid bridge? Materially changes the sell.
3. **Score rubric versioning strategy.** When we change the rubric, do old scores auto-invalidate (re-score on next read) or stay pinned? Proposed: pin, show "rubric v1.0 — re-score?" badge.
4. **pgvector dedup threshold.** What cosine similarity counts as "same person"? Needs calibration on seed data. Default guess: 0.92.
5. **Do we need webhooks for HubSpot in V0?** Hourly polling + "Lara noticed N new leads overnight" is arguably *better* narrative than instant sync. Team call.
6. **FastMCP + dataclass tool signatures.** Flagged in foundation doc — if FastMCP forces Pydantic at the tool boundary, isolate the conversion in one adapter.

---

## Gotchas

- **MappedAsDataclass `default` is a reserved word** — use `insert_default` for DB-side defaults or hit a silent dataclass collision.
- **HubSpot MCP requires PKCE** — don't try to use the legacy HubSpot OAuth flow; it won't give MCP-scoped tokens.
- **Google Sheets MCP tool count** — community server ships 19 tools, ~13k tokens of context. Cherry-pick with `ENABLED_TOOLS` env var or we lose half Lara's working context on Sheets alone.
- **Firecrawl and ScrapeGraphAI both Python-side** — good. Don't re-implement scrapers in the TS frontend.
- **Proxycurl links in old tutorials are dead.** Any 2024/early-2025 enrichment tutorial using Proxycurl is misleading — swap to Apollo/PDL before copying code.
- **Clearbit is now HubSpot-only** — don't sign up expecting a standalone API; you'll be funneled into a HubSpot subscription.
- **Inngest cron DST.** Pin schedules to UTC. Display local TZ at UI layer only.
- **MCP elicitation client support is uneven.** Claude Code 2.1.76+ has it; our own web frontend needs to implement the URL-elicitation response handling (popup/new-tab + return-to-chat) explicitly — not a framework freebie.
- **LinkedIn user-agreement lawsuits name individual engineers.** Not a cost we eat for a portfolio demo.
- **Seeded scraper data must be watermarked.** Every fixture record tagged `demo_seed=True` so a future production deploy can't accidentally train a scorer on fake data.
- **Token cost of scoring 1000 leads on rescore cron.** 1000 × ~3k in / 300 out Sonnet = ~$5 per 48h. Fine now, scale awareness for later.

---

## Sources

- HubSpot MCP Server (official): https://developers.hubspot.com/mcp
- HubSpot Remote MCP GA changelog: https://developers.hubspot.com/changelog/remote-hubspot-mcp-server-is-now-generally-available
- Zoho MCP: https://www.zoho.com/mcp/
- Google MCP announcement: https://cloud.google.com/blog/products/ai-machine-learning/announcing-official-mcp-support-for-google-services
- mcp-google-sheets (xing5): https://www.blog.brightcoding.dev/2026/04/13/mcp-google-sheets-transform-ai-into-spreadsheet-powerhouse
- MCP Authorization spec (draft): https://modelcontextprotocol.io/specification/draft/basic/authorization
- MCP Elicitation (Cisco): https://blogs.cisco.com/developer/whats-new-in-mcp-elicitation-structured-content-and-oauth-enhancements
- FastMCP: https://github.com/jlowin/fastmcp
- Inngest Python SDK: https://github.com/inngest/inngest-py
- Inngest cron guide: https://www.inngest.com/docs/guides/scheduled-functions
- hiQ Labs v. LinkedIn (Wikipedia): https://en.wikipedia.org/wiki/HiQ_Labs_v._LinkedIn
- "Is scraping LinkedIn legal in 2026" (Nubela): https://nubela.co/blog/is-scraping-linkedin-legal-in-2026/
- Firecrawl comparison: https://www.firecrawl.dev/blog/best-open-source-web-crawler
- Scrapfly G2 scraping guide: https://scrapfly.io/blog/posts/how-to-scrape-g2-company-data-and-reviews
- Proxycurl shutdown + alternatives (Crustdata): https://crustdata.com/blog/people-data-labs-alternatives-b2b-data-providers
- Apollo.io: https://www.apollo.io/solutions/b2b-data-enrichment
- Wappalyzer alternatives (SEOmator): https://seomator.com/blog/wappalyzer-alternatives
- SQLAlchemy 2.0 dataclass mapping: https://docs.sqlalchemy.org/en/20/orm/dataclasses.html
- Product Hunt API docs: https://api.producthunt.com/v2/docs
- DPDP Act Phase 1 guide (Secure Privacy): https://secureprivacy.ai/blog/india-dpdp-act-phase-1
- Tally API bridges: https://api2books.com
- Lead score decay (DemandZen): https://demandzen.com/lead-scoring-best-practices-negative-signals/
- LLM structured outputs 2026: https://techsy.io/en/blog/llm-structured-outputs-guide

# SmartBiz OS — TODO

Honest accounting of what's not done. Roughly ordered by impact.

---

## ✓ Done in 2026-05-01 product-pivot session

- [x] **Real scrapers for all sources** — YC directory (5,690 companies), Apollo, Hunter.io, HN Show HN + Hiring, Product Hunt, TechCrunch, GitHub Trending. LinkedIn stays seeded only (legal).
- [x] **Hybrid page fetcher** — httpx → Firecrawl waterfall; saves credits.
- [x] **LLM ICP scoring** with 5-dimension rubric, prompt-injection guards, per-workspace tunable description (workspace_settings + /admin/settings page).
- [x] **CSV import** — paste/upload → preview → header-mapping → commit. Dedupes on email.
- [x] **AI opening-line generator** — per-lead personalized opener grounded in source signal. The wedge differentiator vs Apollo/Smartlead.
- [x] **Slack webhook on hot leads** — workspace_settings.slack_webhook_url; auto-fires when score crosses threshold.
- [x] **LeadDrawer Source card** — surfaces scraper enrichment as structured fields (tech, Hunter intel, deliverability) instead of notes blob.
- [x] **Free-text search on /admin/leads** — backend ILIKE across name, email, company.
- [x] **Manual notes on lead timeline** — POST /api/leads/{id}/notes.
- [x] **"Start sequence" wired to template picker** — killed the warm_v1 TODO.
- [x] **Production-bar bug fixes** — ICP prompt sanitization + .format() KeyError, convert TOCTOU race with FOR UPDATE, request_timeout on every litellm.acompletion path.
- [x] **Reports compare** — silent dead-end replaced with toast.

## P0 — Lying to the user

These are stubs the UI presents as if they were real. Misleading in a demo:

- [x] ~~Automation `send_day0` doesn't actually send email.~~ — DONE 2026-05-01. Active path is `automations/scheduler.py::send_day0` which calls real `automations/email.py::send_email` via Resend (with `RESEND_API_KEY` + `RESEND_FROM`). The Inngest function path is unused but no longer fakes the message_id either.
- [x] ~~Automation `wait_3_days` is 8 seconds.~~ — DONE 2026-05-01. Default flipped to `3 * 86400` (real cadence). Dev environments override via `AUTOMATION_WAIT_SECONDS=8` in `.env`.
- [x] ~~Integration "Connect" is fake OAuth.~~ — DONE 2026-05-01 (commit 93b0e32). Backend now returns 501 honestly; FE replaced "Connect" with disabled "Coming soon" chip. Real OAuth adapters when one ships (HubSpot first).
- [ ] ~~Integration "Sync now" doesn't sync anything.~~ — Endpoint did not actually exist; only IMAP poll-now (which is real). Removed from concern list.
- [x] ~~Scraper "Run now" doesn't scrape.~~ — DONE 2026-05-01. Eight real sources wired.
- [ ] **Voice (Gemini Live API) returns 1008 on connect.** Code is correct; the model alias `gemini-live-2.5-flash-native-audio` requires a tier we don't have. Either upgrade the Gemini API tier, or migrate the voice path to Cartesia / MiniMax / Deepgram.

## P-NEW — From 2026-05-01 competitive scan (build before pricing)

Per Apollo/Clay/Smartlead/Instantly/Reply.io research — table-stakes that
a paying user expects in this category. SmartBiz cannot ship as a real
outbound product without these:

- [x] **Reply detection** — manual button + IMAP poller landed in sprint-1. Catches the catastrophic "sequence keeps firing after reply" failure mode. Path: per-tenant IMAP creds (Fernet-encrypted), poll every 10 min, match by sender email, flip lead.sequence_state=paused_replied, scheduler skips send_* steps. (commits d4076d1, e43a410)
- [ ] **Multi-mailbox sender rotation** — connect N inboxes via SMTP, distribute sends round-robin per sequence, surface per-mailbox health. Sending 100+ emails/day from one inbox flags it within weeks. Resend isn't a warmup network — point users at Mailreach/Warmup Inbox for warmup and own only the rotation mechanics.
- [x] **Bulk actions on /admin/leads** — done (commit e796eb6).

## Sprint-1 — May 2026 PM-grounded sprint

Pass A/B/C of the May-2026 PM workflow defined: persona (Marcus, founder-closer), 5 friction points, 3-feature PRD. Shipped in a 10-day sprint:

- [x] **ICP wizard** — 3-step inline, 6 archetype templates, no LLM. Replaces blank textarea on /admin/settings. Day 1-2. (commit 20ef3cc)
- [x] **Inbox empty-state diagnostics** — 5 cards (run_scraper / check_sources / all_triaged / lower_threshold / loosen_icp) each with concrete next-action CTA. Inline 4-bucket score histogram. Day 3-4. (commit 9dec6c9)
- [x] **Manual reply detection + scheduler guard** — leads.sequence_state, "Mark replied" button, "Resume sequence" button, scheduler skips send_* when paused_replied. Day 5-6. (commit d4076d1)
- [x] **IMAP reply detection** — workspace_imap_settings (Fernet-encrypted), background poller every 10 min, auto-reply filter, idempotent on (lead, source, ±60s). Settings card with provider presets + test-then-save flow. Day 7-9. (commit e43a410)
- [x] **Polish** — `reply_received` activity icon + color, "replied" chip on lead cards, TODO.md sprint log. Day 10.

**Skipped per plan:** telemetry events, public landing page, Resend webhook → activity timeline, OAuth Gmail, sentiment classification.

## P1 — Holes in core features

- [ ] **Lead enrichment via Firecrawl.** Wired in `routers/enrichment.py` but never tested end-to-end with a real Firecrawl call against a fresh lead. Likely silently fails on non-trivial input.
- [x] ~~Score history exists but isn't surfaced in the UI.~~ — DONE 2026-05-01. `ScoreSparkline` renders an inline 220×36 sparkline + delta inside the score-explainer card in `LeadDrawer.jsx`, fed by `/api/leads/{id}/score/history?limit=20`.
- [ ] **Documents RAG retrieval not surfaced.** Upload writes embeddings to `lara_memory`. Search exists in the gateway tool, but the chat doesn't actually call it / show citations on retrieval.
- [ ] **Memory page lists facts but nothing reads them.** No tool surfaces them back into Lara context. Need a `memory_recall` tool wired into the system prompt.
- [ ] **Reports `compare` page is barely tested.** The endpoint works; the FE comparison card UI hasn't been visually inspected with real diffs.
- [x] ~~Webhooks signature verification + tenant lockdown.~~ — DONE 2026-05-02 (commit e5b2265). Generic `/incoming` (X-Webhook-Token), Tally HMAC, HubSpot v3 with anti-replay window. Endpoints return 501 instead of accepting unsigned input. Tenant always `_tenant()` — header-spoof closed. Still: live-fire test against real provider payloads.
- [ ] **Demo Lara token counter is fake.** Always shows 432/2000. Need a real token counter from LiteLLM usage stats.
- [ ] **Conversations list / detail incomplete.** ConversationsList shows "No conversations" because /api/stream/chat doesn't persist to the Conversation table. Need to wire stream completions → Conversation rows.

## P2 — Auth / multi-tenancy / security

- [ ] **Hardcoded `DEFAULT_TENANT_ID`.** Single-tenant only. Every `_tenant()` call in routers reads the same env var. Real multi-tenant needs `tenant_id` derived from the authenticated session.
- [ ] **Demo session can read all admin data.** A visitor with `demo_session` cookie can hit `/api/leads`, `/api/automations/runs`, etc. — there's no auth gate beyond session presence. Need a `require_admin` dependency on writes + scope reads to demo's own tenant.
- [ ] **JWT_SECRET is `dev-secret-change-me`.** Production deploy needs a generated secret stored in Render env.
- [ ] **No CSRF protection.** Relying on `samesite=lax` cookies. Probably fine, but document.
- [ ] **No rate limiting.** Anyone hitting the public ngrok URL can spam `/api/reports/generate` (LLM cost) or `/api/automations/runs` (DB writes). Need slowapi or similar at minimum on the LLM endpoints.
- [ ] **No admin team management.** Admins are bootstrapped from `ADMIN_USERS_JSON` env or seeded once. No UI to add/remove admins, rotate passwords, etc.
- [ ] **CORS allows everything** in dev. Production should lock down to the actual frontend origin.

## P3 — Deployment / ops

- [ ] **Render deploy never tested live.** `render.yaml` exists but no actual production deploy yet. Verify with `make deploy-render`, set env vars in Render dashboard, confirm /health responds.
- [ ] **Vercel deploy never tested live.** Same — `make deploy-frontend` exists but untried.
- [ ] **Custom domain mapping.** User has a domain; needs CNAME → Vercel + Render edge.
- [ ] **No proper migration system.** `apply_migration.py` is a hand-rolled splitter. Should switch to Alembic before the schema changes again, or at least add a `migrations/applied.txt` ledger so we know what's been run.
- [ ] **Environment vars not documented for prod.** `.env.example` lists keys but no doc on what each one does or which are required for which feature.
- [ ] **No CI beyond GitHub Actions skeleton.** Tests aren't run on PR, deploy isn't automated.
- [ ] **Inngest in production** — currently dev gateway only. Either set up Inngest Cloud signing keys or commit to the BackgroundTask path and document the trade-off (no durability across restarts).

## P4 — Observability

- [ ] No structured logging (currently `print()` everywhere).
- [ ] No error tracking (Sentry / Honeybadger).
- [ ] No metrics or request-time histograms.
- [ ] No alerts when an automation run fails or a scraper errors.

## P5 — UX polish

- [ ] **Skeleton loaders.** Most pages show plain "loading…" text. Replace with actual skeleton placeholders so first-paint feels less janky.
- [ ] **URL-persisted filters** on leads list (kind, source, score range). Currently lost on reload.
- [ ] **Mobile responsive.** Sidebar + kanban don't collapse below ~900px.
- [ ] **No light mode.** Dark only.
- [ ] **Drag-and-drop kanban** can desync if optimistic move + server reorder race. Add a transaction id or sequence number.
- [ ] **Empty states** are generic. Each page should have a tailored empty-state with a clear next action.
- [ ] **Keyboard shortcuts** beyond ⌘J are not documented or visible.

## P6 — Testing

- [ ] Backend tests for the DB-backed paths got deleted (they were testing the old in-memory mocks). Need fresh ones for: scheduler tick + step transitions, /reports/generate stats math, /integrations connect/disconnect upsert.
- [ ] Frontend tests are 5 trivial ones — need component tests for Kanban, StartRunModal, ReportsList.
- [ ] No E2E suite. Could add Playwright on top of the puppeteer scaffolding.
- [ ] No load testing — don't know how many concurrent users Neon free tier supports.

## P7 — Module roadmap

- [ ] **M4 Voice** — blocked on Live API tier (see P0). When unblocked: barge-in, transcript persistence into Conversation table, voice-driven CRM tools.
- [ ] **M5 Mobile / responsive** — entire effort.
- [ ] **M7 Whatever-was-skipped** — confirmed out of scope per user, but worth re-checking when MVPs of M1–M6 are real.

---

## Done ✓ (recent context)

- Real DB backing for automations, reports, integrations, scrapers.
- Inline-step execution fallback when Inngest dev gateway is offline.
- LiteLLM-driven Lara chat (was google-genai with aiohttp bug).
- AI-SDK v1 data-stream protocol on `/api/stream/chat`.
- SWR client cache + lazy-loaded module chunks (initial bundle 695KB → 219KB).
- gzip + Cache-Control on read-only endpoints.
- All FE seed/fallback files removed.
- ngrok-friendly dev server config.

## Done ✓ Review pass (2026-05-01 → 2026-05-02)

Two-agent audit (code-reviewer brutal-honesty + flow-audit user-journey):

- ICP scoring + opener generator + IMAP reply-pause confirmed as real
  wedge differentiation vs Apollo/Clay/Smartlead.
- **Code review fixes** (commit 93b0e32): integrations Connect/Sync now
  honestly disabled; `wait_open` no longer fakes "opened" event;
  `_is_auto_reply` parses RFC 3834 primary tokens; LeadDrawer poll-leak
  fixed across rapid clicks + leadId switches; IMAP Save gated on
  successful Test; Inbox `limit=500` → "showing N of M" + Load more.
- **Flow audit fixes** (commit e5b2265): scrubbed `M1/M2/M3/M6 ·` module
  prefixes from breadcrumbs + sidebar + page bodies; removed Integrations
  from top-nav (route still works for deep-links); replaced
  `window.prompt` for Mark Replied with inline modal; live reply-rate on
  Home (`/api/leads/sequence-stats`).
- **Webhook security** (commit e5b2265): signature verification for
  Tally + HubSpot v3 + token-gated generic `/incoming`. Closed
  `X-Tenant-Id` header-spoof hole.

---

## Feature roadmap brainstorm — what to ship next

Categorized. Each item is one-line value + a difficulty hint (S/M/L).
Top picks for the next sprint marked ★. Validated against the May-2026
trend scan (B2B outbound) — the trend agent's top-3 picks are now
front-loaded in their respective sections.

**Trend-validated theses:**
- "Personalized first line" is table stakes; the lift comes from stacking
  2-3 signals (trigger event + public-footprint insight). Deepen the
  wedge with multi-signal grounding, not more openers.
- Google/Microsoft tightened bulk-sender enforcement late 2025. SPF +
  DKIM + DMARC + 1-click-unsub + sub-0.3% complaint + sub-2% bounce are
  enforcement lines, not nice-to-haves. Multi-domain routing required
  above ~few-hundred sends/week.
- Top buying-intent signals (high→low): job change > active hiring >
  funding (30-45d window) > tech-stack change > competitor-review
  activity > LinkedIn engagement (sleeper, not commoditized).
- LinkedIn-only is dead. Multi-channel where LinkedIn is touch 2-3
  generates 40% higher engagement than single-channel.
- Overhyped (skip): full AI-SDRs, volume spray, generic GPT openers,
  warmup-only solutions, open-rate as a metric.

### A. Wedge deepening (AI personalization)
- ★★ **Trigger-signal scoring layer** (M) — TREND-AGENT TOP-1. Add a
  job-postings parser (Greenhouse/Lever feeds) + funding watcher
  (Crunchbase webhook or Tracxn) on top of ICP. When a lead matches a
  fresh trigger, surface in inbox with the trigger context. Converts
  static ICP into time-sensitive scoring; defensible vs Apollo.
- ★★ **Reply intent classification + sentiment** (M) — TREND-AGENT TOP-3
  (combined with reply-pause we already have). On IMAP-detected reply,
  LLM classifies {positive, negative, auto-reply, wrong_person}, routes
  hot replies to top of inbox, gives data on which messaging variants
  generate positive vs negative replies — a feedback loop competitors
  charge for.
- ★ **Bulk opener drafting** (S) — Inbox bulk action "Draft openers";
  runs LLM gen in parallel for selected leads. Converts the wedge from
  "one lead at a time" to "20 in one click" — daily workflow not demo.
- **Multi-source signal grounding** (M) — Opener uses ONE signal today.
  Pull 2-3 stacked signals (PH launch + recent blog + GitHub stars +
  hiring posts) for the 15-25% reply lift the trend scan documents.
- **A/B opener variants with auto-winner** (M) — Generate 2-3 variants,
  send rotating, Thompson-sample winners by reply rate.
- **AI reply drafting** (M) — When prospect replies positive, draft a
  contextual response in user's tone for one-click send.

### B. Trust & deliverability (the wedge gap)
- ★★ **Multi-domain send routing + per-domain health** (L) —
  TREND-AGENT TOP-2. Beyond mailbox rotation. Users register N sending
  domains; we route sends across them with a per-domain visual gauge
  (bounce rate, complaint proxy, daily volume cap). Don't build warmup
  ourselves — point users at Mailreach. The trend scan is explicit:
  "users who ship without multi-domain routing will burn their domains
  in 4-6 weeks and blame your tool." This is the feature that takes
  SmartBiz from demo to "tool I trust for serious volume."
- ★ **DNS health checker** (S) — SPF / DKIM / DMARC / MX lookup +
  pass/fail for sending domain. Now an enforcement line per Google +
  Microsoft 2025. Day-1 utility — most SDRs don't know if their setup
  is right.
- ★ **Suppression list + 1-click unsubscribe (RFC 8058)** (M) — Now
  mandatory per Google bulk-sender rules. One-click unsub link in every
  email, auto-add to suppression. Skipping this gets your sending IPs
  blocklisted, period.
- **Send-volume guardrails** (S) — Per-inbox daily cap (30-50 per trend
  scan); surface "47/100 today" indicator; auto-throttle.
- **Send-time optimization** (M) — Schedule sends per prospect timezone.
- **Bounce auto-handling via Resend webhook** (S) — Soft/hard bounce →
  auto-mark email invalid + pause sequence. Sub-2% bounce rate is now
  enforcement-line; auto-removal protects it.

### C. Intelligence & signals
- **Account-level rollup** (S) — Group leads by `company_domain`. View
  "Acme Corp · 4 leads · 2 replied · 1 hot" — different lens for ABM.
- **Job-change detection** (M) — Track champion email-domain changes;
  alert when they move companies (re-engage at new co).
- **Funding/news signal feed** (M) — Daily subscribe to "new $X funding
  for accounts in your ICP" via Crunchbase/HN scrapers.
- **Tech-stack change tracking** (L) — Re-run BuiltWith-style detection;
  alert on stack changes that match your sales motion.
- **Web visitor identification** (L) — Drop a snippet on user's site,
  identify visiting companies (Clearbit Reveal-style). Premium feature.

### D. Workflow productivity
- **Send-from-drawer** (S) — Compose first email inline in lead drawer
  with opener pre-filled, send via Resend. Kills the "Convert → leads
  page → drawer → start sequence → modal" loop.
- **Calendar booking link injection** (S) — Auto-include user's
  Cal.com/Calendly link when reply is detected as "interested".
- **Daily digest email** (M) — To the user, summarizing yesterday's
  replies + today's hot leads. Gets users back into the product.
- **Slack inline actions** (M) — Approve/Reject/Schedule from the Slack
  hot-lead alert DM (already firing the alert; add interactivity).

### E. Analytics / answers the user's "what worked?"
- **Sequence performance breakdown** (M) — Per-step + per-template reply
  rate. Tells the user "Step 2 of welcome_v1 gets 80% of replies."
- **Source ROI** (S) — Replies per scraper source. "Stop running PH,
  start running YC."
- **ICP retrospective** (M) — Cluster top-N hot leads, surface common
  attributes, suggest ICP edits. Closes the ICP feedback loop.

### F. Multi-tenancy / agency mode (Zerotoprod IS an agency)
- **Workspace switcher + real multi-tenancy** (L) — Already in P2.
  Agency-mode is the most aligned monetization vector for the user's
  position. One client = one tenant. Aggregate dashboard across clients.
- **Per-client ICP isolation** (S) — Each client has its own ICP rubric.
- **Agency-level reporting** (M) — Cross-tenant aggregation for owner.

### G. Onboarding
- **First-send wizard** (M) — ICP → 10 leads → first email queued in
  60 seconds. Single guided flow. Removes the "what do I do next?" gap
  the flow audit flagged.
- **Template marketplace** (M) — Pre-built sequences by industry (SaaS,
  agency, vertical SaaS, etc.).
- **Demo data toggle** (S) — One-click "fill with sample leads" so a new
  user can explore before any real data.

### H. Compliance / legal
- **GDPR consent tracking** (M) — Lawful-basis log per lead.
- **Data export / deletion** (S) — User-requested export.

### I. Monetization (when ready)
- **Stripe billing + plans** (L) — Free tier (50 leads), $29/mo
  (500 leads + 1 mailbox), $99/mo (unlimited + agency mode).
- **Usage-based metering** (M) — Per-LLM-call cost tracking, surface as
  "this month: 1.2k openers, $4 in LLM cost" so user understands cost.
- **Referral program** (S) — One-tier referral credit.

---

### Sprint-2 candidate bundle (revised after trend scan)

The trend-agent's verdict: **the three things that take SmartBiz from
demo to serious tool** are (in order) trigger-signal scoring,
multi-domain routing with health metrics, and reply intent +
branching. Everything else is decoration on top of those three.

A pragmatic 7-day sprint that mixes wedge-deepening + day-1 utility:

| Day | Feature | Bucket |
|---|---|---|
| 1   | ★ Bulk opener drafting | A — wedge, daily-workflow lift |
| 2   | ★ DNS health checker | B — trust, day-1 utility |
| 3-4 | ★★ Reply intent classification | A — trend-top-3, uses IMAP we have |
| 5-6 | ★★ Trigger-signal scoring layer (job postings + funding) | A — trend-top-1 |
| 7   | ★ Suppression list + RFC 8058 unsubscribe | B — Google enforcement line |

The trend-agent's #2 (multi-domain routing) is correctly its own sprint
— full table-stakes feature, ~10 days, the highest dollar-value lift
once shipped. Schedule it as Sprint-3 standalone.

Sprint-7 SHIPPED (confidence pass, this turn):

- ★ **Backend test suite for load-bearing logic** — DONE.
  117 tests passing across:
  - test_variant_picker (epsilon-greedy explore-then-exploit)
  - test_trigger_detector (regex + boost cap; surfaced + fixed
    a real bug in tech_stack_change matching past-tense verbs)
  - test_send_time (TLD offset table + window snap + weekend bump)
  - test_reply_intent (heuristic pre-filter for unsubscribe + OOO)
  - test_suppression_tokens (HMAC roundtrip + tamper rejection +
    secret-rotation invalidation + RFC 8058 headers)
  - test_scraper_helpers (_parse_funding round/amount, _normalize_domain
    cross-source matching, _reddit_intent_score, YC batch year filter)
  - test_imap_helpers (RFC 3834 Auto-Submitted parsing — guards the
    catastrophic "drops real replies" failure mode)
  - test_webhook_signatures (Tally HMAC, HubSpot v3 + replay window,
    Svix multi-signature handling for secret rotation)

- ★ **Run-failure Slack alert** — DONE. New
  `maybe_alert_slack_run_failed` in routers/settings.py reuses the
  Slack webhook config. Scheduler fires the alert at both failure
  paths (uncaught exception + soft-fail return). SDR sees automation
  breakage in Slack without watching the dashboard.

- ★ **Skeleton loaders** — DONE. New SBSkeleton primitive (row /
  card / list variants with pulse animation, fading-opacity stack).
  Replaced "▸ loading…" mono text on Accounts, Inbox, Scrapers,
  Templates, Channels, LeadDrawer.

- ★ **Empty states polish** — DONE. Accounts page now has a tailored
  empty state explaining where accounts come from + a "Go to Inbox"
  CTA, instead of the generic "no accounts" line.

Sprint-6 SHIPPED (scraper deepening pass, this turn):

Driven by a fresh trend scan (May-2026) of B2B scraper sources.
Trend agent's verdict: highest signal:reliability adds are job-board
APIs, SEC EDGAR S-1 feed, and Reddit intent monitoring. All three
are httpx-only — no headless / proxy needed.

Existing scraper enrichment
- Retry+backoff helper: 3 attempts (1s/3s/8s) with rotating UA strings.
  Detects Cloudflare interstitials and retries with a different UA.
  Every existing scraper now goes through it instead of raw httpx.get.
- Product Hunt: extracts maker name + tagline + published date,
  not just title. Tagline carries the highest-signal phrasing for
  the opener generator.
- TechCrunch: structured funding parser pulls `amount_raw` + `round`
  (pre-seed / seed / series-a..f). Skips opinion / event / live-cov
  TC posts via prefix filter. Score band: 75 (round + amount), 70
  (round only), 65 (amount only), 40 (general).
- GitHub Trending: signal-aware scoring — owner-type Organization +
  org-keyword heuristic + high-signal language list + real homepage
  domain (not github.io) all bump the score.
- YC directory: pulls founders array (name + title + twitter +
  linkedin), `is_hiring` flag, `tagline`. Score boosts for current-
  year batch, ICP-relevant industry, public LinkedIn presence.
- Apollo: titles / seniorities / headcount_ranges now read from
  `workspace_settings.apollo_icp` JSONB so each tenant can target
  their actual ICP without code changes. Defaults preserved.

NEW sources (trend-agent top picks)
- ★★ **Job boards (Greenhouse / Lever / Ashby)**: public unauth JSON,
  zero rate limits, hiring velocity = buying intent. Seeds from
  JOB_BOARD_TOKENS env (greenhouse:stripe,lever:figma,...). Scores
  by sales/eng role density. One row per company carrying open-role
  count + sample titles for opener generator context.
- ★★ **SEC EDGAR S-1**: free no-auth gov API. Pre-IPO companies =
  highest-budget buying segment. Last-60-days filter. Each row
  carries `cik`, filing date, EDGAR detail URL. Base score 80.
- ★★ **Reddit intent monitor**: r/SaaS / r/devops / r/sysadmin /
  r/startups. Keyword filter ("looking for X", "switched from Y",
  "alternatives to Z"). Per-post score 55-90 based on phrase count
  + pain-language bumps.

Cross-source dedup + score boost
- _insert_results now dedups by normalized root domain (45-day
  window) AND exact URL. When the same company appears in 2+
  sources, the existing row gets +5 score (cap 95) and a
  `cross_source_signals` array appended to its raw_data. The
  Inbox / Drawer can render "this lead also appears in YC + GitHub"
  to give the SDR a confidence cue. Caps duplicate inbox noise.

Sprint-5 SHIPPED (continuing megasprint, this turn):

- ★ **Daily digest auto-cron** — DONE. Hooked into the scheduler tick;
  fires once per UTC day at DIGEST_HOUR_UTC (default 9). Idempotent on
  (date, tenant) so multiple ticks in the trigger hour don't double-send.
  DIGEST_ENABLED=false to disable.

- ★ **Calendar booking link injection** — DONE. workspace_settings
  gains calendar_link (Cal.com / Calendly / HubSpot Meetings / SavvyCal
  validated). AI reply drafter auto-injects a soft CTA when the link is
  set; LLM gets it as context too so it can weave the link naturally.

- ★ **ICP retrospective** — DONE. GET /api/leads/icp-retrospective
  clusters top hot/replied leads by source, title, trigger, domain TLD.
  Surfaces 2-4 actionable suggestions ("60% from `scraper:yc` — prioritize
  it"). Card on /admin/reports above the weekly list. Closes the ICP
  feedback loop.

- ★ **GDPR data export** — DONE. GET /api/leads/{id}/data-export streams
  the lead row + activity + score history + scraper origin in one JSON
  blob. Compliance baseline.

- ★ **Demo data toggle** — DONE. POST /api/workspace/settings/demo-data/
  load drops 12 sample leads (varied score / source / trigger).
  DELETE wipes them in one statement (source='demo' filter). DemoDataCard
  on Settings.

- ★ **Per-request structured log middleware** — DONE. Logs method/path/
  status/duration via smartbiz.access logger. 4xx/5xx promoted to
  WARNING / ERROR levels. Health + static + unsubscribe paths skipped to
  keep the stream readable.

- ★ **Drag-and-drop kanban race fix** — DONE. Per-lead monotonic seq
  number; stale callbacks can't overwrite fresh state in either success
  or rollback paths.

- ★ **Keyboard shortcuts cheatsheet** — DONE. Global ? hotkey opens a
  modal listing every shortcut grouped by surface. Plus G+I/L/A/R as a
  vim-style nav shortcut. Ignored while typing in inputs.

Sprint-4 SHIPPED (continuing megasprint, this turn):

- ★★ **Send-time optimization** — DONE. New `automations/send_time.py`
  with TLD→offset table for ~40 countries; `next_send_window()` snaps
  to the prospect's next 9-11 AM local, bumps weekends to Monday.
  Workspace toggle `send_time_optimization`; /runs uses it on insert.

- ★★ **Multi-source signal grounding** — DONE. Opener prompt now asks
  for 2-3 STACKED signals (PH launch + funding + tech, etc.) per the
  trend scan's 15-25% lift target. Pulls from notes, tagline,
  highlights, summary, funding stage, tech stack, detected triggers,
  scraper source. Higher temperature + style nudges produce divergent
  variants.

- ★★ **A/B opener variants + winner tracking** — DONE.
  `opening_line_variants` JSONB on Lead. Generate N variants endpoint
  with five style nudges (curious / observational / pragmatic /
  founder-to-founder / hypothesis). Scheduler picks via epsilon-greedy
  (round-robin until 3+ sends each, then highest reply rate). IMAP +
  manual reply paths bump replied_count for the active variant.
  Drawer surfaces variant list with sent/replied/rate + "use this"
  promotion buttons.

- ★ **Daily digest email** — DONE. `automations/digest.py` aggregates
  24h of replies + new hot leads + sequence health + suppressions
  into one HTML email per active admin. POST
  /api/workspace/settings/digest/send-now manual trigger; "Send daily
  digest" button on Home. Returns 'no activity' instead of empty
  digest. Day-2 retention killer per the trend scan.

- ★ **URL-persisted filters on /admin/leads** — DONE. useSearchParams
  mirrors filter state to ?status=hot&intent=positive style query
  params. Survives reload, shareable, browser-back works.

- ★ **First-send wizard (60-second onboarding)** — DONE. Single
  4-step overlay: confirm ICP → pick top hot leads (multi-select) →
  bulk-draft openers → pick template → fire sequences. Closes the
  multi-page friction the flow audit flagged. Launched from "First
  send · 60s" button on Home.

- ★ **Structured logging + Sentry hook** — DONE. main.py configures
  root logger with format/level/datefmt + quiets noisy libs unless
  LOG_LEVEL=DEBUG. Sentry init when SENTRY_DSN env set (lazy import
  so missing dep doesn't crash). Per-component filtering via logger
  names already in place across modules.

Sprint-3 SHIPPED (continuing into a single megasprint):

- ★★ **Suppression list + RFC 8058 1-click unsubscribe** — DONE.
  workspace_suppressions table + unsubscribed_at on leads (migration
  008). HMAC-signed tokens via `automations/suppression.py` (no DB
  roundtrip to verify). Public `/api/u/{token}` endpoint serving GET
  (HTML confirmation page) and POST (RFC 8058 one-click). Scheduler
  injects List-Unsubscribe + List-Unsubscribe-Post headers and
  appends a footer link in every rendered email. send_day0 hard-blocks
  with `skipped_suppressed` outcome when recipient is on the list.
  SuppressionsCard on Settings.

- ★★ **Bounce + complaint auto-handling via Resend webhook** — DONE.
  `/api/webhooks/resend` with Svix signature verification (handles
  whsec_-prefixed Resend secrets) + 5-min replay window. Hard bounce
  → `bounce_hard` suppression; soft bounce → `bounce_soft`; complaint
  → `complained`. Returns 501 honestly when RESEND_WEBHOOK_SECRET is
  unset.

- ★★ **Send-from-drawer (compose first email inline)** — DONE.
  POST /api/leads/{id}/send-now routes through the same multi-mailbox
  / Resend fallback as the scheduler with a pre-flight suppression
  gate. New drawer Compose modal: subject + HTML body fields pre-
  filled with template + opener; "Send" button hits the endpoint
  directly. Kills the convert → leads list → drawer → start-sequence
  → modal chain.

- ★★ **AI reply drafting** — DONE.
  POST /api/leads/{id}/draft-reply pulls the most recent reply
  snippet, prompts Gemini to draft a contextual response in JSON
  shape, returns {subject, body_html}. Drawer surfaces a "Draft reply"
  button only when last_reply_intent='positive'. Stub fallback when
  no LLM key so the user always lands on a usable starting point.

- ★ **Inbox filter by reply intent** — DONE.
  /api/leads now accepts `?intent=` query. New chip row above the
  kanban: all / positive / neutral / negative / wrong-person / unsub.
  One-click filter to "show me only positive replies" — surfaces the
  intent classification feature so it actually steers the SDR's day.

- ★ **Account-level rollup** — DONE.
  GET /api/leads/accounts groups by company_domain (or company_name
  fallback) with hot_count, replied_count, avg_score, lead_count,
  last_activity, and aggregated triggers. New /admin/accounts page
  with sort tabs (most hot / most replied / recent) + click-through
  to the leads list filtered by company. Sidebar gains "Accounts"
  next to "Leads".

- ★ **Source ROI + sequence performance analytics** — DONE.
  GET /api/reports/source-roi and /api/reports/sequence-performance.
  Two cards on /admin/reports above the weekly-report list:
  bar-chart per source with replied/leads/rate, and per-template
  reply-rate display with sends + skipped_replied counts. Live data,
  no manual report generation needed — answers "which scrapers
  convert?" and "which templates work?" the moment a reply lands.

Sprint-2 SHIPPED (commits 70aeb26 + this turn):
- ★ Bulk opener drafting — DONE
- ★ DNS health checker — DONE
- ★★ Reply intent classification — DONE (LLM-classified into positive,
  negative, neutral, wrong_person, unsubscribe, auto_reply; chip on
  lead card + drawer; heuristic pre-filter for unsubscribe + OOO so we
  don't pay for LLM on obvious cases; falls back to "neutral" silently
  when no LLM key)
- ★★ Trigger-signal scoring layer (lite) — DONE (regex + field-presence
  detector for hiring/funding/launch/tech_stack_change; +5/each score
  boost capped at +15; wired into bulk-convert; new
  /api/leads/{id}/detect-triggers for re-scan; trigger badges on lead
  card + drawer)
- ★★ Multi-mailbox SMTP routing MVP — DONE (workspace_mailboxes table,
  Fernet-encrypted creds reusing IMAP key, Gmail/Outlook/Fastmail
  presets, Test-then-Save flow, scheduler routes through mailboxes
  with daily caps + lazy reset, falls back to Resend when none
  configured. MailboxesCard with per-mailbox volume gauges + cap
  editing inline. No warmup integration yet — point users at Mailreach
  on top.)

# M3 Automation Engine — Research & Decisions

**Date:** 2026-04-19
**Status:** Research for team review.
**Depends on:** foundation.md, m2-sales-intel.md (lead source)

## Summary

M3 is the workflow framework for lead nurture: trigger → action → wait → check → branch. The stack is locked: **Inngest (Python SDK)** drives every long-running workflow and scheduled job in SmartBiz OS, **FastAPI** hosts the HTTP handler Inngest calls, and **Postgres projection tables** (`automation_runs`, `automation_events`) feed the per-lead timeline UI that makes the product feel alive on seeded data. V0 ships one real channel (email via **Resend**, swappable through a `ChannelAdapter` registry), three pre-seeded nurture templates, and stub adapters for WhatsApp / LinkedIn / SMS so the "pluggable framework" pitch is demonstrably real — not just slideware. The demo footprint comfortably fits Inngest's 50k/mo free executions and Resend's 3k/mo free tier. The single honest caveat we carry into every demo: Resend (and every mainstream ESP) forbids pure cold outbound at scale; for paying customers we route through a specialist adapter (Smartlead / Instantly / customer's own infra) which the registry already supports.

## Inngest function shape

A nurture workflow is one `@inngest_client.create_function` decorated Python coroutine. In prose: define the client once at module import, decorate a function with `fn_id="nurture.cold_outbound_v1"` and `trigger=inngest.TriggerEvent(event="lead.nurture.start")`, accept a single `ctx: inngest.Context` argument (async) or `ContextSync` (sync), and use `ctx.step.*` primitives to build the durable sequence. Register it with `inngest.fast_api.serve(app, inngest_client, [nurture_fn])`, and kick a run from anywhere by emitting `await inngest_client.send(inngest.Event(name="lead.nurture.start", data={"lead_id": ..., "template_id": ...}))`.

The V0 cold-outbound flow reads (in prose) like this:

1. `ctx.step.run("load_lead", _load_lead, lead_id)` — pulls the lead snapshot (name, email, company, segment) from Postgres. One checkpoint, retried on DB blips.
2. `ctx.step.run("render_email_day0", _render, lead, "cold_v1_day0")` — expands the pre-written template with placeholders. Deterministic given the memoized lead.
3. `ctx.step.run("send_day0", channels.send, "email", lead, rendered)` — the ChannelAdapter call. Returns a `SendResult` with provider message id.
4. `ctx.step.run("log_event_sent", _log_event, run_id, "email_sent", payload)` — append to `automation_events`.
5. `ctx.step.sleep("wait_3_days", datetime.timedelta(days=3))` — zero cost while sleeping; doesn't consume compute.
6. `opened = ctx.step.wait_for_event("wait_open", event="email.opened", if_exp=f'async.data.message_id == "{message_id}"', timeout=datetime.timedelta(days=3))` — resolves with the event or `None` on timeout.
7. Branch on `opened is None`. If None → render + send breakup, log `branch_no_response`. If truthy → render + send follow-up, log `branch_opened`, then another `wait_for_event` for a reply with a 4-day timeout, then branch again.

**Step determinism — what must go inside `step.run` vs outside.** Inngest re-invokes the function from the top on every step boundary; previous step results are replayed from memoized state (keyed by step ID). Anything non-deterministic — DB calls, HTTP, `random`, `uuid.uuid4()`, `datetime.now()`, file I/O — **must** be inside `step.run` so the return value is captured once and replayed. Code outside `step.run` must be pure: lookups into `ctx.event.data`, branch logic on previously-memoized values, and local variable assignment. A common foot-gun: generating `message_id = str(uuid.uuid4())` at function scope will produce a different ID on replay and break the `wait_for_event` `if_exp` filter. Fix: compute it inside `step.run("mint_message_id", lambda: str(uuid.uuid4()))`. Same rule for timestamps that we later pass to `step.sleep_until` or store in the timeline.

**Timeouts and branching.** Python `wait_for_event` takes a `datetime.timedelta` and returns the matched event dict or `None`. We always guard with `if event is None:` and route to the breakup branch — never assume truthy. The `if_exp` CEL expression filters which inbound events count (scope it by `message_id` or `lead_id` to prevent cross-run bleed).

**Inngest billing note.** Critically, Inngest bills per **function execution**, not per step. A 7-step nurture that spans 10 days counts as a single run (retries add runs). This changes the math from the prompt: we do not need to obsess over step count for cost — we need to watch **retry count** and **run concurrency**. Cost math is redone in the "Cost at demo scale" section.

## Channel adapter registry

The registry is a thin module-level singleton loaded at FastAPI startup:

- `ChannelAdapter` is a `Protocol` (or abstract dataclass) with one primary method: `send(lead: Lead, template: RenderedTemplate, context: SendContext) -> SendResult`. `SendResult` is a dataclass with `provider`, `provider_message_id`, `status` (`sent | queued | failed`), `error`, and `raw` (JSONB passthrough for the timeline payload).
- A second method `receive_webhook(payload: dict) -> list[InboundEvent]` lets each adapter translate its provider's webhook schema into our canonical event shape (`email.opened`, `email.clicked`, `email.replied`, `email.bounced`, `whatsapp.delivered`, etc.) before we hand those to `inngest_client.send`.
- `channels.register("email", EmailAdapter(provider=ResendProvider()))` in `startup`. `channels.send("email", ...)` looks up the adapter and dispatches. Unknown channel raises a loud error surfaced in the timeline as `channel_not_registered`.

**V0 adapters.** `EmailAdapter` wrapping `ResendProvider` is live. `WhatsAppAdapter`, `LinkedInAdapter`, `SMSAdapter` are registered as **honest stubs**: `send` writes `would_send` to the timeline event payload and returns `SendResult(status="stubbed", provider="stub")`. The UI badge renders these runs with a "stub channel" tag so nobody is misled during a demo.

**Pluggable providers we've scoped (not building V0).** WhatsApp: direct WhatsApp Business Cloud API (Meta) is cheapest and most capable; Twilio WhatsApp is simplest DX; WATI is highest-level but Indian-region-biased. LinkedIn: no official API for cold messaging — options are PhantomBuster, Expandi, or HeyReach (automation tools that drive a real logged-in session). SMS: Twilio is default; MessageBird if customer is EU. We document these in the pitch; we do not implement.

**Templates.** Template files live under `templates/<channel>/<template_id>/` with `meta.yaml` (id, channel, version, name, description, segment, step_order) and `body.md` (mustache placeholders: `{{lead.first_name}}`, `{{lead.company}}`, `{{sender.name}}`). Render pipeline: markdown → HTML (for email) via `markdown-it-py`, placeholders filled from a typed `TemplateContext` dataclass. Versioning is baked into the path (`cold_v1_day0`, `cold_v2_day0`); we never mutate a shipped template, we ship a new version. The preview endpoint (`/api/templates/:id/preview?lead_id=...`) re-runs the render pipeline and returns the HTML + subject for in-UI inspection.

## Email provider pick

**Recommendation: Resend for V0.** Reasoning:

- **DX and Python SDK quality.** Resend's Python SDK is modern, typed, minimal ceremony (`resend.Emails.send({...})`). Postmark's Python story is the community-maintained `postmarker` library — fine, but Resend feels more native in 2026.
- **Webhooks.** Resend fires `email.delivered`, `email.opened`, `email.clicked`, `email.bounced`, `email.complained` — exactly what we need to emit into Inngest for the `wait_for_event` gates. Signature verification uses Svix, which has a Python SDK.
- **Free tier.** 3k/mo, 100/day, one verified domain — covers every demo scenario.
- **Click/open toggles via API.** We can turn tracking on/off per send, useful for the occasional demo that needs a clean compliance story.

**Why not the others (for V0 specifically).**

- **Postmark.** Best-in-class transactional deliverability (98.7% independent inbox placement, enforced message-stream separation). But the Python SDK is community-maintained and the ToS is stricter on any promotional send. Good "V2 transactional" choice, not V0.
- **Amazon SES.** Cheapest ($0.10 / 1k), but raw infrastructure — we'd be building the webhook plumbing, bounce handling, and templating ourselves. Demo velocity loses.
- **SendGrid.** Deprecated-feeling in 2026, explicit ToS ban on scraped-list cold outbound, enterprise sales motion. Skip.
- **Mailgun.** Fine, but no DX advantage over Resend and weaker brand in modern startup stacks.

**The honest ToS caveat — surfaced in every pitch and in the README.** Resend routes through Amazon SES shared IP pools; like every mainstream transactional ESP, their ToS requires recipient opt-in / existing relationship. True scraped-list cold outbound belongs on Smartlead or Instantly (purpose-built, with warm-up + account rotation). The `ChannelAdapter` interface is deliberately provider-agnostic: a `SmartleadAdapter` is a future drop-in replacement for `ResendProvider` with zero workflow changes. We pitch this as feature, not bug: "the framework is email-provider-agnostic; your team plugs in whatever your compliance / volume needs."

## Timeline schema

Two tables, both SQLAlchemy `MappedAsDataclass`:

```
automation_runs
  id                UUID pk
  lead_id           UUID fk → leads.id
  template_id       TEXT              -- "cold_v1"
  inngest_run_id    TEXT unique       -- correlation key for passthrough diagnostics
  status            TEXT              -- running | completed | failed | cancelled | paused
  current_step      TEXT              -- last step_name we logged
  started_at        TIMESTAMPTZ
  completed_at      TIMESTAMPTZ nullable
  created_by        TEXT              -- "lara" | "user:<uid>" | "system"

automation_events
  id                UUID pk
  run_id            UUID fk → automation_runs.id
  step_name         TEXT              -- "email_sent" | "wait_completed" | ...
  channel           TEXT nullable     -- "email" | "whatsapp" | null for control events
  outcome           TEXT              -- "ok" | "failed" | "timed_out" | "skipped"
  occurred_at       TIMESTAMPTZ
  payload           JSONB             -- message_id, subject, provider raw, error, etc.
```

**Why separate from Inngest's own state.** Inngest keeps its own durable state, but reading it requires an HTTP roundtrip to Inngest's API and their schema is not shaped for UI rendering. The projection table approach lets the timeline UI serve a single indexed query (`SELECT * FROM automation_events WHERE run_id = $1 ORDER BY occurred_at`) and keeps the dashboard snappy. The projection is an append-only log; we never update events, we insert new ones for corrections.

**Canonical event vocabulary.** `run_started`, `email_sent`, `email_queued`, `email_delivered`, `email_opened`, `email_clicked`, `email_replied`, `email_bounced`, `email_complained`, `wait_started`, `wait_completed`, `wait_timed_out`, `branch_taken` (payload: `{branch: "no_response" | "opened" | "replied"}`), `step_retried`, `step_failed`, `run_completed`, `run_cancelled`, `run_paused`. New channels extend this with `whatsapp_sent`, `linkedin_connection_sent`, etc.

**Writer discipline.** Every `step.run` in the nurture function ends with a `step.run("log_<x>", _log_event, ...)` call. That log step is itself idempotent (upsert on `(run_id, step_name, occurred_at)` or on a dedicated `event_key`) so a replay doesn't duplicate rows.

## State transitions & failure

**Retry policy.** Default Inngest retry is 4 attempts with exponential backoff. We set `retries=3` at the function level for nurture (sending spam-triggering retry volume is worse than failing loud). Per-step failures that exhaust retries mark the run `failed` in Inngest's UI and stop future steps. Our `on_failure` handler (registered on the function) writes a `run_failed` event to the timeline with the exception detail — the UI shows a red node rather than silently swallowing.

**Bounced or provider-down email.** The `EmailAdapter.send` raises on non-2xx from Resend; `step.run` retries 3×. If all retries fail, the timeline shows `email_sent` with `outcome="failed"` + error string, the run marks `failed`, and a subsequent `wait_for_event` is never reached (it's past the failed step). For hard bounces that succeed at send but fail asynchronously, Resend's `email.bounced` webhook arrives later and we log it as a separate event — the run may have already moved on, which is fine for the timeline (we just append the bounce as a standalone record linked via `provider_message_id`).

**Crash mid-step.** Inngest's durability model: on replay the function re-enters from the top, each `step.run` with a memoized result short-circuits, and execution resumes at the first un-memoized step. The `_send_email` call therefore runs **exactly once** on the happy path even through pod restarts. The idempotency requirement is on the inner function — if the step raised after the provider already accepted the send, a retry would duplicate. Mitigation: attach an idempotency key to the Resend request (`idempotency_key=f"{run_id}:{step_name}"`) so provider-side dedup catches it.

**Late opens after timeout branch fired.** Concrete case: `wait_for_event("wait_open", timeout=3d)` times out, we send breakup, lead opens the email on day 5. Inngest's `wait_for_event` has already resolved `None` and moved on — a later `email.opened` event does **not** rewind the function. But the event still reaches us via webhook and we log it in `automation_events` as `email_opened` anyway. The timeline renders honestly: "breakup sent day 3 · lead opened day 5 (after breakup)." No workflow rollback, no silent discarding — the UI tells the true story. This is the "idempotent opens" guarantee: late signals are recorded, never altering past branches.

**Cancellation and pause.** User hits "Cancel run" in UI → backend calls Inngest's `DELETE /v1/runs/{id}` (or `POST /cancellations` for bulk) → we write `run_cancelled` to the timeline. Pause works at the function level (Inngest pauses all runs of that function); we expose per-run pause by cancelling and marking for resume-from-state, acknowledging this is a V1+ feature.

## Lara MCP surface

A FastMCP server exposes `automation.*` tools to Lara. All tools read / write through the FastAPI backend rather than direct DB or Inngest API access, so authorization and audit logs are consistent with user actions.

- `automation.list_templates()` → list of `{id, name, channel, steps, description, version}` for pre-seeded nurtures.
- `automation.list_running(lead_id?, template_id?)` → open runs, optional filters. Backs questions like "what's in flight for Acme?"
- `automation.get_timeline(run_id)` → ordered `automation_events` with enriched channel/outcome strings. This is what Lara reads aloud when the user asks "what happened with this lead?"
- `automation.start(lead_id, template_id)` → emits `lead.nurture.start` event, returns `run_id` once the projection row is created.
- `automation.pause(run_id)` → calls Inngest pause API, writes `run_paused` event.
- `automation.cancel(run_id)` → calls Inngest cancel API, writes `run_cancelled` event.
- `automation.preview_template(template_id, lead_id)` → rendered HTML / subject, no send.

**Passthrough to Inngest's official MCP.** Inngest ships a dev-server MCP today (`send_event`, `list_functions`, `invoke_function`, `get_run_status`, `poll_run_status`, `grep_docs`, `read_doc`, `list_docs`). For deep diagnostics ("why did step X retry three times?"), we proxy `get_run_status` through a single `automation.inngest_diagnostics(run_id, tool, args)` passthrough — we store the Inngest `run_id` on our `automation_runs` row precisely to enable this correlation. **Caveat**: the published MCP is framed as dev-server, not production — we'll either self-host the MCP against our prod Inngest account or fall back to direct REST calls wrapped by our tool. Flagging as an open question below.

## V0 nurture templates

Three templates ship, validating the prompt's proposal:

1. **`cold_outbound_v1`** (rich, 5 steps): Day 0 intro → wait 3d → open-check → Day 3 follow-up or breakup → wait 4d → final breakup. Demonstrates full branching.
2. **`welcome_v1`** (simple, 2 steps): Day 0 welcome → wait 1d → Day 1 onboarding tip. Linear, no branching. Best demo starter — runs complete in minutes with time-scaled config.
3. **`reengagement_v1`** (simple, 3 steps): Day 0 "we miss you" → wait 7d → open-check → Day 7 incentive or silent close. One branch.

**Format: Python dataclass, not YAML.** Compile-time safety, IDE autocomplete, and identical storage shape across environments beat YAML's editability. `NurtureTemplate(id, name, channel, version, steps: list[Step])` where `Step` is a tagged union (`SendStep(template_id, channel)`, `WaitStep(duration)`, `WaitForEventStep(event, timeout, if_expr)`, `BranchStep(on_event, then, else_)`). The Inngest function interprets this dataclass to drive `step.run` / `step.sleep` / `step.wait_for_event` calls — one engine, many templates, template authors never write Inngest code.

**Demo time-compression.** A dev-only flag `AUTOMATION_TIME_SCALE=0.001` divides every `timedelta` in every step. A 3-day wait becomes 4 minutes in a demo. Production ignores the flag.

## Pluggable channels roadmap

The honest V0 story, in three beats we can defend:

1. **What's live.** Email via Resend, fully wired end-to-end including open/click webhook → Inngest event → `wait_for_event` resolution.
2. **What's framework-real.** The `ChannelAdapter` registry is the real abstraction. WhatsApp, LinkedIn, SMS adapters are registered at boot with working `send` methods that log `{"would_send": true, "channel": "whatsapp", "body": "..."}` into `automation_events`. The timeline renders a stubbed send as a visibly-badged node ("stubbed — WhatsApp live in V1"). No lie, no empty box.
3. **What's pitched.** "If you have bandwidth or budget, we plug in the live adapter for your channel mix — Twilio for SMS, Meta Cloud API for WhatsApp, PhantomBuster for LinkedIn. The workflow, templates, timeline, and Lara surface don't change — the adapter does."

Demo script: run one cold_outbound on email (real sends), one on whatsapp (stubbed, shows timeline + would-send payload). The contrast is the pitch.

## Cost at demo scale

**Inngest.** 50k free executions/month. A nurture run = 1 execution regardless of step count (retries add). With 3 templates × 50 demo leads × realistic retry fudge of 1.3 = ~200 runs/month for our own demos. Comfortably inside free tier by two orders of magnitude. Even at "showcase" volume (5k leads in a customer pilot) we're at ~6.5k runs — still free.

**Resend.** Free tier: 3k emails/month, 100/day, one domain. Each cold_outbound_v1 sends up to 3 emails per lead (intro, follow-up or breakup, final breakup). 50 demo leads × 3 = 150 sends. Welcome/reengagement cheaper. Total < 500/month. Well under cap.

**Postgres.** Each run produces ~10-20 events. 200 runs × 20 events = 4k rows/month. Negligible.

**Webhook ingestion.** Resend webhooks fire ~5 events per send (delivered, opened, clicked, etc.). 500 sends × 5 = 2.5k inbound events/month. FastAPI handler is essentially free.

V0 demo runs on free tiers across the board. First paid tier hits only when a customer pilot scales past ~20k sends/month — by which point we're charging them.

## Open questions

- **Inngest production MCP.** The published MCP is framed as dev-server. Confirm whether we can point it at our prod Inngest account or whether we build a thin proxy. Ticket for spike in week 2.
- **Reply detection for email.** Resend does not detect replies natively; we need an inbound email handler (Resend has inbound domains) or an IMAP poller. Deciding between (a) using the customer's IMAP for replies vs (b) routing replies to our inbound domain complicates the cold_outbound branch. V0 proposal: treat "clicked" as the positive signal instead of "replied" — simpler, and we avoid reply-parsing hell. Validate with team.
- **WhatsApp Business Cloud API onboarding.** Meta verification takes 1-3 weeks. If any customer wants live WhatsApp at launch, start the process in parallel.
- **Template editing in-app.** V0 ships code-as-template (Python dataclass). Do we need a template editor UI? Probably V1. Confirm with design.
- **Timeline replay / "what-if".** Do we show a dry-run preview of the whole flow for a lead before starting it? Nice-to-have, not V0.

## Gotchas

- **UUIDs and timestamps outside `step.run`.** Most common Inngest bug in Python. Any `uuid4()` or `datetime.now()` outside a step breaks replay. Lint rule: grep the nurture module for `uuid4\|datetime\.now\|random\.` outside `def _` helpers.
- **`wait_for_event` CEL filter scope.** `if_exp` must key on `message_id` or similar unique id, otherwise any open anywhere in the system could resolve the wait. We mint the message_id inside `step.run` and pass it into `if_exp` as a literal.
- **Inngest retry counts count as billable executions.** Permanent errors are free (they fail fast), transient errors are costly. Our `send_email` step must fail fast on 4xx (no retry) and retry only on 5xx/network — `retries=3` globally is too blunt. We configure per-step using try/catch + `inngest.NonRetriableError`.
- **Late webhook vs branch idempotency.** See state transitions — we record the late `email_opened` even if the flow already moved to breakup. Timeline must render with time-ordered clarity, not "opened" overriding "breakup sent."
- **Cold outbound ToS.** Every ESP bans it at volume. In pitch and README, name this out loud: "Resend is our default dev adapter. For volume cold outbound, you plug in Smartlead / Instantly / your own infra — our adapter layer is the whole point." If we hide this, we'll eat an account ban mid-demo.
- **Demo time-compression hazard.** The `TIME_SCALE` env flag must be explicitly off in any shared environment. A 0.001 scale applied to a real customer campaign sends all the emails at once. Guard with an assert on `is_production`.
- **Idempotency on `channels.send`.** Even with `step.run` memoization, the adapter's inner provider call should use a provider-level idempotency key (`run_id:step_name`) so a mid-step crash that occurred after the provider accepted the send won't double-send when Inngest retries.

## Sources

- [Inngest Python SDK — GitHub](https://github.com/inngest/inngest-py)
- [Inngest Python Quick Start](https://www.inngest.com/docs/getting-started/python-quick-start)
- [Inngest Python SDK reference](https://www.inngest.com/docs/reference/python)
- [Inngest — Sleeps](https://www.inngest.com/docs/features/inngest-functions/steps-workflows/sleeps)
- [Inngest — Wait for an Event](https://www.inngest.com/docs/features/inngest-functions/steps-workflows/wait-for-event)
- [Inngest — step.waitForEvent reference](https://www.inngest.com/docs/reference/functions/step-wait-for-event)
- [Inngest — Multi-Step Functions](https://www.inngest.com/docs/guides/multi-step-functions)
- [Inngest — Errors & Retries](https://www.inngest.com/docs/guides/error-handling)
- [Inngest — Cancellation](https://www.inngest.com/docs/features/inngest-functions/cancellation)
- [Inngest — Bulk Cancellation](https://www.inngest.com/docs/guides/cancel-running-functions)
- [Inngest — Function Pausing](https://www.inngest.com/docs/guides/pause-functions)
- [Inngest — Usage Limits](https://www.inngest.com/docs/usage-limits/inngest)
- [Inngest Pricing](https://www.inngest.com/pricing)
- [Inngest MCP](https://www.inngest.com/docs/ai-dev-tools/mcp)
- [Inngest Dev Server MCP announcement](https://www.inngest.com/changelog/2025-10-27-dev-server-mcp)
- [Resend — Pricing](https://resend.com/pricing)
- [Resend — Account quotas and limits](https://resend.com/docs/knowledge-base/account-quotas-and-limits)
- [Resend — New Free Tier](https://resend.com/blog/new-free-tier)
- [Resend — Update Click/Open Tracking via API](https://resend.com/changelog/update-click-open-tracking-via-api)
- [Postmark — Compare: Resend alternative](https://postmarkapp.com/compare/resend-alternative)
- [Postmark — Open tracking webhook](https://postmarkapp.com/developer/webhooks/open-tracking-webhook)
- [Postmark — Click webhook](https://postmarkapp.com/developer/webhooks/click-webhook)
- [Postmark — Can I send bulk emails?](https://postmarkapp.com/support/article/can-i-send-bulk-emails)
- [Postmark — Terms of Service](https://postmarkapp.com/terms-of-service)
- [Email API Pricing Comparison (April 2026)](https://www.buildmvpfast.com/api-costs/email)
- [Resend vs Postmark: Modern DX vs Proven Reliability (2026)](https://xmit.sh/versus/resend-vs-postmark)
- [Top Email Sending APIs in 2026](https://instantly.ai/blog/top-email-sending-apis-in-2026-complete-comparison-guide/)
- [Smartlead vs Instantly 2026](https://formanorden.com/blog/smartlead-vs-instantly/)

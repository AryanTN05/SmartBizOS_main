-- Migration 006 — reply intent + trigger signals.
-- Adds two columns to leads for the trend-agent's top-3 features:
--   1. last_reply_intent  — LLM-classified reply category (positive,
--      negative, neutral, wrong_person, unsubscribe, auto_reply). Surfaced
--      as a chip on the lead card and as an Inbox filter.
--   2. triggers           — JSON list of detected buying signals (hiring,
--      funding, etc). Surfaced as badges and adds a score boost.
-- Both nullable so historical leads stay valid; the application code
-- treats absence as "no signal yet" and never throws.

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS last_reply_intent TEXT,
  ADD COLUMN IF NOT EXISTS triggers JSONB;

CREATE INDEX IF NOT EXISTS idx_leads_reply_intent
  ON leads(last_reply_intent)
  WHERE last_reply_intent IS NOT NULL;

-- A/B opener variants (added in same conceptual feature batch). Each
-- variant is {text, sent_count, replied_count, generated_at_unix}.
-- The chosen variant lives in opening_line; opening_line_variants[]
-- is the candidate pool used for rotation + winner-tracking.
ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS opening_line_variants JSONB;

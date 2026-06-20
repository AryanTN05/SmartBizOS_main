-- Migration 008 — suppression list (1-click unsubscribe + bounce protection).
-- Google + Microsoft 2024-2025 bulk-sender rules require working
-- unsubscribe + sub-0.3% complaint + sub-2% bounce. This table is the
-- compliance backbone: any (tenant_id, email) pair listed here is
-- never sent to again, period. The scheduler hard-blocks the send_day0
-- step before render and the run completes early with "skipped_suppressed".
--
-- Sources (`reason` column):
--   manual          — user added via UI
--   user_unsub      — recipient hit the 1-click unsubscribe link
--   bounce_hard     — Resend webhook reported a permanent bounce
--   bounce_soft     — soft-bounced 3+ times in the last 30d
--   complained      — Resend webhook reported a spam complaint
--
-- Idempotent on (tenant_id, email). Adding a duplicate is a no-op.

CREATE TABLE IF NOT EXISTS workspace_suppressions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL,
  email       TEXT NOT NULL,
  reason      TEXT NOT NULL,
  notes       TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (tenant_id, email)
);

CREATE INDEX IF NOT EXISTS idx_suppressions_tenant_email
  ON workspace_suppressions (tenant_id, email);

-- Public unsubscribe tokens — opaque, single-use-ish per (lead, list_token).
-- We don't expire them aggressively because some recipients click weeks
-- after delivery. Token = HMAC(unsubscribe_secret, lead_id || tenant_id).
ALTER TABLE leads ADD COLUMN IF NOT EXISTS unsubscribed_at TIMESTAMPTZ;

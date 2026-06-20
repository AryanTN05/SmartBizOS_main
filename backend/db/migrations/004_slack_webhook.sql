-- Migration 004 — workspace-scoped Slack webhook for hot-lead notifications.
-- Idempotent. Run via:
--   .venv/bin/python -m scripts.apply_migration db/migrations/004_slack_webhook.sql
--
-- When a scraper (or enrichment pass) produces a lead with score >= the
-- alert threshold, we POST a compact summary to this webhook so founders
-- see new high-fit leads in Slack the moment they land. NULL = no alerts.

ALTER TABLE workspace_settings
  ADD COLUMN IF NOT EXISTS slack_webhook_url TEXT;

ALTER TABLE workspace_settings
  ADD COLUMN IF NOT EXISTS slack_alert_min_score INTEGER NOT NULL DEFAULT 80;

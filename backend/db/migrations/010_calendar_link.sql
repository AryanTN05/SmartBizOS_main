-- Migration 010 — workspace calendar booking link + Apollo ICP override.
-- calendar_link: single URL the email renderer + AI reply drafter inject
-- as a soft CTA. Empty/NULL = no insertion.
-- apollo_icp: per-workspace override for the Apollo scraper's filter
-- (titles / seniorities / headcount_ranges). NULL = use defaults.

ALTER TABLE workspace_settings
  ADD COLUMN IF NOT EXISTS calendar_link TEXT,
  ADD COLUMN IF NOT EXISTS apollo_icp JSONB;

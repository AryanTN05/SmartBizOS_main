-- Migration 003 — per-lead AI-generated opening line.
-- Idempotent. Run via:
--   .venv/bin/python -m scripts.apply_migration db/migrations/003_lead_opening_line.sql
--
-- The opening line is one personalized sentence grounded in the lead's
-- source signal (Product Hunt launch, YC batch, HN post, GitHub trending
-- repo). Generated on demand by the LLM and stored here so the user can
-- edit + reuse it across sequence steps via the {{opening_line}} variable.
-- NULL means "not generated yet" — the UI shows a "Generate" button.

ALTER TABLE leads ADD COLUMN IF NOT EXISTS opening_line TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS opening_line_generated_at TIMESTAMPTZ;

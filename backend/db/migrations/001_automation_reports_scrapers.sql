-- Migration 001 — adds DB backing for automations, reports, and scrapers.
-- Idempotent so it's safe to re-run on Neon (or any environment that already
-- has schema.sql applied). Run with:
--   psql $DATABASE_URL_PSQL < backend/db/migrations/001_automation_reports_scrapers.sql

-- ─────────────────────────────────────────
-- AUTOMATION TEMPLATES
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS automation_templates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key             TEXT NOT NULL UNIQUE,
  name            TEXT NOT NULL,
  description     TEXT,
  version         TEXT NOT NULL DEFAULT 'v1',
  status          TEXT NOT NULL DEFAULT 'active',
  step_count      INTEGER NOT NULL DEFAULT 0,
  channels_used   TEXT[] DEFAULT '{}',
  steps           JSONB NOT NULL DEFAULT '[]',
  placeholder_schema TEXT[] DEFAULT '{}',
  previews        JSONB NOT NULL DEFAULT '[]',
  created_at      TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────
-- AUTOMATION RUNS — one row per executing/completed sequence
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS automation_runs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL,

  lead_id           UUID REFERENCES leads(id) ON DELETE SET NULL,
  template_id       UUID REFERENCES automation_templates(id) ON DELETE SET NULL,
  template_key      TEXT NOT NULL,
  inngest_event_id  TEXT,

  status            TEXT NOT NULL DEFAULT 'running',
  current_step_name TEXT,
  next_fire_at      TIMESTAMPTZ,

  started_at        TIMESTAMPTZ DEFAULT NOW(),
  completed_at      TIMESTAMPTZ,
  created_by        TEXT DEFAULT 'admin:demo',

  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aruns_tenant_started ON automation_runs(tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_aruns_lead ON automation_runs(lead_id);
CREATE INDEX IF NOT EXISTS idx_aruns_template ON automation_runs(template_id);
CREATE INDEX IF NOT EXISTS idx_aruns_status ON automation_runs(tenant_id, status);


-- ─────────────────────────────────────────
-- AUTOMATION EVENTS — per-step ledger written by Inngest function
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS automation_events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id       UUID NOT NULL REFERENCES automation_runs(id) ON DELETE CASCADE,
  step_name    TEXT NOT NULL,
  channel      TEXT,
  outcome      TEXT NOT NULL,
  payload      JSONB DEFAULT '{}',
  occurred_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aevents_run_time ON automation_events(run_id, occurred_at);


-- ─────────────────────────────────────────
-- REPORTS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reports (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL,
  kind            TEXT NOT NULL DEFAULT 'weekly',
  period_start    TIMESTAMPTZ NOT NULL,
  period_end      TIMESTAMPTZ NOT NULL,
  headline        TEXT,
  narrative       TEXT,
  stats           JSONB NOT NULL DEFAULT '{}',
  prompt_version  TEXT DEFAULT 'v1',
  model           TEXT DEFAULT 'gemini/gemini-2.5-flash',
  has_embedding   BOOLEAN DEFAULT FALSE,
  generated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_tenant_kind_end ON reports(tenant_id, kind, period_end DESC);


-- ─────────────────────────────────────────
-- SCRAPERS — registry of configured scraper sources
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scrapers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL,
  source_key      TEXT NOT NULL,
  name            TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'available',  -- available | running | paused | failed
  schedule        TEXT DEFAULT '—',
  last_run_at     TIMESTAMPTZ,
  next_run_at     TIMESTAMPTZ,
  leads_last_run  INTEGER DEFAULT 0,
  leads_total     INTEGER DEFAULT 0,
  note            TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(tenant_id, source_key)
);

CREATE INDEX IF NOT EXISTS idx_scrapers_tenant ON scrapers(tenant_id);


-- ─────────────────────────────────────────
-- updated_at triggers (safe to re-create)
-- ─────────────────────────────────────────
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'aruns_updated_at') THEN
    CREATE TRIGGER aruns_updated_at
      BEFORE UPDATE ON automation_runs
      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'scrapers_updated_at') THEN
    CREATE TRIGGER scrapers_updated_at
      BEFORE UPDATE ON scrapers
      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
  END IF;
END $$;

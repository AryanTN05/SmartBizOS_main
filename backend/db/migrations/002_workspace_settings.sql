-- Migration 002 — workspace-scoped settings (ICP description, etc.)
-- Idempotent. Run via:
--   .venv/bin/python -m scripts.apply_migration db/migrations/002_workspace_settings.sql

CREATE TABLE IF NOT EXISTS workspace_settings (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL UNIQUE,

  -- Free-form ICP description that the LLM scorer interpolates into its
  -- system prompt. NULL = use the in-code default.
  icp_description TEXT,

  -- Display name + sender identity for outbound emails.
  workspace_name  TEXT,
  sender_name     TEXT,

  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_settings_tenant ON workspace_settings(tenant_id);

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'workspace_settings_updated_at') THEN
    CREATE TRIGGER workspace_settings_updated_at
      BEFORE UPDATE ON workspace_settings
      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
  END IF;
END $$;

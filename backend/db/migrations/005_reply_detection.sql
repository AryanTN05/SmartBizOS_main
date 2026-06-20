-- Migration 005 — reply detection: per-lead sequence_state + IMAP creds.
-- Idempotent. Run via:
--   .venv/bin/python -m scripts.apply_migration db/migrations/005_reply_detection.sql
--
-- Pass C, Feature 1 (catastrophic-failure-mode fix). Without this, sequences
-- keep firing after a prospect replies — kills trust at week 2.

ALTER TABLE leads ADD COLUMN IF NOT EXISTS sequence_state TEXT
  NOT NULL DEFAULT 'active';
-- expected values: active | paused_replied | paused_manual | completed
-- enforced at the application layer to keep migrations cheap (we can
-- promote to a real CHECK constraint without a backfill if we grow).

CREATE INDEX IF NOT EXISTS idx_leads_sequence_state
  ON leads(sequence_state)
  WHERE deleted_at IS NULL;

-- Last-reply marker for fast "show replied dot" queries on the inbox row.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_reply_at TIMESTAMPTZ;

-- Per-tenant IMAP credentials for the reply poller. password is stored as
-- Fernet ciphertext using IMAP_ENCRYPTION_KEY (set in env). Never returned
-- by any GET endpoint.
CREATE TABLE IF NOT EXISTS workspace_imap_settings (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL UNIQUE,
  host                TEXT NOT NULL,
  port                INTEGER NOT NULL DEFAULT 993,
  email               TEXT NOT NULL,
  password_ciphertext BYTEA NOT NULL,
  use_ssl             BOOLEAN NOT NULL DEFAULT true,
  last_poll_at        TIMESTAMPTZ,
  last_error          TEXT,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'workspace_imap_settings_updated_at') THEN
    CREATE TRIGGER workspace_imap_settings_updated_at
      BEFORE UPDATE ON workspace_imap_settings
      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
  END IF;
END $$;

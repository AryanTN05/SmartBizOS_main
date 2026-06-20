-- Migration 007 — multi-mailbox SMTP routing.
-- Adds per-tenant SMTP sending mailboxes for outbound rotation. Each row is
-- one inbox the user has connected (Gmail/Workspace, Outlook 365, custom).
-- The scheduler picks the next eligible mailbox at send time, respecting
-- per-mailbox daily volume caps so a single inbox doesn't burn its
-- reputation.
--
-- Reuses IMAP_ENCRYPTION_KEY (Fernet) for the SMTP password ciphertext —
-- one key, one ciphertext format across IMAP + SMTP.

CREATE TABLE IF NOT EXISTS workspace_mailboxes (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL,

  -- Display + From-address.
  email               TEXT NOT NULL,
  from_name           TEXT,                  -- "Kartik from Zerotoprod" etc

  -- SMTP creds.
  host                TEXT NOT NULL,
  port                INTEGER NOT NULL DEFAULT 587,
  username            TEXT NOT NULL,         -- usually the email itself
  password_ciphertext BYTEA NOT NULL,
  use_tls             BOOLEAN NOT NULL DEFAULT true,

  -- Volume + health.
  daily_send_cap      INTEGER NOT NULL DEFAULT 50,   -- per the May-2026 trend scan: 30-50/day per inbox
  sent_today          INTEGER NOT NULL DEFAULT 0,
  reset_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- rolled forward at first send each UTC day
  last_send_at        TIMESTAMPTZ,
  last_error          TEXT,

  -- enabled = scheduler may pick this mailbox; disabled = parked
  enabled             BOOLEAN NOT NULL DEFAULT true,

  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE (tenant_id, email)
);

CREATE INDEX IF NOT EXISTS idx_mailboxes_tenant_enabled
  ON workspace_mailboxes (tenant_id, enabled);

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'workspace_mailboxes_updated_at') THEN
    CREATE TRIGGER workspace_mailboxes_updated_at
      BEFORE UPDATE ON workspace_mailboxes
      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
  END IF;
END $$;

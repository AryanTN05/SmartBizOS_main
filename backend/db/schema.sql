-- ─────────────────────────────────────────
-- LEADS — core table
-- ─────────────────────────────────────────
CREATE TABLE leads (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL,

  -- Contact info
  name          TEXT NOT NULL,
  email         TEXT,
  phone         TEXT,
  company_name  TEXT,                  -- Human-readable display name e.g. "Stripe"
  company_domain TEXT,                 -- Root domain e.g. "stripe.com" — used for enrichment
  title         TEXT,
  linkedin_url  TEXT,

  -- Pipeline state
  status        TEXT NOT NULL DEFAULT 'new',

  -- Scoring
  score         INTEGER DEFAULT 0,
  score_reason  TEXT,

  -- Where this lead came from
  source        TEXT NOT NULL DEFAULT 'manual',
  source_ref_id TEXT,

  -- Free-form
  notes         TEXT,
  tags          TEXT[] DEFAULT '{}',

  -- Soft delete
  deleted_at    TIMESTAMPTZ DEFAULT NULL,

  -- Timestamps
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  last_activity TIMESTAMPTZ DEFAULT NOW()
);

-- Fast lookups
CREATE INDEX idx_leads_tenant_status ON leads(tenant_id, status);
CREATE INDEX idx_leads_tenant_score  ON leads(tenant_id, score DESC);
CREATE INDEX idx_leads_tenant_created ON leads(tenant_id, created_at DESC);


-- ─────────────────────────────────────────
-- ENRICHMENT — intel dossier per lead
-- ─────────────────────────────────────────
CREATE TABLE enrichment (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL,
  lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,

  -- Company intel
  company_size    TEXT,
  employee_count  INTEGER,
  industry        TEXT,
  funding_stage   TEXT,
  funding_amount  TEXT,

  -- Tech + behaviour
  tech_stack      TEXT[] DEFAULT '{}',
  pain_points     TEXT,
  recent_news     JSONB DEFAULT '[]',
  competitor_tools TEXT[] DEFAULT '{}',

  -- Enrichment metadata
  enrichment_status TEXT DEFAULT 'pending',
  last_enriched_at TIMESTAMPTZ,
  raw_data         JSONB DEFAULT '{}',

  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_enrichment_lead ON enrichment(lead_id);
CREATE INDEX idx_enrichment_tenant ON enrichment(tenant_id);


-- ─────────────────────────────────────────
-- SCORE HISTORY — every scoring event
-- ─────────────────────────────────────────
CREATE TABLE score_history (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL,
  lead_id     UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,

  score       INTEGER NOT NULL,
  reason      TEXT,
  factors     JSONB DEFAULT '{}',
  scored_by   TEXT DEFAULT 'ai',
  scored_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_score_lead ON score_history(lead_id);
CREATE INDEX idx_score_tenant_time ON score_history(tenant_id, scored_at DESC);


-- ─────────────────────────────────────────
-- ACTIVITY LOG — full lead timeline
-- ─────────────────────────────────────────
CREATE TABLE activity_log (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL,
  lead_id     UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,

  action_type TEXT NOT NULL,
  description TEXT,
  metadata    JSONB DEFAULT '{}',
  triggered_by TEXT DEFAULT 'system',
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_activity_lead ON activity_log(lead_id);
CREATE INDEX idx_activity_tenant_time ON activity_log(tenant_id, created_at DESC);
CREATE INDEX idx_activity_tenant_type ON activity_log(tenant_id, action_type);


-- ─────────────────────────────────────────
-- INTEGRATIONS — connected external sources
-- ─────────────────────────────────────────
CREATE TABLE integrations (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL,

  type          TEXT NOT NULL,
  status        TEXT DEFAULT 'connected',
  config        JSONB DEFAULT '{}',
  last_synced_at TIMESTAMPTZ,
  last_sync_count INTEGER DEFAULT 0,
  error_message  TEXT,

  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(tenant_id, type)
);


-- ─────────────────────────────────────────
-- SCRAPER RESULTS — staging area
-- ─────────────────────────────────────────
CREATE TABLE scraper_results (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL,

  source_type     TEXT NOT NULL,
  raw_data        JSONB NOT NULL,
  
  extracted_name    TEXT,
  extracted_email   TEXT,
  extracted_company TEXT,
  extracted_url     TEXT,

  relevance_score INTEGER,
  status          TEXT DEFAULT 'pending',
  converted_lead_id UUID REFERENCES leads(id),

  scraped_at      TIMESTAMPTZ DEFAULT NOW(),
  reviewed_at     TIMESTAMPTZ
);

CREATE INDEX idx_scraper_tenant_status ON scraper_results(tenant_id, status);

-- ─────────────────────────────────────────
-- HELPER: auto-update updated_at
-- ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER leads_updated_at
  BEFORE UPDATE ON leads
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER integrations_updated_at
  BEFORE UPDATE ON integrations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ─────────────────────────────────────────
-- ADMIN USERS — seeded from env on startup
-- ─────────────────────────────────────────
CREATE TABLE admin_users (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email          TEXT NOT NULL UNIQUE,
  bcrypt_hash    TEXT NOT NULL,
  name           TEXT NOT NULL DEFAULT '',
  role           TEXT NOT NULL DEFAULT 'admin',   -- forward-compat: admin | sales | readonly
  status         TEXT NOT NULL DEFAULT 'active',  -- active | disabled
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  last_login_at  TIMESTAMPTZ
);

CREATE INDEX idx_admin_users_email ON admin_users(email);

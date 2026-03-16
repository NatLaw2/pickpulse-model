-- =============================================================================
-- Engine Tables — Production Schema
-- Creates (or upgrades) the four tables backing DB-backed job tracking,
-- model versioning, persistent predictions, and audit logging.
--
-- Previous migration (20260223_create_engine_tables.sql) created these tables
-- with a generic schema and no tenant isolation. Those tables had no
-- production data; this migration adds all required columns via
-- ADD COLUMN IF NOT EXISTS so it is safe to run on either a fresh database
-- or one with the legacy schema in place.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- datasets
-- Replaces the flat .dataset_state.json file.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS datasets (
    id              UUID         DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id       UUID         NOT NULL,
    module          TEXT         NOT NULL,
    filename        TEXT,
    raw_path        TEXT,
    readiness_mode  TEXT,
    source_columns  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    confirmed_mappings JSONB     NOT NULL DEFAULT '{}'::jsonb,
    is_current      BOOLEAN      NOT NULL DEFAULT TRUE,
    registered_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Columns added for upgrades from the 20260223 schema
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS tenant_id       UUID;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS filename        TEXT;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS raw_path        TEXT;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS readiness_mode  TEXT;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS source_columns  JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS confirmed_mappings JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS is_current      BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS registered_at   TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_datasets_tenant_module
    ON datasets (tenant_id, module, is_current);

-- ---------------------------------------------------------------------------
-- model_runs
-- Tracks training jobs (pending → running → complete/failed) and stores the
-- artifact path for each versioned model. is_current marks the active model.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_runs (
    id              UUID         DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id       UUID         NOT NULL,
    module          TEXT         NOT NULL,
    version_str     TEXT,
    artifact_path   TEXT,
    status          TEXT         NOT NULL DEFAULT 'pending',
    metrics_json    JSONB,
    feature_meta_json JSONB,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    is_current      BOOLEAN      NOT NULL DEFAULT FALSE,
    trained_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Columns added for upgrades from the 20260223 schema
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS tenant_id       UUID;
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS version_str     TEXT;
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS artifact_path   TEXT;
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS status          TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS metrics_json    JSONB;
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS feature_meta_json JSONB;
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS error_message   TEXT;
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS started_at      TIMESTAMPTZ;
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS completed_at    TIMESTAMPTZ;
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS is_current      BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS trained_at      TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_model_runs_tenant_module
    ON model_runs (tenant_id, module, is_current);
CREATE INDEX IF NOT EXISTS idx_model_runs_status
    ON model_runs (status, trained_at DESC);

-- ---------------------------------------------------------------------------
-- predictions_live
-- Stores per-account predictions and account status for each tenant.
-- account_id + tenant_id + module is unique per run; status tracks CSM actions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS predictions_live (
    id                  UUID         DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id           UUID         NOT NULL,
    module              TEXT         NOT NULL,
    model_run_id        UUID         REFERENCES model_runs(id) ON DELETE SET NULL,
    account_id          TEXT         NOT NULL,
    score               NUMERIC,
    confidence_tier     TEXT,
    status              TEXT         NOT NULL DEFAULT 'none',
    status_changed_at   TIMESTAMPTZ,
    prediction_json     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    predicted_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Columns added for upgrades from the 20260223 schema
ALTER TABLE predictions_live ADD COLUMN IF NOT EXISTS tenant_id         UUID;
ALTER TABLE predictions_live ADD COLUMN IF NOT EXISTS model_run_id      UUID REFERENCES model_runs(id) ON DELETE SET NULL;
ALTER TABLE predictions_live ADD COLUMN IF NOT EXISTS account_id        TEXT;
ALTER TABLE predictions_live ADD COLUMN IF NOT EXISTS score             NUMERIC;
ALTER TABLE predictions_live ADD COLUMN IF NOT EXISTS confidence_tier   TEXT;
ALTER TABLE predictions_live ADD COLUMN IF NOT EXISTS status            TEXT NOT NULL DEFAULT 'none';
ALTER TABLE predictions_live ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ;
ALTER TABLE predictions_live ADD COLUMN IF NOT EXISTS prediction_json   JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE predictions_live ADD COLUMN IF NOT EXISTS predicted_at      TIMESTAMPTZ DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS uq_predictions_tenant_module_account
    ON predictions_live (tenant_id, module, account_id);
CREATE INDEX IF NOT EXISTS idx_predictions_tenant_module
    ON predictions_live (tenant_id, module, predicted_at DESC);

-- ---------------------------------------------------------------------------
-- audit_log
-- Append-only log of state-changing actions (never deleted).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID         DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id       UUID         NOT NULL,
    user_id         UUID,
    action          TEXT         NOT NULL,
    entity_id       TEXT,
    metadata_json   JSONB,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_tenant
    ON audit_log (tenant_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- RLS — tenant_id = auth.uid() on all four tables
-- Drops old policies (from 20260223 service_role_all) before recreating.
-- ---------------------------------------------------------------------------
ALTER TABLE datasets         ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_runs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions_live ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log        ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['datasets', 'model_runs', 'predictions_live', 'audit_log']
    LOOP
        -- Drop the permissive service_role_all policy added in 20260223
        EXECUTE format('DROP POLICY IF EXISTS service_role_all ON %I', t);
        -- Drop prior tenant isolation policy if it was already applied
        EXECUTE format('DROP POLICY IF EXISTS "Tenant isolation on %s" ON %I', t, t);
        -- Recreate with auth.uid() enforcement
        EXECUTE format(
            'CREATE POLICY "Tenant isolation on %s" ON %I FOR ALL TO authenticated '
            'USING (tenant_id = auth.uid()) WITH CHECK (tenant_id = auth.uid())',
            t, t
        );
    END LOOP;
END $$;

DO $$ BEGIN
    RAISE NOTICE 'Engine table migration (20260316) complete.';
END $$;

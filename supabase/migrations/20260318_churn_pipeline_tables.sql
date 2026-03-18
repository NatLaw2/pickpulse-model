-- =============================================================================
-- Churn Integration Pipeline Tables (correct multi-tenant version)
--
-- Supersedes 20260225_create_churn_integration_tables.sql which was missing
-- tenant_id on all three tables.  app/storage/repo.py upserts use conflict
-- keys (tenant_id, source, external_id), (tenant_id, account_id, signal_date,
-- signal_key), and (tenant_id, account_id, score_date) — all of which require
-- tenant_id as a real column.
--
-- Safe to run on a fresh database.  Tables are created with IF NOT EXISTS so
-- running twice is a no-op.  The old 20260225 migration should NOT be applied
-- if this one is used.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Reuse set_updated_at() if already defined by integration_platform migration.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
-- 1) accounts
--    Unique key: (tenant_id, source, external_id)
--    matches repo.upsert_accounts on_conflict="tenant_id,source,external_id"
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.accounts (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   text        NOT NULL,
    source      text        NOT NULL,
    external_id text        NOT NULL,
    name        text,
    domain      text,
    arr         numeric,
    status      text        NOT NULL DEFAULT 'active',
    auto_renew  boolean,
    metadata    jsonb,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT accounts_tenant_source_external_id_key
        UNIQUE (tenant_id, source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_accounts_tenant   ON public.accounts (tenant_id);
CREATE INDEX IF NOT EXISTS idx_accounts_source   ON public.accounts (source);

DROP TRIGGER IF EXISTS trg_accounts_updated_at ON public.accounts;
CREATE TRIGGER trg_accounts_updated_at
    BEFORE UPDATE ON public.accounts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ---------------------------------------------------------------------------
-- 2) account_signals_daily
--    Unique key: (tenant_id, account_id, signal_date, signal_key)
--    matches repo.upsert_signals on_conflict="tenant_id,account_id,signal_date,signal_key"
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.account_signals_daily (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    text        NOT NULL,
    account_id   uuid        NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    signal_date  date        NOT NULL,
    signal_key   text        NOT NULL,
    signal_value numeric,
    signal_text  text,
    CONSTRAINT account_signals_daily_tenant_account_date_key_key
        UNIQUE (tenant_id, account_id, signal_date, signal_key)
);

CREATE INDEX IF NOT EXISTS idx_signals_tenant ON public.account_signals_daily (tenant_id);
CREATE INDEX IF NOT EXISTS idx_signals_date   ON public.account_signals_daily (signal_date);


-- ---------------------------------------------------------------------------
-- 3) churn_scores_daily
--    Unique key: (tenant_id, account_id, score_date)
--    matches repo.insert_scores on_conflict="tenant_id,account_id,score_date"
--
--    latest_scores() uses PostgREST FK embedding:
--      .select("*, accounts(name, domain, arr, source, external_id, metadata)")
--    This works because account_id FK → accounts.id.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.churn_scores_daily (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          text        NOT NULL,
    account_id         uuid        NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    score_date         date        NOT NULL,
    churn_risk_pct     numeric     NOT NULL,
    urgency            numeric,
    renewal_window     text,
    arr_at_risk        numeric,
    recommended_action text,
    account_status     text        NOT NULL DEFAULT 'active',
    model_version      text        NOT NULL DEFAULT 'churn_v1',
    CONSTRAINT churn_scores_daily_tenant_account_date_key
        UNIQUE (tenant_id, account_id, score_date)
);

CREATE INDEX IF NOT EXISTS idx_scores_tenant    ON public.churn_scores_daily (tenant_id);
CREATE INDEX IF NOT EXISTS idx_scores_date      ON public.churn_scores_daily (score_date);
CREATE INDEX IF NOT EXISTS idx_scores_risk_desc ON public.churn_scores_daily (churn_risk_pct DESC);


-- ---------------------------------------------------------------------------
-- RLS — service role bypasses by default; enable for future tenant policies
-- ---------------------------------------------------------------------------
ALTER TABLE public.accounts              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_signals_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.churn_scores_daily    ENABLE ROW LEVEL SECURITY;

-- Permissive policies for service role (backend uses service_role key)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'accounts' AND policyname = 'Service role full access on accounts'
  ) THEN
    CREATE POLICY "Service role full access on accounts"
        ON public.accounts FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'account_signals_daily' AND policyname = 'Service role full access on account_signals_daily'
  ) THEN
    CREATE POLICY "Service role full access on account_signals_daily"
        ON public.account_signals_daily FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'churn_scores_daily' AND policyname = 'Service role full access on churn_scores_daily'
  ) THEN
    CREATE POLICY "Service role full access on churn_scores_daily"
        ON public.churn_scores_daily FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;

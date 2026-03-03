-- =============================================================================
-- Multi-Tenancy Migration
-- Adds tenant_id to all core tables, updates unique constraints, enables RLS
-- with auth.uid()-based policies for the authenticated role.
-- Existing rows get the default tenant UUID (backward compatible).
-- =============================================================================

-- Default tenant UUID for existing data
DO $$ BEGIN
    RAISE NOTICE 'Adding tenant_id to core tables...';
END $$;

-- ---------------------------------------------------------------------------
-- 1) accounts — add tenant_id, update unique constraint
-- ---------------------------------------------------------------------------
ALTER TABLE public.accounts
    ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::uuid;

DROP INDEX IF EXISTS uq_accounts_source_external;
CREATE UNIQUE INDEX uq_accounts_source_external
    ON public.accounts (tenant_id, source, external_id);

CREATE INDEX IF NOT EXISTS idx_accounts_tenant
    ON public.accounts (tenant_id);

-- ---------------------------------------------------------------------------
-- 2) account_signals_daily — add tenant_id, update unique constraint
-- ---------------------------------------------------------------------------
ALTER TABLE public.account_signals_daily
    ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::uuid;

DROP INDEX IF EXISTS uq_signals_account_date_key;
CREATE UNIQUE INDEX uq_signals_account_date_key
    ON public.account_signals_daily (tenant_id, account_id, signal_date, signal_key);

CREATE INDEX IF NOT EXISTS idx_signals_tenant
    ON public.account_signals_daily (tenant_id);

-- ---------------------------------------------------------------------------
-- 3) churn_scores_daily — add tenant_id, update unique constraint
-- ---------------------------------------------------------------------------
ALTER TABLE public.churn_scores_daily
    ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::uuid;

DROP INDEX IF EXISTS uq_scores_account_date;
CREATE UNIQUE INDEX uq_scores_account_date
    ON public.churn_scores_daily (tenant_id, account_id, score_date);

CREATE INDEX IF NOT EXISTS idx_scores_tenant
    ON public.churn_scores_daily (tenant_id);

-- ---------------------------------------------------------------------------
-- 4-8) Engine tables — only alter if they exist in this database
--      (these tables may not have been created in Supabase; the app
--       stores model artifacts on disk, not in these tables)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    -- model_runs
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'model_runs') THEN
        ALTER TABLE public.model_runs ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::uuid;
        CREATE INDEX IF NOT EXISTS idx_model_runs_tenant ON public.model_runs (tenant_id);
    END IF;

    -- model_run_rows
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'model_run_rows') THEN
        ALTER TABLE public.model_run_rows ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::uuid;
        CREATE INDEX IF NOT EXISTS idx_model_run_rows_tenant ON public.model_run_rows (tenant_id);
    END IF;

    -- predictions_live
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'predictions_live') THEN
        ALTER TABLE public.predictions_live ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::uuid;
        CREATE INDEX IF NOT EXISTS idx_predictions_live_tenant ON public.predictions_live (tenant_id);
    END IF;

    -- datasets
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'datasets') THEN
        ALTER TABLE public.datasets ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::uuid;
        CREATE INDEX IF NOT EXISTS idx_datasets_tenant ON public.datasets (tenant_id);
    END IF;

    -- onboarding_customers
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'onboarding_customers') THEN
        ALTER TABLE public.onboarding_customers ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::uuid;
        CREATE INDEX IF NOT EXISTS idx_onboarding_customers_tenant ON public.onboarding_customers (tenant_id);
    END IF;
END $$;

-- ===========================================================================
-- RLS Policies for authenticated role (tenant_id = auth.uid())
-- ===========================================================================

-- accounts
ALTER TABLE public.accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tenant isolation on accounts"
    ON public.accounts FOR ALL
    TO authenticated
    USING (tenant_id = auth.uid())
    WITH CHECK (tenant_id = auth.uid());

-- account_signals_daily
ALTER TABLE public.account_signals_daily ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tenant isolation on account_signals_daily"
    ON public.account_signals_daily FOR ALL
    TO authenticated
    USING (tenant_id = auth.uid())
    WITH CHECK (tenant_id = auth.uid());

-- churn_scores_daily
ALTER TABLE public.churn_scores_daily ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tenant isolation on churn_scores_daily"
    ON public.churn_scores_daily FOR ALL
    TO authenticated
    USING (tenant_id = auth.uid())
    WITH CHECK (tenant_id = auth.uid());

-- Engine tables RLS policies (only if tables exist)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'model_runs') THEN
        EXECUTE 'CREATE POLICY "Tenant isolation on model_runs" ON public.model_runs FOR ALL TO authenticated USING (tenant_id = auth.uid()) WITH CHECK (tenant_id = auth.uid())';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'model_run_rows') THEN
        EXECUTE 'CREATE POLICY "Tenant isolation on model_run_rows" ON public.model_run_rows FOR ALL TO authenticated USING (tenant_id = auth.uid()) WITH CHECK (tenant_id = auth.uid())';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'predictions_live') THEN
        EXECUTE 'CREATE POLICY "Tenant isolation on predictions_live" ON public.predictions_live FOR ALL TO authenticated USING (tenant_id = auth.uid()) WITH CHECK (tenant_id = auth.uid())';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'datasets') THEN
        EXECUTE 'CREATE POLICY "Tenant isolation on datasets" ON public.datasets FOR ALL TO authenticated USING (tenant_id = auth.uid()) WITH CHECK (tenant_id = auth.uid())';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'onboarding_customers') THEN
        EXECUTE 'CREATE POLICY "Tenant isolation on onboarding_customers" ON public.onboarding_customers FOR ALL TO authenticated USING (tenant_id = auth.uid()) WITH CHECK (tenant_id = auth.uid())';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Integration child tables: tenant isolation via join to integrations
-- ---------------------------------------------------------------------------

CREATE POLICY "Tenant isolation on integration_tokens"
    ON public.integration_tokens FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.integrations i
            WHERE i.id = integration_id AND i.tenant_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.integrations i
            WHERE i.id = integration_id AND i.tenant_id = auth.uid()
        )
    );

CREATE POLICY "Tenant isolation on integration_sync_state"
    ON public.integration_sync_state FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.integrations i
            WHERE i.id = integration_id AND i.tenant_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.integrations i
            WHERE i.id = integration_id AND i.tenant_id = auth.uid()
        )
    );

CREATE POLICY "Tenant isolation on integration_field_mappings"
    ON public.integration_field_mappings FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.integrations i
            WHERE i.id = integration_id AND i.tenant_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.integrations i
            WHERE i.id = integration_id AND i.tenant_id = auth.uid()
        )
    );

CREATE POLICY "Tenant isolation on integration_events"
    ON public.integration_events FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.integrations i
            WHERE i.id = integration_id AND i.tenant_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.integrations i
            WHERE i.id = integration_id AND i.tenant_id = auth.uid()
        )
    );

CREATE POLICY "Tenant isolation on integrations"
    ON public.integrations FOR ALL
    TO authenticated
    USING (tenant_id = auth.uid())
    WITH CHECK (tenant_id = auth.uid());

DO $$ BEGIN
    RAISE NOTICE 'Multi-tenancy migration complete.';
END $$;

-- Predictive Engine OS — Generic storage tables
-- These supplement existing sports-specific tables (no breaking changes)

-- Model runs (generic version of model_backtest_runs)
CREATE TABLE IF NOT EXISTS model_runs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    module TEXT NOT NULL,                   -- 'sales', 'churn', etc.
    model_version TEXT,
    n_samples INT,
    n_train INT,
    n_val INT,
    model_type TEXT,                        -- 'logistic', 'gradient_boosting'
    calibration_method TEXT,
    train_metrics JSONB,
    val_metrics JSONB,
    feature_importance JSONB,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

-- Model run rows (individual scored rows from a run)
CREATE TABLE IF NOT EXISTS model_run_rows (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    run_id UUID REFERENCES model_runs(id) ON DELETE CASCADE,
    module TEXT NOT NULL,
    entity_id TEXT,                         -- deal_id, customer_id, etc.
    timestamp TIMESTAMPTZ,
    probability FLOAT,
    tier TEXT,
    rank INT,
    label INT,                             -- actual outcome if known
    value FLOAT,                           -- deal amount, ARR, etc.
    value_at_risk FLOAT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Live predictions (for production scoring)
CREATE TABLE IF NOT EXISTS predictions_live (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    module TEXT NOT NULL,
    model_version TEXT,
    entity_id TEXT NOT NULL,
    probability FLOAT NOT NULL,
    tier TEXT,
    rank INT,
    value_at_risk FLOAT,
    features_used JSONB,
    scored_at TIMESTAMPTZ DEFAULT now()
);

-- Dataset metadata
CREATE TABLE IF NOT EXISTS datasets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    module TEXT NOT NULL,
    name TEXT,
    storage_path TEXT,
    n_rows INT,
    n_columns INT,
    validation_result JSONB,
    uploaded_at TIMESTAMPTZ DEFAULT now()
);

-- Onboarding customers
CREATE TABLE IF NOT EXISTS onboarding_customers (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    company_name TEXT NOT NULL,
    module TEXT NOT NULL,
    status TEXT DEFAULT 'kickoff',          -- kickoff, data_sent, training, live, etc.
    steps_completed JSONB DEFAULT '[]'::jsonb,
    contact_email TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_model_runs_module ON model_runs(module);
CREATE INDEX IF NOT EXISTS idx_model_run_rows_run_id ON model_run_rows(run_id);
CREATE INDEX IF NOT EXISTS idx_predictions_live_module ON predictions_live(module, scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_live_entity ON predictions_live(entity_id);
CREATE INDEX IF NOT EXISTS idx_datasets_module ON datasets(module);

-- RLS: service role only for demo
ALTER TABLE model_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_run_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions_live ENABLE ROW LEVEL SECURITY;
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE onboarding_customers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON model_runs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON model_run_rows FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON predictions_live FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON datasets FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON onboarding_customers FOR ALL USING (true) WITH CHECK (true);

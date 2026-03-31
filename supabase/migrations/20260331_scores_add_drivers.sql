-- Phase 1: Add SHAP-derived driver columns to churn_scores_daily
-- top_drivers: JSON array of {feature, shap_value, direction} per account
-- confidence_level: "high" | "medium" | "low" based on feature data coverage

ALTER TABLE public.churn_scores_daily
    ADD COLUMN IF NOT EXISTS top_drivers    jsonb   DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS confidence_level text;

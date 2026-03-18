-- Migration: 20260317_add_patch_prediction_json_rpc
-- Adds the patch_prediction_json stored procedure used by store.py to perform
-- a server-side JSONB merge on predictions_live without a read-modify-write cycle.
--
-- Called by: app/engine/store.py patch_prediction_json()
-- Parameters mirror the Python call:
--   p_tenant_id  TEXT   — tenant UUID (matches tenant_id column)
--   p_module     TEXT   — module name, e.g. "churn"
--   p_account_id TEXT   — account identifier
--   p_patch      JSONB  — key/value pairs to merge into the existing prediction_json

CREATE OR REPLACE FUNCTION patch_prediction_json(
    p_tenant_id  TEXT,
    p_module     TEXT,
    p_account_id TEXT,
    p_patch      JSONB
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER   -- runs as the function owner (bypasses RLS), safe because
                   -- the service-role caller already has full access
AS $$
BEGIN
    UPDATE predictions_live
    SET    prediction_json = COALESCE(prediction_json, '{}'::jsonb) || p_patch
    WHERE  tenant_id  = p_tenant_id
      AND  module     = p_module
      AND  account_id = p_account_id;
END;
$$;

-- Grant execution to the service role (used by the backend) and authenticated
-- users (in case the anon/auth clients ever call it directly).
GRANT EXECUTE ON FUNCTION patch_prediction_json(TEXT, TEXT, TEXT, JSONB)
    TO service_role, authenticated;

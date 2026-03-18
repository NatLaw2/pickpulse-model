-- Migration: 20260318_datasets_add_metadata_columns
-- Adds row_count, column_count, and is_demo to the datasets table so that
-- store.get_current_dataset() can return a fully-hydrated dataset object
-- after a cold start, without needing the in-memory cache.
--
-- Previously these fields existed only in the in-memory _tenant_state dict
-- and were lost on every process restart, causing frontend crashes when
-- dataset.rows or dataset.columns were undefined.
--
-- Safe to run on existing databases: ADD COLUMN IF NOT EXISTS with defaults
-- means existing rows get row_count=0, column_count=0, is_demo=false.
-- They will be correct on the next dataset upload.

ALTER TABLE datasets
  ADD COLUMN IF NOT EXISTS row_count    INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS column_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS is_demo      BOOLEAN NOT NULL DEFAULT false;

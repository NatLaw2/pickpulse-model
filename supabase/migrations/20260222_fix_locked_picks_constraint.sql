-- ==========================================================================
-- Fix locked_picks unique constraint to allow multiple markets per game.
--
-- Old: (run_date, event_id) — only 1 pick per game per day
-- New: (run_date, event_id, market) — 1 pick per game per market per day
--
-- Also: ensures idempotent re-lock attempts are silently ignored.
-- ==========================================================================

-- Drop old constraint
ALTER TABLE locked_picks
  DROP CONSTRAINT IF EXISTS locked_picks_run_date_event_id_key;

-- Add new composite unique constraint
ALTER TABLE locked_picks
  ADD CONSTRAINT locked_picks_run_date_event_market_key
  UNIQUE (run_date, event_id, market);

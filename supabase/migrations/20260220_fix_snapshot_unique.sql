-- ==========================================================================
-- Fix closing_lines unique indexes so near-tip snapshots ACCUMULATE
-- ==========================================================================
--
-- ROOT CAUSE: Two old unique indexes block new snapshot rows:
--   - closing_lines_unique_row    (sport, event_id, bookmaker_key, market, outcome_name, COALESCE(point,0))
--   - closing_lines_unique_row_v2 (sport, event_id, bookmaker_key, market, outcome_name, point)
-- Neither includes a timestamp, so any second snapshot for the same
-- event/bookmaker/market/outcome silently fails (ignoreDuplicates).
--
-- FIX: Drop both old indexes.  Keep closing_lines_snap_unique which
-- includes captured_minute for per-minute deduplication.  Rebuild it
-- on plain columns (no COALESCE expression) so Supabase JS onConflict works.
--
-- The edge function snap_odds_nba_near_tip is updated to populate
-- captured_minute = date_trunc('minute', captured_at) on every insert.
-- ==========================================================================

-- 1. Drop old indexes that block multi-snapshot inserts
DROP INDEX IF EXISTS closing_lines_unique_row;
DROP INDEX IF EXISTS closing_lines_unique_row_v2;

-- 2. Drop the existing snap_unique (uses COALESCE expression, incompatible with onConflict)
DROP INDEX IF EXISTS closing_lines_snap_unique;

-- 3. Backfill captured_minute for any existing rows
UPDATE closing_lines
SET captured_minute = date_trunc('minute', captured_at)
WHERE captured_minute IS NULL;

-- 4. Create clean unique index on plain columns (no expressions)
--    point is NOT NULL DEFAULT 0, so no COALESCE needed.
CREATE UNIQUE INDEX closing_lines_snap_unique
ON closing_lines (sport, event_id, bookmaker_key, market, outcome_name, point, captured_minute);

-- 5. Verify
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'closing_lines'
ORDER BY indexname;

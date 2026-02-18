-- Allow multiple captured_at snapshots per event in closing_lines.
--
-- The old unique constraint was:
--   (sport, event_id, bookmaker_key, market, outcome_name, point)
-- which caused upserts to overwrite captured_at on every run,
-- leaving only a single snapshot per event.
--
-- The new constraint adds captured_at (truncated to the minute) so
-- that each 2-minute cron run inserts a NEW row instead of overwriting.
--
-- Run against production Supabase via SQL Editor or psql.

-- Step 1: drop the old constraint (find its actual name first)
-- NOTE: the constraint name may differ — check with:
--   SELECT conname FROM pg_constraint WHERE conrelid = 'closing_lines'::regclass AND contype = 'u';
-- Common names: closing_lines_sport_event_id_bookmaker_key_market_outcome_na_key

DO $$
DECLARE
    cname text;
BEGIN
    SELECT conname INTO cname
    FROM pg_constraint
    WHERE conrelid = 'closing_lines'::regclass
      AND contype = 'u'
    LIMIT 1;

    IF cname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE closing_lines DROP CONSTRAINT %I', cname);
        RAISE NOTICE 'Dropped constraint: %', cname;
    ELSE
        RAISE NOTICE 'No unique constraint found on closing_lines — skipping drop';
    END IF;
END $$;

-- Step 2: add new constraint that includes captured_at truncated to minute
-- Using a unique INDEX with expression (date_trunc) instead of a plain constraint
-- so that snapshots within the same minute still de-duplicate.
CREATE UNIQUE INDEX IF NOT EXISTS closing_lines_snap_unique
ON closing_lines (
    sport,
    event_id,
    bookmaker_key,
    market,
    outcome_name,
    COALESCE(point, 0),
    date_trunc('minute', captured_at)
);

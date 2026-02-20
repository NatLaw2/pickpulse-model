-- ==========================================================================
-- Fix cron jobs: use jsonb_build_object() to prevent 0x0a JSON parse errors
-- ==========================================================================
--
-- INSTRUCTIONS:
--   1. Copy this entire file into Supabase SQL Editor
--   2. Find-and-replace __PASTE_SERVICE_ROLE_KEY_HERE__ with your actual
--      service role key (no quotes, no newlines)
--   3. Run the query
--   4. Verify: SELECT jobname, schedule FROM cron.job ORDER BY jobname;
--
-- Root cause: pasting the JWT with a trailing newline into a raw JSON string
-- like '{"Authorization":"Bearer eyJ...\n"}' causes Postgres to reject it
-- with "Character with value 0x0a must be escaped".
--
-- Fix: jsonb_build_object() handles escaping automatically.
-- ==========================================================================

-- Unschedule existing jobs (ignore errors if they don't exist)
SELECT cron.unschedule(jobname)
FROM cron.job
WHERE jobname IN (
  'snap-odds-nba-2min',
  'lock-picks-tminus15-5min',
  'capture-closing-nba-5min',
  'grade-picks-5min',
  'final-nba-5min'
);

-- -----------------------------------------------------------------------
-- 1. snap_odds_nba_near_tip — every 2 minutes
--    Captures odds snapshots for games within T-90
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'snap-odds-nba-2min',
  '*/2 * * * *',
  $$
  SELECT net.http_post(
    url   := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/snap_odds_nba_near_tip',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer __PASTE_SERVICE_ROLE_KEY_HERE__'
    ),
    body  := '{}'::jsonb
  );
  $$
);

-- -----------------------------------------------------------------------
-- 2. lock_picks_tminus15 — every 5 minutes
--    Locks picks at T-15 before game start
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'lock-picks-tminus15-5min',
  '*/5 * * * *',
  $$
  SELECT net.http_post(
    url   := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/lock_picks_tminus15',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer __PASTE_SERVICE_ROLE_KEY_HERE__'
    ),
    body  := '{}'::jsonb
  );
  $$
);

-- -----------------------------------------------------------------------
-- 3. capture_closing_nba — every 5 minutes
--    Fills closing odds on game_results from closing_lines snapshots
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'capture-closing-nba-5min',
  '*/5 * * * *',
  $$
  SELECT net.http_post(
    url   := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/capture_closing_nba',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer __PASTE_SERVICE_ROLE_KEY_HERE__'
    ),
    body  := '{}'::jsonb
  );
  $$
);

-- -----------------------------------------------------------------------
-- 4. grade_picks — every 5 minutes
--    Grades locked_picks against game_results, writes pick_results
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'grade-picks-5min',
  '*/5 * * * *',
  $$
  SELECT net.http_post(
    url   := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/grade_picks',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer __PASTE_SERVICE_ROLE_KEY_HERE__'
    ),
    body  := '{}'::jsonb
  );
  $$
);

-- -----------------------------------------------------------------------
-- 5. final_nba — every 5 minutes
--    Fetches final scores from Odds API, upserts game_results
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'final-nba-5min',
  '*/5 * * * *',
  $$
  SELECT net.http_post(
    url   := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/final_nba',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer __PASTE_SERVICE_ROLE_KEY_HERE__'
    ),
    body  := '{}'::jsonb
  );
  $$
);

-- -----------------------------------------------------------------------
-- Verify
-- -----------------------------------------------------------------------
SELECT jobname, schedule, active
FROM cron.job
ORDER BY jobname;

-- ==========================================================================
-- Fix cron jobs: deploy functions with --no-verify-jwt, remove empty Bearer
-- tokens, set proper timeouts.
--
-- Root cause: the old migration used a placeholder key that was never
-- replaced, resulting in `Authorization: Bearer ` (empty key) → 401.
-- Additionally, lock_picks_tminus15 chains through slate → Odds API → model,
-- which takes >5s and hit the default net.http_post 5s timeout.
--
-- Fix:
--   1. All 5 edge functions deployed with --no-verify-jwt (no auth needed)
--   2. Cron jobs use simple Content-Type header (no Authorization needed)
--   3. lock_picks_tminus15 gets 30s timeout; others get 15s
--
-- Applied: 2026-02-22
-- ==========================================================================

-- Unschedule all existing pipeline jobs
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
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'snap-odds-nba-2min',
  '*/2 * * * *',
  $$
  SELECT net.http_post(
    url     := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/snap_odds_nba_near_tip',
    headers := '{"Content-Type": "application/json"}'::jsonb,
    body    := '{}'::jsonb,
    timeout_milliseconds := 15000
  );
  $$
);

-- -----------------------------------------------------------------------
-- 2. lock_picks_tminus15 — every 5 minutes  (30s timeout: chains to slate)
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'lock-picks-tminus15-5min',
  '*/5 * * * *',
  $$
  SELECT net.http_post(
    url     := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/lock_picks_tminus15',
    headers := '{"Content-Type": "application/json"}'::jsonb,
    body    := '{}'::jsonb,
    timeout_milliseconds := 30000
  );
  $$
);

-- -----------------------------------------------------------------------
-- 3. capture_closing_nba — every 5 minutes
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'capture-closing-nba-5min',
  '*/5 * * * *',
  $$
  SELECT net.http_post(
    url     := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/capture_closing_nba',
    headers := '{"Content-Type": "application/json"}'::jsonb,
    body    := '{}'::jsonb,
    timeout_milliseconds := 15000
  );
  $$
);

-- -----------------------------------------------------------------------
-- 4. grade_picks — every 5 minutes
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'grade-picks-5min',
  '*/5 * * * *',
  $$
  SELECT net.http_post(
    url     := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/grade_picks',
    headers := '{"Content-Type": "application/json"}'::jsonb,
    body    := '{}'::jsonb,
    timeout_milliseconds := 15000
  );
  $$
);

-- -----------------------------------------------------------------------
-- 5. final_nba — every 5 minutes
-- -----------------------------------------------------------------------
SELECT cron.schedule(
  'final-nba-5min',
  '*/5 * * * *',
  $$
  SELECT net.http_post(
    url     := 'https://cctvkxxnrhkhapcvwbgp.supabase.co/functions/v1/final_nba',
    headers := '{"Content-Type": "application/json"}'::jsonb,
    body    := '{}'::jsonb,
    timeout_milliseconds := 15000
  );
  $$
);

-- -----------------------------------------------------------------------
-- Verify
-- -----------------------------------------------------------------------
SELECT jobname, schedule, active
FROM cron.job
ORDER BY jobname;

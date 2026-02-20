-- ==========================================================================
-- Create monitoring views for pipeline health checks
-- ==========================================================================

-- v_recent_locked_picks: canonical view for "recent locked picks" monitoring.
-- Avoids schema confusion (locked_at lives on locked_picks, not pick_results).
CREATE OR REPLACE VIEW public.v_recent_locked_picks AS
SELECT
  lp.id,
  lp.event_id,
  lp.sport,
  lp.league,
  lp.market,
  lp.side,
  lp.tier,
  lp.score,
  lp.confidence,
  lp.selection_team,
  lp.home_team,
  lp.away_team,
  lp.game_start_time,
  lp.locked_at,
  lp.run_date,
  lp.graded_at,
  lp.locked_ml_home,
  lp.locked_ml_away
FROM locked_picks lp
WHERE lp.locked_at > now() - interval '7 days'
ORDER BY lp.locked_at DESC;

-- v_recent_pick_results: canonical view for graded pick results.
-- Uses start_time and graded_at (pick_results has NO locked_at column).
CREATE OR REPLACE VIEW public.v_recent_pick_results AS
SELECT
  pr.id,
  pr.locked_pick_id,
  pr.event_id,
  pr.sport,
  pr.tier,
  pr.confidence,
  pr.result,
  pr.units,
  pr.home_team,
  pr.away_team,
  pr.selection_team,
  pr.home_score,
  pr.away_score,
  pr.start_time,
  pr.graded_at,
  pr.run_date
FROM pick_results pr
WHERE pr.start_time > now() - interval '7 days'
  AND pr.result IN ('win', 'loss', 'push')
ORDER BY pr.graded_at DESC;

-- v_snapshot_density: per-event snapshot counts for CLV health monitoring.
CREATE OR REPLACE VIEW public.v_snapshot_density AS
SELECT
  event_id,
  home_team,
  away_team,
  commence_time,
  COUNT(*) AS snap_count,
  COUNT(DISTINCT captured_minute) AS distinct_minutes,
  MIN(captured_at) AS first_snap,
  MAX(captured_at) AS last_snap,
  EXTRACT(EPOCH FROM MAX(captured_at) - MIN(captured_at)) / 60 AS span_minutes
FROM closing_lines
WHERE captured_at > now() - interval '24 hours'
  AND sport = 'nba'
  AND market = 'h2h'
GROUP BY event_id, home_team, away_team, commence_time
ORDER BY commence_time DESC;

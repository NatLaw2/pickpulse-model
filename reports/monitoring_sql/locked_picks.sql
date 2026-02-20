-- ==========================================================================
-- Locked Picks Monitoring Queries
-- ==========================================================================
-- Use these in the Supabase SQL Editor for pipeline health checks.
-- NOTE: pick_results does NOT have a locked_at column.
--       Use locked_picks.locked_at or pick_results.graded_at / start_time.
-- ==========================================================================

-- 1. Recent locked picks (via canonical view)
SELECT * FROM v_recent_locked_picks LIMIT 20;

-- 2. Recent graded results (via canonical view)
SELECT * FROM v_recent_pick_results LIMIT 20;

-- 3. Snapshot density for CLV (via canonical view)
SELECT * FROM v_snapshot_density;

-- 4. Ungraded picks (games finished but not yet graded)
SELECT id, event_id, tier, confidence, game_start_time, locked_at
FROM locked_picks
WHERE graded_at IS NULL
  AND game_start_time < now()
ORDER BY game_start_time DESC;

-- 5. Today's locked picks with odds
SELECT
  run_date, tier, market, selection_team,
  score, confidence,
  locked_ml_home, locked_ml_away,
  game_start_time, locked_at
FROM locked_picks
WHERE run_date = current_date
ORDER BY locked_at DESC;

-- 6. Performance by confidence bucket (last 30 days)
SELECT
  CASE
    WHEN tier = 'top_pick' OR confidence >= 0.80 THEN 'Top'
    WHEN tier = 'strong_lean' OR confidence >= 0.65 THEN 'High'
    ELSE 'Medium'
  END AS bucket,
  COUNT(*) FILTER (WHERE result = 'win') AS wins,
  COUNT(*) FILTER (WHERE result = 'loss') AS losses,
  COUNT(*) AS picks,
  ROUND(100.0 * COUNT(*) FILTER (WHERE result = 'win') / NULLIF(COUNT(*), 0), 1) AS win_pct,
  ROUND(SUM(units)::numeric, 2) AS total_units
FROM pick_results
WHERE start_time > now() - interval '30 days'
  AND result IN ('win', 'loss', 'push')
GROUP BY 1
ORDER BY 1;

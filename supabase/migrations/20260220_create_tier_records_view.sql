-- ==========================================================================
-- v_tier_records: canonical aggregated view of performance by tier bucket.
--
-- Returns one row per (tier_bucket, source) with lifetime stats.
-- For time-filtered queries, use the performance-summary edge function
-- or query pick_results directly with PostgREST filters.
--
-- Tier mapping:
--   top_pick     → 'top'
--   strong_lean  → 'high'
--   watchlist    → 'medium'
-- ==========================================================================

CREATE OR REPLACE VIEW public.v_tier_records AS
SELECT
  CASE
    WHEN tier = 'top_pick'    THEN 'top'
    WHEN tier = 'strong_lean' THEN 'high'
    WHEN tier = 'watchlist'   THEN 'medium'
  END AS tier_bucket,
  source,
  COUNT(*) FILTER (WHERE result = 'win')  AS wins,
  COUNT(*) FILTER (WHERE result = 'loss') AS losses,
  COUNT(*) FILTER (WHERE result = 'push') AS pushes,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE result = 'win')
    / NULLIF(COUNT(*) FILTER (WHERE result IN ('win', 'loss')), 0),
    1
  ) AS win_pct,
  ROUND(COALESCE(SUM(units), 0)::numeric, 2) AS units,
  MAX(graded_at) AS updated_at
FROM pick_results
WHERE result IN ('win', 'loss', 'push')
  AND tier IN ('top_pick', 'strong_lean', 'watchlist')
GROUP BY 1, 2
ORDER BY 1, 2;

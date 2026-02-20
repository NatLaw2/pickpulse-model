# PickPulse NBA Pipeline — Debug Reference

## Data Flow

```
Odds API (every 2 min)
    |
    v
snap_odds_nba_near_tip  -->  closing_lines  (T-90 to T-0 snapshots)
    |
    v
lock_picks_tminus15     -->  locked_picks   (T-15 before tip)
  (calls slate-with-picks -> model API -> events table)
    |
    v
[Game happens]
    |
    v
final_nba               -->  game_results   (scores + closing odds)
  (Odds API /scores)
    |
    v
capture_closing_nba     -->  game_results   (patches closing_ml/spread)
  (reads closing_lines)
    |
    v
grade_picks             -->  pick_results   (win/loss/push + units)
  (locked_picks x game_results)
    |
    v
performance-summary     <--  pick_results   (API for frontend)
    |
    v
[Frontend: PerformancePage.tsx]
```

## Tables

| Table | Written by | Key columns |
|-------|-----------|-------------|
| `closing_lines` | snap_odds_nba_near_tip, backfill_close_nba | event_id, captured_at, market, price, point |
| `events` | slate-with-picks | event_id, start_time, home_team, away_team |
| `locked_picks` | lock_picks_tminus15 | event_id, tier, score, confidence, locked_at, locked_ml_*, graded_at |
| `game_results` | final_nba, capture_closing_nba | event_id, home_score, away_score, closing_ml_* |
| `pick_results` | grade_picks | locked_pick_id, result, units, tier, confidence, graded_at |

## Cron Jobs (pg_cron via net.http_post)

| Job | Schedule | Function | Purpose |
|-----|----------|----------|---------|
| snap-odds-nba-2min | */2 * * * * | snap_odds_nba_near_tip | Odds snapshots |
| lock-picks-tminus15-5min | */5 * * * * | lock_picks_tminus15 | Lock at T-15 |
| capture-closing-nba-5min | */5 * * * * | capture_closing_nba | Backfill closing odds |
| grade-picks-5min | */5 * * * * | grade_picks | Grade locked picks |
| final-nba-5min | */5 * * * * | final_nba | Fetch final scores |

## Common Failures

1. **"Character with value 0x0a must be escaped"**: Newline in JWT inside cron header JSON. Fix: use `jsonb_build_object()` in cron command.
2. **Locked picks = 0**: Cron not firing (see above), or no games in T-15 window.
3. **Performance not updating**: `final_nba` not running → no scores in `game_results` → `grade_picks` can't grade.
4. **CLV = 0**: Only 1 daily backfill snapshot per event. Need near-tip snapshots from `snap_odds_nba_near_tip`.

## Tier / Confidence Mapping

| Tier | Score Range | Confidence Bucket |
|------|------------|-------------------|
| top_pick | >= 74 | Top (>= 0.80) |
| strong_lean | 66–73 | High (0.65–0.80) |
| watchlist | 65 | Medium (0.55–0.65) |

## Verification Queries

```sql
-- Cron jobs
SELECT jobname, schedule, active FROM cron.job ORDER BY jobname;

-- Recent cron failures
SELECT jobname, status, return_message, start_time
FROM cron.job_run_details
WHERE start_time > now() - interval '1 hour'
ORDER BY start_time DESC LIMIT 20;

-- Locked picks today
SELECT * FROM locked_picks WHERE run_date = current_date ORDER BY locked_at DESC;

-- Ungraded picks
SELECT id, event_id, game_start_time, graded_at
FROM locked_picks WHERE graded_at IS NULL AND game_start_time < now();

-- Snapshot density
SELECT event_id, COUNT(*) snaps, MIN(captured_at) first, MAX(captured_at) last
FROM closing_lines WHERE captured_at > now() - interval '24 hours'
GROUP BY event_id ORDER BY MAX(commence_time) DESC;
```

/// <reference lib="deno.ns" />
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

/**
 * grade_picks
 *
 * Joins locked_picks with game_results, computes outcome + units using
 * locked odds, and writes to pick_results.
 *
 * Idempotent: uses upsert on (locked_pick_id) so re-running is safe.
 *
 * Designed to run every 5-10 minutes via cron.
 *
 * Required env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

const VERSION = "grade_picks@2026-02-17_v1";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getEnv(name: string): string {
  const v = Deno.env.get(name);
  if (!v) throw new Error(`Missing env var: ${name}`);
  return v;
}

function json(res: unknown, status = 200) {
  return new Response(JSON.stringify(res), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

/**
 * Convert American odds to profit per 1 unit staked.
 * +150 => 1.5, -200 => 0.5
 */
function americanProfitPer1u(odds: number): number {
  if (odds >= 100) return odds / 100;
  if (odds <= -100) return 100 / Math.abs(odds);
  return 0;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LockedPick = {
  id: string;
  event_id: string;
  sport: string;
  league: string;
  market: string;
  side: string;
  tier: string;
  score: number;
  confidence: number;
  why: string[];
  game_start_time: string;
  locked_at: string;
  run_date: string;
  source: string;
  home_team: string | null;
  away_team: string | null;
  selection_team: string | null;
  bookmaker_key: string | null;
  locked_ml_home: number | null;
  locked_ml_away: number | null;
  locked_spread_home_point: number | null;
  locked_spread_home_price: number | null;
  locked_spread_away_point: number | null;
  locked_spread_away_price: number | null;
};

type GameResult = {
  event_id: string;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
};

// ---------------------------------------------------------------------------
// Grading logic
// ---------------------------------------------------------------------------

function gradeMoneyline(
  pick: LockedPick,
  result: GameResult,
): { outcome: "win" | "loss" | "push"; units: number } | null {
  if (result.home_score === null || result.away_score === null) return null;

  const selTeam = pick.selection_team;
  if (!selTeam) return null;

  const homeWon = result.home_score > result.away_score;
  const awayWon = result.away_score > result.home_score;
  const tie = result.home_score === result.away_score;

  if (tie) return { outcome: "push", units: 0 };

  // Determine if picked team won
  const pickedHome = selTeam === result.home_team;
  const pickedAway = selTeam === result.away_team;

  if (!pickedHome && !pickedAway) {
    // Fuzzy match: check if selection_team is a substring
    const selLower = selTeam.toLowerCase();
    const homeLower = result.home_team.toLowerCase();
    const awayLower = result.away_team.toLowerCase();

    if (homeLower.includes(selLower) || selLower.includes(homeLower)) {
      return gradeMLResult(homeWon, pick.locked_ml_home);
    }
    if (awayLower.includes(selLower) || selLower.includes(awayLower)) {
      return gradeMLResult(awayWon, pick.locked_ml_away);
    }

    return null; // Can't determine team
  }

  if (pickedHome) return gradeMLResult(homeWon, pick.locked_ml_home);
  if (pickedAway) return gradeMLResult(awayWon, pick.locked_ml_away);

  return null;
}

function gradeMLResult(
  teamWon: boolean,
  lockedOdds: number | null,
): { outcome: "win" | "loss"; units: number } {
  if (teamWon) {
    const profit = lockedOdds !== null ? americanProfitPer1u(lockedOdds) : 1;
    return { outcome: "win", units: profit };
  } else {
    return { outcome: "loss", units: -1 };
  }
}

function gradeSpread(
  pick: LockedPick,
  result: GameResult,
): { outcome: "win" | "loss" | "push"; units: number } | null {
  if (result.home_score === null || result.away_score === null) return null;

  const selTeam = pick.selection_team;
  if (!selTeam) return null;

  // Determine which side was picked
  let spreadPoint: number | null = null;
  let spreadPrice: number | null = null;

  const selLower = selTeam.toLowerCase();
  const homeLower = result.home_team.toLowerCase();
  const awayLower = result.away_team.toLowerCase();

  const isHome =
    selTeam === result.home_team ||
    homeLower.includes(selLower) ||
    selLower.includes(homeLower);
  const isAway =
    selTeam === result.away_team ||
    awayLower.includes(selLower) ||
    selLower.includes(awayLower);

  if (isHome) {
    spreadPoint = pick.locked_spread_home_point;
    spreadPrice = pick.locked_spread_home_price;
  } else if (isAway) {
    spreadPoint = pick.locked_spread_away_point;
    spreadPrice = pick.locked_spread_away_price;
  }

  if (spreadPoint === null) return null;

  // Margin for picked team
  const margin = isHome
    ? result.home_score - result.away_score
    : result.away_score - result.home_score;

  const adjusted = margin + spreadPoint;

  if (adjusted === 0) return { outcome: "push", units: 0 };

  if (adjusted > 0) {
    const profit = spreadPrice !== null ? americanProfitPer1u(spreadPrice) : 1;
    return { outcome: "win", units: profit };
  } else {
    return { outcome: "loss", units: -1 };
  }
}

function gradePick(
  pick: LockedPick,
  result: GameResult,
): { outcome: "win" | "loss" | "push"; units: number } | null {
  if (pick.market === "moneyline") return gradeMoneyline(pick, result);
  if (pick.market === "spread") return gradeSpread(pick, result);
  // total not yet supported
  return null;
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const SUPABASE_URL = getEnv("SUPABASE_URL");
    const SERVICE_ROLE_KEY = getEnv("SUPABASE_SERVICE_ROLE_KEY");

    const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
      auth: { persistSession: false },
    });

    // Step 1: Find locked picks that haven't been graded yet
    // We look for locked_picks where the game has started (game_start_time < now)
    // and no corresponding pick_results row exists
    const now = new Date();

    const { data: ungradedPicks, error: pickErr } = await supabase
      .from("locked_picks")
      .select("*")
      .eq("sport", "nba")
      .lt("game_start_time", now.toISOString())
      .is("graded_at", null)
      .limit(500);

    if (pickErr) throw new Error(`locked_picks fetch failed: ${pickErr.message}`);

    const picks = (ungradedPicks ?? []) as LockedPick[];

    if (picks.length === 0) {
      return json({
        ok: true,
        version: VERSION,
        message: "No ungraded picks found",
        now: now.toISOString(),
        checked: 0,
        graded: 0,
      });
    }

    // Step 2: Fetch game_results for these events
    const eventIds = [...new Set(picks.map((p) => p.event_id))];

    const { data: resultRows, error: resErr } = await supabase
      .from("game_results")
      .select("event_id,home_team,away_team,home_score,away_score")
      .eq("sport", "nba")
      .in("event_id", eventIds);

    if (resErr) throw new Error(`game_results fetch failed: ${resErr.message}`);

    const resultsMap = new Map<string, GameResult>();
    for (const r of (resultRows ?? []) as GameResult[]) {
      // Only include if scores are available (game is final)
      if (r.home_score !== null && r.away_score !== null) {
        resultsMap.set(r.event_id, r);
      }
    }

    // Step 3: Grade each pick
    let graded = 0;
    let skipped = 0;
    let noResult = 0;

    for (const pick of picks) {
      const result = resultsMap.get(pick.event_id);
      if (!result) {
        noResult++;
        continue;
      }

      const grade = gradePick(pick, result);
      if (!grade) {
        skipped++;
        continue;
      }

      // Step 4: Upsert to pick_results
      const pickResult = {
        locked_pick_id: pick.id,
        event_id: pick.event_id,
        sport: pick.sport,
        league: pick.league,
        market: pick.market,
        side: pick.side,
        tier: pick.tier,
        score: pick.score,
        confidence: pick.confidence,
        source: pick.source,
        run_date: pick.run_date,
        start_time: pick.game_start_time,
        home_team: pick.home_team,
        away_team: pick.away_team,
        selection_team: pick.selection_team,
        result: grade.outcome,
        units: grade.units,
        locked_ml_home: pick.locked_ml_home,
        locked_ml_away: pick.locked_ml_away,
        locked_spread_home_point: pick.locked_spread_home_point,
        locked_spread_home_price: pick.locked_spread_home_price,
        locked_spread_away_point: pick.locked_spread_away_point,
        locked_spread_away_price: pick.locked_spread_away_price,
        home_score: result.home_score,
        away_score: result.away_score,
        graded_at: now.toISOString(),
      };

      const { error: upsertErr } = await supabase
        .from("pick_results")
        .upsert(pickResult, {
          onConflict: "locked_pick_id",
        });

      if (upsertErr) {
        console.error(`[grade_picks] pick_results upsert failed for ${pick.id}: ${upsertErr.message}`);
        skipped++;
        continue;
      }

      // Mark locked_pick as graded
      const { error: updateErr } = await supabase
        .from("locked_picks")
        .update({ graded_at: now.toISOString() })
        .eq("id", pick.id);

      if (updateErr) {
        console.error(`[grade_picks] locked_picks update failed for ${pick.id}: ${updateErr.message}`);
      }

      graded++;
    }

    return json({
      ok: true,
      version: VERSION,
      now: now.toISOString(),
      picks_checked: picks.length,
      events_with_scores: resultsMap.size,
      graded,
      skipped,
      no_result_yet: noResult,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[grade_picks] error: ${msg}`);
    return json({ ok: false, error: msg }, 500);
  }
});

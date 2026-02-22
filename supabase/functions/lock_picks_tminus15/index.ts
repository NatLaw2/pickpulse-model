/// <reference lib="deno.ns" />
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

/**
 * lock_picks_tminus15  v2
 *
 * Locks picks at T-15 minutes before NBA game starts.
 *
 * Flow:
 *   1. Call slate-with-picks?day=today to get model predictions + odds
 *   2. Filter to games in [now+10m, now+20m]  (T-15 ± 5 min buffer)
 *   3. For each qualifying market (score >= 65), build a locked pick row
 *   4. Look up current odds from closing_lines for locked odds
 *   5. Enforce single daily Top Pick (highest score for the day)
 *   6. Upsert to locked_picks  (idempotent on run_date + event_id + market)
 *
 * Query params:
 *   dry_run=1  – runs full logic but does NOT write; returns would-be rows
 *
 * Designed to run every 5 minutes via cron.
 * Deploy with --no-verify-jwt so cron can invoke without auth header.
 *
 * Required env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

const VERSION = "lock_picks_tminus15@2026-02-22_v2";
const RUN_TZ = "America/Chicago";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

// ---------------------------------------------------------------------------
// Thresholds
// ---------------------------------------------------------------------------

const MIN_SCORE = 65;

const THRESHOLDS = {
  TOP_PICK_MIN_SCORE: 74,
  STRONG_LEAN_MIN_SCORE: 66,
  WATCHLIST_MIN_SCORE: 65,
};

function tierForScore(score: number): "top_pick" | "strong_lean" | "watchlist" | null {
  if (score >= THRESHOLDS.TOP_PICK_MIN_SCORE) return "top_pick";
  if (score >= THRESHOLDS.STRONG_LEAN_MIN_SCORE) return "strong_lean";
  if (score >= THRESHOLDS.WATCHLIST_MIN_SCORE) return "watchlist";
  return null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getEnv(name: string): string {
  const v = Deno.env.get(name);
  if (!v) throw new Error(`Missing env var: ${name}`);
  return v;
}

function jsonResp(res: unknown, status = 200) {
  return new Response(JSON.stringify(res, null, 2), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

function ymdInTZ(d: Date, tz: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);

  const y = parts.find((p) => p.type === "year")?.value ?? "1970";
  const m = parts.find((p) => p.type === "month")?.value ?? "01";
  const da = parts.find((p) => p.type === "day")?.value ?? "01";
  return `${y}-${m}-${da}`;
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

// ---------------------------------------------------------------------------
// Types from slate-with-picks
// ---------------------------------------------------------------------------

type SlatePickOut = {
  status: "pick" | "no_bet";
  selection?: string;
  score?: number;
  rationale?: string[];
  good_bet_prob?: number;
};

type SlateTeam = { name?: string; abbreviation?: string };

type SlateGame = {
  id: string;
  sport: string;
  startTime: string;
  homeTeam?: SlateTeam;
  awayTeam?: SlateTeam;
  picks: {
    moneyline: SlatePickOut;
    spread: SlatePickOut;
    total: SlatePickOut;
  };
};

type Candidate = {
  event_id: string;
  sport: string;
  start_time: string;
  market: "moneyline" | "spread" | "total";
  side: string;
  score: number;
  confidence: number;
  why: string[];
  home_team: string | null;
  away_team: string | null;
  selection_team: string | null;
};

// ---------------------------------------------------------------------------
// Summary object  (returned in every response)
// ---------------------------------------------------------------------------

type Summary = {
  version: string;
  dry_run: boolean;
  now_utc: string;
  run_date: string;
  target_window_start_utc: string;
  target_window_end_utc: string;
  candidate_games_total: number;       // games returned by slate-with-picks
  games_in_window: number;             // games inside T-15 window
  games_missing_odds: number;          // games where closing_lines had no odds
  games_with_odds: number;             // games where we found locked odds
  picks_built_total: number;           // total picks passing score threshold
  picks_by_tier: { top: number; high: number; medium: number };
  already_locked: number;              // picks already in locked_picks today
  insert_attempted: number;
  inserted_rows: number;
  any_error: string | null;
};

function emptySummary(now: Date, runDate: string, windowStart: Date, windowEnd: Date, dryRun: boolean): Summary {
  return {
    version: VERSION,
    dry_run: dryRun,
    now_utc: now.toISOString(),
    run_date: runDate,
    target_window_start_utc: windowStart.toISOString(),
    target_window_end_utc: windowEnd.toISOString(),
    candidate_games_total: 0,
    games_in_window: 0,
    games_missing_odds: 0,
    games_with_odds: 0,
    picks_built_total: 0,
    picks_by_tier: { top: 0, high: 0, medium: 0 },
    already_locked: 0,
    insert_attempted: 0,
    inserted_rows: 0,
    any_error: null,
  };
}

// ---------------------------------------------------------------------------
// Slate extraction
// ---------------------------------------------------------------------------

function teamDisplayName(team?: SlateTeam): string | null {
  const name = team?.name?.trim();
  if (name) return name;
  const abbr = team?.abbreviation?.trim();
  if (abbr) return abbr;
  return null;
}

function deriveSelectionTeam(params: {
  market: string;
  selection: string;
  homeName: string | null;
  awayName: string | null;
  homeAbbr: string | null;
  awayAbbr: string | null;
}): string | null {
  const { market, selection, homeName, awayName, homeAbbr, awayAbbr } = params;
  if (market === "total") return null;

  const sel = (selection || "").trim();
  if (!sel) return null;

  const firstToken = sel.split(/\s+/)[0]?.toUpperCase() ?? "";

  if (homeAbbr && firstToken === homeAbbr.toUpperCase()) return homeName;
  if (awayAbbr && firstToken === awayAbbr.toUpperCase()) return awayName;

  const lower = sel.toLowerCase();
  if (homeName && lower.includes(homeName.toLowerCase())) return homeName;
  if (awayName && lower.includes(awayName.toLowerCase())) return awayName;

  return null;
}

async function fetchSlateWithPicks(day: string): Promise<Record<string, SlateGame[]>> {
  const supabaseUrl = Deno.env.get("PP_SUPABASE_URL") || Deno.env.get("SUPABASE_URL");
  const serviceRole =
    Deno.env.get("PP_SERVICE_ROLE_KEY") ||
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ||
    Deno.env.get("SERVICE_ROLE_KEY");

  if (!supabaseUrl) throw new Error("Missing SUPABASE_URL");
  if (!serviceRole) throw new Error("Missing SUPABASE_SERVICE_ROLE_KEY");

  const url = `${supabaseUrl}/functions/v1/slate-with-picks?day=${encodeURIComponent(day)}`;

  const res = await fetch(url, {
    method: "GET",
    headers: {
      apikey: serviceRole,
      authorization: `Bearer ${serviceRole}`,
      "content-type": "application/json",
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`slate-with-picks failed: ${res.status} ${text}`);
  }

  return await res.json();
}

/**
 * Extract ALL qualifying candidates (not just best-per-game).
 * Returns one candidate per (event, market) that passes score >= MIN_SCORE.
 */
function extractCandidates(
  rawSlate: Record<string, SlateGame[]>,
  windowStart: Date,
  windowEnd: Date,
): { candidates: Candidate[]; totalGames: number; gamesInWindow: number } {
  const candidates: Candidate[] = [];
  let totalGames = 0;
  let gamesInWindow = 0;

  for (const sportKey of Object.keys(rawSlate || {})) {
    if (sportKey === "topPicks") continue;
    if (sportKey !== "nba") continue; // NBA only for now

    const games = rawSlate[sportKey] || [];
    totalGames += games.length;

    for (const game of games) {
      const st = new Date(game.startTime);
      if (Number.isNaN(st.getTime())) continue;

      // Hard guard: never lock a game that has already started
      const rightNow = new Date();
      if (st <= rightNow) continue;
      if (st < windowStart || st > windowEnd) continue;

      gamesInWindow++;

      const homeName = teamDisplayName(game?.homeTeam);
      const awayName = teamDisplayName(game?.awayTeam);
      const homeAbbr = game?.homeTeam?.abbreviation?.trim() ?? null;
      const awayAbbr = game?.awayTeam?.abbreviation?.trim() ?? null;

      const markets: Array<"moneyline" | "spread" | "total"> = ["moneyline", "spread", "total"];

      for (const m of markets) {
        const pick = game?.picks?.[m];
        if (!pick || pick.status !== "pick" || !pick.selection) continue;
        if (typeof pick.score !== "number") continue;

        const score = clamp(pick.score, 0, 100);
        if (score < MIN_SCORE) continue;

        const confidence = (pick.good_bet_prob !== undefined && pick.good_bet_prob !== null)
          ? pick.good_bet_prob
          : score / 100;

        const selection_team = deriveSelectionTeam({
          market: m,
          selection: pick.selection,
          homeName,
          awayName,
          homeAbbr,
          awayAbbr,
        });

        candidates.push({
          event_id: game.id,
          sport: sportKey,
          start_time: game.startTime,
          market: m,
          side: pick.selection,
          score,
          confidence,
          why: Array.isArray(pick.rationale) ? pick.rationale.slice(0, 5) : [],
          home_team: homeName,
          away_team: awayName,
          selection_team,
        });
      }
    }
  }

  return { candidates, totalGames, gamesInWindow };
}

// ---------------------------------------------------------------------------
// Fetch current odds from closing_lines for locked odds
// ---------------------------------------------------------------------------

async function fetchCurrentOdds(
  supabase: ReturnType<typeof createClient>,
  eventId: string,
  bookmakerKey: string,
): Promise<{
  locked_ml_home: number | null;
  locked_ml_away: number | null;
  locked_spread_home_point: number | null;
  locked_spread_home_price: number | null;
  locked_spread_away_point: number | null;
  locked_spread_away_price: number | null;
  _odds_found: boolean;
}> {
  const result = {
    locked_ml_home: null as number | null,
    locked_ml_away: null as number | null,
    locked_spread_home_point: null as number | null,
    locked_spread_home_price: null as number | null,
    locked_spread_away_point: null as number | null,
    locked_spread_away_price: null as number | null,
    _odds_found: false,
  };

  const { data, error } = await supabase
    .from("closing_lines")
    .select("market,outcome_name,price,point,home_team,away_team")
    .eq("sport", "nba")
    .eq("event_id", eventId)
    .eq("bookmaker_key", bookmakerKey)
    .order("captured_at", { ascending: false })
    .limit(20);

  if (error || !data || data.length === 0) return result;

  result._odds_found = true;

  // Take the latest captured_at group
  const latestRow = data[0];
  const homeTeam = latestRow.home_team;
  const awayTeam = latestRow.away_team;

  for (const r of data as any[]) {
    if (!r.market || !r.outcome_name) continue;

    if (r.market === "h2h") {
      if (r.outcome_name === homeTeam && result.locked_ml_home === null)
        result.locked_ml_home = r.price;
      if (r.outcome_name === awayTeam && result.locked_ml_away === null)
        result.locked_ml_away = r.price;
    }
    if (r.market === "spreads") {
      if (r.outcome_name === homeTeam && result.locked_spread_home_point === null) {
        result.locked_spread_home_point = r.point;
        result.locked_spread_home_price = r.price;
      }
      if (r.outcome_name === awayTeam && result.locked_spread_away_point === null) {
        result.locked_spread_away_point = r.point;
        result.locked_spread_away_price = r.price;
      }
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  const now = new Date();
  const runDate = ymdInTZ(now, RUN_TZ);

  // T-15 window: games starting in [now+10m, now+20m]
  // Wider than before (was ±2 min) so a 5-minute cron cadence ALWAYS catches every game.
  const windowStartMs = now.getTime() + 10 * 60 * 1000;
  const windowEndMs = now.getTime() + 20 * 60 * 1000;
  const windowStart = new Date(windowStartMs);
  const windowEnd = new Date(windowEndMs);

  // Parse query params
  const reqUrl = new URL(req.url);
  const dryRun = reqUrl.searchParams.get("dry_run") === "1";

  const summary = emptySummary(now, runDate, windowStart, windowEnd, dryRun);

  try {
    const SUPABASE_URL = getEnv("SUPABASE_URL");
    const SERVICE_ROLE_KEY = getEnv("SUPABASE_SERVICE_ROLE_KEY");
    const bookmakerKey = (Deno.env.get("PREFERRED_BOOKMAKER") ?? "fanduel").toLowerCase();

    const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
      auth: { persistSession: false },
    });

    // -----------------------------------------------------------------------
    // Step 1: Fetch predictions from slate-with-picks
    // -----------------------------------------------------------------------
    const rawSlate = await fetchSlateWithPicks("today");

    // -----------------------------------------------------------------------
    // Step 2: Extract candidates in the T-15 window with score >= 65
    // -----------------------------------------------------------------------
    const { candidates, totalGames, gamesInWindow } = extractCandidates(rawSlate, windowStart, windowEnd);

    summary.candidate_games_total = totalGames;
    summary.games_in_window = gamesInWindow;
    summary.picks_built_total = candidates.length;

    if (candidates.length === 0) {
      return jsonResp({ ok: true, summary });
    }

    // -----------------------------------------------------------------------
    // Step 3: Check which (event_id, market) combos are already locked today
    // -----------------------------------------------------------------------
    const eventIds = [...new Set(candidates.map((c) => c.event_id))];
    const { data: existingRows, error: existErr } = await supabase
      .from("locked_picks")
      .select("event_id,market")
      .eq("run_date", runDate)
      .in("event_id", eventIds);

    if (existErr) throw new Error(`locked_picks check failed: ${existErr.message}`);

    const alreadyLockedSet = new Set(
      (existingRows ?? []).map((r: any) => `${r.event_id}::${r.market}`),
    );
    const newCandidates = candidates.filter(
      (c) => !alreadyLockedSet.has(`${c.event_id}::${c.market}`),
    );
    summary.already_locked = alreadyLockedSet.size;

    if (newCandidates.length === 0) {
      return jsonResp({ ok: true, summary });
    }

    // -----------------------------------------------------------------------
    // Step 4: Enforce single daily Top Pick
    // -----------------------------------------------------------------------
    const { data: existingTopPick, error: topErr } = await supabase
      .from("locked_picks")
      .select("id")
      .eq("run_date", runDate)
      .eq("tier", "top_pick")
      .limit(1);

    if (topErr) throw new Error(`top_pick check failed: ${topErr.message}`);

    const hasTopPickToday = (existingTopPick ?? []).length > 0;

    // Sort by score descending so highest score gets top_pick
    newCandidates.sort((a, b) => b.score - a.score);

    // -----------------------------------------------------------------------
    // Step 5: Build insert rows with locked odds
    // -----------------------------------------------------------------------
    const inserts: Record<string, unknown>[] = [];
    let topPickAssigned = hasTopPickToday;
    let gamesMissingOdds = 0;
    let gamesWithOdds = 0;
    const oddsCache = new Map<string, Awaited<ReturnType<typeof fetchCurrentOdds>>>();

    for (const c of newCandidates) {
      const tier = tierForScore(c.score);
      if (!tier) continue;

      // Tier assignment
      let finalTier = tier;
      if (tier === "top_pick") {
        if (topPickAssigned) {
          finalTier = "strong_lean";
        } else {
          topPickAssigned = true;
        }
      }

      // Count by tier for summary
      if (finalTier === "top_pick") summary.picks_by_tier.top++;
      else if (finalTier === "strong_lean") summary.picks_by_tier.high++;
      else if (finalTier === "watchlist") summary.picks_by_tier.medium++;

      // Fetch locked odds (cache per event to avoid duplicate API calls)
      let lockedOdds = oddsCache.get(c.event_id);
      if (!lockedOdds) {
        lockedOdds = await fetchCurrentOdds(supabase, c.event_id, bookmakerKey);
        oddsCache.set(c.event_id, lockedOdds);
      }

      if (lockedOdds._odds_found) gamesWithOdds++;
      else gamesMissingOdds++;

      const { _odds_found, ...oddsFields } = lockedOdds;

      inserts.push({
        event_id: c.event_id,
        sport: c.sport,
        league: "NBA",
        market: c.market,
        side: c.side,
        tier: finalTier,
        score: c.score,
        confidence: c.confidence,
        why: c.why,
        game_start_time: c.start_time,
        locked_at: now.toISOString(),
        run_date: runDate,
        source: "live",
        home_team: c.home_team,
        away_team: c.away_team,
        selection_team: c.selection_team,
        bookmaker_key: bookmakerKey,
        ...oddsFields,
      });
    }

    summary.games_missing_odds = gamesMissingOdds;
    summary.games_with_odds = gamesWithOdds;

    if (inserts.length === 0) {
      return jsonResp({ ok: true, summary });
    }

    summary.insert_attempted = inserts.length;

    // -----------------------------------------------------------------------
    // Step 6: dry_run → return rows without writing
    // -----------------------------------------------------------------------
    if (dryRun) {
      return jsonResp({
        ok: true,
        summary,
        would_lock: inserts.map((row) => ({
          event_id: row.event_id,
          tier: row.tier,
          market: row.market,
          side: row.side,
          selection_team: row.selection_team,
          confidence: row.confidence,
          score: row.score,
          locked_ml_home: row.locked_ml_home,
          locked_ml_away: row.locked_ml_away,
          game_start_time: row.game_start_time,
          home_team: row.home_team,
          away_team: row.away_team,
        })),
      });
    }

    // -----------------------------------------------------------------------
    // Step 7: Upsert to locked_picks
    // Conflict on (run_date, event_id, market) — re-lock attempts no-op.
    // -----------------------------------------------------------------------
    const { data: upsertedData, error: insErr, count } = await supabase
      .from("locked_picks")
      .upsert(inserts, {
        onConflict: "run_date,event_id,market",
        ignoreDuplicates: true,
        count: "exact",
      });

    if (insErr) {
      summary.any_error = `locked_picks upsert failed: ${insErr.message}`;
      console.error(`[lock_picks_tminus15] ${summary.any_error}`);
      return jsonResp({ ok: false, summary }, 500);
    }

    summary.inserted_rows = count ?? inserts.length;

    return jsonResp({ ok: true, summary });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    summary.any_error = msg;
    console.error(`[lock_picks_tminus15] error: ${msg}`);
    return jsonResp({ ok: false, summary }, 500);
  }
});

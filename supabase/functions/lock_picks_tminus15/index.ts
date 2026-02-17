/// <reference lib="deno.ns" />
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

/**
 * lock_picks_tminus15
 *
 * Locks picks exactly at T-15 minutes before game start.
 * - Finds NBA games starting in [now+10m, now+20m]
 * - Calls slate-with-picks to get model predictions
 * - Filters score >= 65
 * - Looks up current odds from closing_lines to store as locked odds
 * - Enforces exactly ONE daily Top Pick (highest score for the day)
 * - Writes to locked_picks table (new table, separate from pick_snapshots)
 *
 * Designed to run every 5 minutes via cron.
 *
 * Required env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

const VERSION = "lock_picks_tminus15@2026-02-17_v1";
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

function json(res: unknown, status = 200) {
  return new Response(JSON.stringify(res), {
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
// Slate extraction (mirrors lock-picks-at-start patterns)
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

function extractCandidates(
  rawSlate: Record<string, SlateGame[]>,
  windowStart: Date,
  windowEnd: Date,
): Candidate[] {
  const candidates: Candidate[] = [];

  for (const sportKey of Object.keys(rawSlate || {})) {
    if (sportKey === "topPicks") continue;
    if (sportKey !== "nba") continue; // NBA only

    const games = rawSlate[sportKey] || [];

    for (const game of games) {
      const st = new Date(game.startTime);
      if (st < windowStart || st > windowEnd) continue;

      const homeName = teamDisplayName(game?.homeTeam);
      const awayName = teamDisplayName(game?.awayTeam);
      const homeAbbr = game?.homeTeam?.abbreviation?.trim() ?? null;
      const awayAbbr = game?.awayTeam?.abbreviation?.trim() ?? null;

      const markets: Array<"moneyline" | "spread" | "total"> = ["moneyline", "spread", "total"];
      let bestForGame: Candidate | null = null;

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

        const cand: Candidate = {
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
        };

        // Keep best market per game (highest score)
        if (!bestForGame || cand.score > bestForGame.score) {
          bestForGame = cand;
        }
      }

      if (bestForGame) candidates.push(bestForGame);
    }
  }

  return candidates;
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
}> {
  const defaults = {
    locked_ml_home: null,
    locked_ml_away: null,
    locked_spread_home_point: null,
    locked_spread_home_price: null,
    locked_spread_away_point: null,
    locked_spread_away_price: null,
  };

  const { data, error } = await supabase
    .from("closing_lines")
    .select("market,outcome_name,price,point,home_team,away_team")
    .eq("sport", "nba")
    .eq("event_id", eventId)
    .eq("bookmaker_key", bookmakerKey)
    .order("captured_at", { ascending: false })
    .limit(20);

  if (error || !data || data.length === 0) return defaults;

  // Take the latest captured_at group (all rows share the same captured_at since ordered desc)
  const latestCaptured = data[0];
  const homeTeam = latestCaptured.home_team;
  const awayTeam = latestCaptured.away_team;

  for (const r of data as any[]) {
    if (!r.market || !r.outcome_name) continue;

    if (r.market === "h2h") {
      if (r.outcome_name === homeTeam && defaults.locked_ml_home === null)
        defaults.locked_ml_home = r.price;
      if (r.outcome_name === awayTeam && defaults.locked_ml_away === null)
        defaults.locked_ml_away = r.price;
    }
    if (r.market === "spreads") {
      if (r.outcome_name === homeTeam && defaults.locked_spread_home_point === null) {
        defaults.locked_spread_home_point = r.point;
        defaults.locked_spread_home_price = r.price;
      }
      if (r.outcome_name === awayTeam && defaults.locked_spread_away_point === null) {
        defaults.locked_spread_away_point = r.point;
        defaults.locked_spread_away_price = r.price;
      }
    }
  }

  return defaults;
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const SUPABASE_URL = getEnv("SUPABASE_URL");
    const SERVICE_ROLE_KEY = getEnv("SUPABASE_SERVICE_ROLE_KEY");
    const bookmakerKey = (Deno.env.get("PREFERRED_BOOKMAKER") ?? "fanduel").toLowerCase();

    const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
      auth: { persistSession: false },
    });

    const now = new Date();
    const runDate = ymdInTZ(now, RUN_TZ);

    // T-15 window: games starting in [now+10m, now+20m]
    const windowStartMs = now.getTime() + 10 * 60 * 1000;
    const windowEndMs = now.getTime() + 20 * 60 * 1000;
    const windowStart = new Date(windowStartMs);
    const windowEnd = new Date(windowEndMs);

    // Fetch predictions from slate-with-picks
    const rawSlate = await fetchSlateWithPicks("today");

    // Extract candidates in the T-15 window with score >= 65
    const candidates = extractCandidates(rawSlate, windowStart, windowEnd);

    if (candidates.length === 0) {
      return json({
        ok: true,
        version: VERSION,
        message: "No games in T-15 window or no picks above threshold",
        now: now.toISOString(),
        run_date: runDate,
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
        candidates: 0,
        locked: 0,
      });
    }

    // Check which events are already locked today
    const eventIds = candidates.map((c) => c.event_id);
    const { data: existingRows, error: existErr } = await supabase
      .from("locked_picks")
      .select("event_id")
      .eq("run_date", runDate)
      .in("event_id", eventIds);

    if (existErr) throw new Error(`locked_picks check failed: ${existErr.message}`);

    const alreadyLocked = new Set((existingRows ?? []).map((r: any) => r.event_id));
    const newCandidates = candidates.filter((c) => !alreadyLocked.has(c.event_id));

    if (newCandidates.length === 0) {
      return json({
        ok: true,
        version: VERSION,
        message: "All candidates already locked",
        now: now.toISOString(),
        run_date: runDate,
        candidates: candidates.length,
        already_locked: alreadyLocked.size,
        locked: 0,
      });
    }

    // Enforce single daily Top Pick:
    // Check if a top_pick already exists for today
    const { data: existingTopPick, error: topErr } = await supabase
      .from("locked_picks")
      .select("id")
      .eq("run_date", runDate)
      .eq("tier", "top_pick")
      .limit(1);

    if (topErr) throw new Error(`top_pick check failed: ${topErr.message}`);

    const hasTopPickToday = (existingTopPick ?? []).length > 0;

    // Sort new candidates by score descending
    newCandidates.sort((a, b) => b.score - a.score);

    // Build inserts with locked odds
    const inserts: Record<string, unknown>[] = [];

    for (const c of newCandidates) {
      const tier = tierForScore(c.score);
      if (!tier) continue;

      // If this would be a top_pick but we already have one today, downgrade to strong_lean
      let finalTier = tier;
      if (tier === "top_pick" && hasTopPickToday) {
        finalTier = "strong_lean";
      }

      // If this is the first top_pick candidate and no top_pick exists today,
      // mark it as top_pick (it's the highest score since we sorted)
      if (tier === "top_pick" && !hasTopPickToday) {
        // Only the FIRST one (highest score) gets top_pick
        // Check if we've already assigned a top_pick in this batch
        const alreadyAssignedTopPick = inserts.some((i) => i.tier === "top_pick");
        if (alreadyAssignedTopPick) {
          finalTier = "strong_lean";
        }
      }

      // Fetch locked odds
      const lockedOdds = await fetchCurrentOdds(supabase, c.event_id, bookmakerKey);

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
        ...lockedOdds,
      });
    }

    if (inserts.length === 0) {
      return json({
        ok: true,
        version: VERSION,
        message: "No picks passed tier threshold after filtering",
        now: now.toISOString(),
        run_date: runDate,
        candidates: candidates.length,
        locked: 0,
      });
    }

    // Upsert to locked_picks (idempotent on run_date + event_id)
    const { error: insErr } = await supabase
      .from("locked_picks")
      .upsert(inserts, {
        onConflict: "run_date,event_id",
        ignoreDuplicates: true,
      });

    if (insErr) throw new Error(`locked_picks upsert failed: ${insErr.message}`);

    return json({
      ok: true,
      version: VERSION,
      now: now.toISOString(),
      run_date: runDate,
      window_start: windowStart.toISOString(),
      window_end: windowEnd.toISOString(),
      candidates: candidates.length,
      already_locked: alreadyLocked.size,
      locked: inserts.length,
      top_pick_assigned: inserts.some((i) => i.tier === "top_pick"),
      bookmaker: bookmakerKey,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[lock_picks_tminus15] error: ${msg}`);
    return json({ ok: false, error: msg }, 500);
  }
});

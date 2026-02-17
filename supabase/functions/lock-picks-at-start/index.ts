// supabase/functions/lock-picks-at-start/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

const VERSION = "lock-picks-at-start@2026-02-06_v11_FIXED_no_double_calibration";
const RUN_TZ = "America/Chicago";
const EVENTS_TABLE = "events";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

type SlatePickOut = {
  status: "pick" | "no_bet";
  selection?: string;
  confidence?: "low" | "medium" | "high";
  score?: number;
  rationale?: string[];
  reason?: string;
  confidence_pct?: number;
  good_bet_prob?: number;  // ✅ Now properly supported from Python model
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
  league: string;
  start_time: string;
  market: "moneyline" | "spread" | "total";
  side: string;
  score: number;
  confidence: number;
  why: string[];

  home_team: string | null;
  away_team: string | null;
  home_abbr: string | null;
  away_abbr: string | null;
  selection_team: string | null;
};

function isoNow() {
  return new Date().toISOString();
}
function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}
function normalizeMarket(market: string): "moneyline" | "spread" | "total" {
  if (market === "moneyline" || market === "spread" || market === "total") return market;
  return "spread";
}
function leagueLabelFromSportKey(sportKey: string): string {
  const map: Record<string, string> = {
    nba: "NBA",
    mlb: "MLB",
    nhl: "NHL",
    ncaab: "NCAAB",
    ncaaf: "NCAAF",
    nfl: "NFL",
  };
  return map[sportKey] || sportKey.toUpperCase();
}

// ✅ FIX: REMOVED calibrateConfidence() function entirely!
// The Python model already provides calibrated probabilities via isotonic regression.
// Re-calibrating here was causing predictions to be 5-15% overconfident.

const THRESHOLDS = {
  TOP_PICK_MIN_SCORE: 74,
  STRONG_LEAN_MIN_SCORE: 66,
  WATCHLIST_MIN_SCORE: 60,
};

function tierForScore(score: number): "top_pick" | "strong_lean" | "watchlist" | null {
  if (score >= THRESHOLDS.TOP_PICK_MIN_SCORE) return "top_pick";
  if (score >= THRESHOLDS.STRONG_LEAN_MIN_SCORE) return "strong_lean";
  if (score >= THRESHOLDS.WATCHLIST_MIN_SCORE) return "watchlist";
  return null;
}

function teamDisplayName(team?: SlateTeam): string | null {
  const name = team?.name?.trim();
  if (name) return name;
  const abbr = team?.abbreviation?.trim();
  if (abbr) return abbr;
  return null;
}

function deriveSelectionTeam(params: {
  market: "moneyline" | "spread" | "total";
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

function pickToCandidate(params: {
  game: SlateGame;
  sportKey: string;
  league: string;
  market: "moneyline" | "spread" | "total";
  pick: SlatePickOut;
}): Candidate | null {
  const { game, sportKey, league, market, pick } = params;

  if (pick.status !== "pick") return null;
  if (!pick.selection) return null;
  if (typeof pick.score !== "number") return null;

  const score = clamp(pick.score, 0, 100);

  const homeName = teamDisplayName(game?.homeTeam);
  const awayName = teamDisplayName(game?.awayTeam);
  const homeAbbr = game?.homeTeam?.abbreviation?.trim() ?? null;
  const awayAbbr = game?.awayTeam?.abbreviation?.trim() ?? null;

  const selection_team = deriveSelectionTeam({
    market,
    selection: pick.selection,
    homeName,
    awayName,
    homeAbbr,
    awayAbbr,
  });

  // ✅ FIX: Use the calibrated probability from the model if available
  // If not available, fall back to score/100
  let confidence: number;
  if (pick.good_bet_prob !== undefined && pick.good_bet_prob !== null) {
    // Model provided the actual isotonic-calibrated probability - use it!
    confidence = pick.good_bet_prob;
  } else {
    // Fallback for non-model picks (shouldn't happen for NBA)
    confidence = score / 100;
  }

  return {
    event_id: game.id,
    sport: sportKey,
    league,
    start_time: game.startTime,
    market,
    side: pick.selection,
    score,
    confidence,  // ✅ This is now the ACTUAL calibrated probability!
    why: Array.isArray(pick.rationale) ? pick.rationale.slice(0, 5) : [],
    home_team: homeName,
    away_team: awayName,
    home_abbr: homeAbbr,
    away_abbr: awayAbbr,
    selection_team,
  };
}

function extractBestPickPerGame(rawSlate: Record<string, SlateGame[]>): Candidate[] {
  const bestByGame = new Map<string, Candidate>();

  for (const sportKey of Object.keys(rawSlate || {})) {
    if (sportKey === "topPicks") continue;

    const league = leagueLabelFromSportKey(sportKey);
    const games = rawSlate[sportKey] || [];

    for (const game of games) {
      const markets: Array<"moneyline" | "spread" | "total"> = ["moneyline", "spread", "total"];
      for (const m of markets) {
        const pick = game?.picks?.[m];
        if (!pick) continue;

        const cand = pickToCandidate({
          game,
          sportKey,
          league,
          market: normalizeMarket(m),
          pick,
        });

        if (!cand) continue;

        const existing = bestByGame.get(cand.event_id);
        if (!existing || cand.score > existing.score) bestByGame.set(cand.event_id, cand);
      }
    }
  }

  return Array.from(bestByGame.values());
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

function resolveRunDate(dayParam: string, now: Date, runDateOverride?: string | null): string {
  if (runDateOverride && /^\d{4}-\d{2}-\d{2}$/.test(runDateOverride)) return runDateOverride;

  const dp = (dayParam || "").trim().toLowerCase();
  if (/^\d{4}-\d{2}-\d{2}$/.test(dp)) return dp;

  return ymdInTZ(now, RUN_TZ);
}

async function fetchSlateWithPicks(day: string): Promise<Record<string, SlateGame[]>> {
  const supabaseUrl = Deno.env.get("PP_SUPABASE_URL") || Deno.env.get("SUPABASE_URL");
  const serviceRole =
    Deno.env.get("PP_SERVICE_ROLE_KEY") ||
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ||
    Deno.env.get("SERVICE_ROLE_KEY");

  if (!supabaseUrl) throw new Error("Missing PP_SUPABASE_URL (or SUPABASE_URL)");
  if (!serviceRole) throw new Error("Missing PP_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_ROLE_KEY)");

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

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const url = new URL(req.url);

    const day = (url.searchParams.get("day") || "today").toLowerCase();
    const mode = (url.searchParams.get("mode") || "").toLowerCase();
    const source = (url.searchParams.get("source") || "live").toLowerCase();

    const leadMinutes = Number(url.searchParams.get("lead_minutes") || "120");
    const graceMinutes = Number(url.searchParams.get("grace_minutes") || "15");

    const debug = url.searchParams.get("debug") === "1";
    const runDateOverride = url.searchParams.get("run_date_override");

    const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
    const SERVICE_ROLE_KEY =
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || Deno.env.get("SERVICE_ROLE_KEY");

    if (!SUPABASE_URL) throw new Error("Missing SUPABASE_URL");
    if (!SERVICE_ROLE_KEY) throw new Error("Missing SUPABASE_SERVICE_ROLE_KEY (or SERVICE_ROLE_KEY)");

    const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
      auth: { persistSession: false },
    });

    const now = new Date();
    const runDate = resolveRunDate(day, now, runDateOverride);

    const rawSlate = await fetchSlateWithPicks(day);

    const teamsByEventId = new Map<
      string,
      { home_team: string | null; away_team: string | null; home_abbr: string | null; away_abbr: string | null }
    >();

    for (const sportKey of Object.keys(rawSlate || {})) {
      if (sportKey === "topPicks") continue;
      const games = (rawSlate as any)[sportKey] as SlateGame[] | undefined;
      if (!Array.isArray(games)) continue;

      for (const g of games) {
        teamsByEventId.set(g.id, {
          home_team: teamDisplayName(g?.homeTeam),
          away_team: teamDisplayName(g?.awayTeam),
          home_abbr: g?.homeTeam?.abbreviation?.trim() ?? null,
          away_abbr: g?.awayTeam?.abbreviation?.trim() ?? null,
        });
      }
    }

    const slateEventIds = Array.from(teamsByEventId.keys());

    async function fetchTeamsFromEventsTable(eventIds: string[]) {
      if (eventIds.length === 0) return new Map<string, any>();

      const { data, error } = await supabase
        .from(EVENTS_TABLE)
        .select("event_id,home_team,away_team,home_abbr,away_abbr")
        .in("event_id", eventIds);

      if (error) {
        return new Map<string, any>([["__error__", error.message]]);
      }

      const m = new Map<string, any>();
      for (const r of (data ?? []) as any[]) m.set(r.event_id, r);
      return m;
    }

    async function backfillForRunDate(): Promise<{
      backfilled_rows: number;
      missing_in_slate: number;
      filled_from_events: number;
      events_lookup_error?: string;
      sample_missing: string[];
      sample_slate: string[];
    }> {
      const { data: nullRows, error: nullErr } = await supabase
        .from("pick_snapshots")
        .select("id,event_id,market,side,run_date")
        .eq("run_date", runDate)
        .or("home_team.is.null,away_team.is.null,selection_team.is.null")
        .limit(3000);

      if (nullErr) throw new Error(nullErr.message);

      const rows = (nullRows ?? []) as any[];
      if (rows.length === 0) {
        return {
          backfilled_rows: 0,
          missing_in_slate: 0,
          filled_from_events: 0,
          sample_missing: [],
          sample_slate: slateEventIds.slice(0, 10),
        };
      }

      const missingIds = Array.from(
        new Set(rows.map((r) => r.event_id).filter((eid) => !teamsByEventId.has(eid))),
      );

      const eventsMap = await fetchTeamsFromEventsTable(missingIds);
      const eventsLookupError = eventsMap.get("__error__") as string | undefined;

      let updated = 0;
      let filledFromEvents = 0;
      const missingStill: string[] = [];

      for (const r of rows) {
        let t = teamsByEventId.get(r.event_id) as any;

        if (!t && !eventsLookupError) {
          const ev = eventsMap.get(r.event_id);
          if (ev) {
            t = {
              home_team: ev.home_team ?? null,
              away_team: ev.away_team ?? null,
              home_abbr: ev.home_abbr ?? null,
              away_abbr: ev.away_abbr ?? null,
            };
            filledFromEvents++;
          }
        }

        if (!t) {
          missingStill.push(r.event_id);
          continue;
        }

        const selection_team = deriveSelectionTeam({
          market: normalizeMarket(r.market),
          selection: r.side,
          homeName: t.home_team,
          awayName: t.away_team,
          homeAbbr: t.home_abbr,
          awayAbbr: t.away_abbr,
        });

        const patch: Record<string, any> = { home_team: t.home_team, away_team: t.away_team };
        if (selection_team) patch.selection_team = selection_team;

        const { error: upErr } = await supabase.from("pick_snapshots").update(patch).eq("id", r.id);
        if (!upErr) updated++;
      }

      return {
        backfilled_rows: updated,
        missing_in_slate: missingIds.length,
        filled_from_events: filledFromEvents,
        events_lookup_error: eventsLookupError,
        sample_missing: Array.from(new Set(missingStill)).slice(0, 10),
        sample_slate: slateEventIds.slice(0, 10),
      };
    }

    if (mode === "backfill") {
      const res = await backfillForRunDate();

      return new Response(
        JSON.stringify({
          ok: true,
          version: VERSION,
          mode,
          day,
          run_date: runDate,
          now: isoNow(),
          slate_event_ids: slateEventIds.length,
          backfilled_rows: res.backfilled_rows,
          missing_in_slate: res.missing_in_slate,
          filled_from_events: res.filled_from_events,
          events_lookup_error: res.events_lookup_error,
          debug: debug
            ? {
                sample_slate_event_ids: res.sample_slate,
                sample_still_missing_event_ids: res.sample_missing,
              }
            : undefined,
        }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const leadMs = Math.max(0, leadMinutes) * 60 * 1000;
    const graceMs = Math.max(0, graceMinutes) * 60 * 1000;

    const windowStart = new Date(now.getTime() - graceMs);
    const windowEnd = new Date(now.getTime() + leadMs);

    const best = extractBestPickPerGame(rawSlate);

    const candidatesToLock = best.filter((c) => {
      const st = new Date(c.start_time);
      return st >= windowStart && st <= windowEnd;
    });

    if (candidatesToLock.length === 0) {
      return new Response(
        JSON.stringify({
          ok: true,
          version: VERSION,
          message: "No games to lock in window",
          now: isoNow(),
          run_date: runDate,
          window_start: windowStart.toISOString(),
          window_end: windowEnd.toISOString(),
          lead_minutes: leadMinutes,
          grace_minutes: graceMinutes,
          attempted: 0,
          inserted: 0,
          debug: debug ? { slate_event_ids: slateEventIds.length } : undefined,
        }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const eventIds = Array.from(new Set(candidatesToLock.map((c) => c.event_id)));

    const { data: existingRows, error: existingErr } = await supabase
      .from("pick_snapshots")
      .select("event_id")
      .eq("run_date", runDate)
      .in("event_id", eventIds);

    if (existingErr) throw new Error(existingErr.message);

    const alreadyLocked = new Set((existingRows ?? []).map((r: any) => r.event_id));

    const inserts = candidatesToLock
      .filter((c) => !alreadyLocked.has(c.event_id))
      .map((c) => {
        const tier = tierForScore(c.score);
        if (!tier) return null;

        return {
          event_id: c.event_id,
          sport: c.sport,
          league: c.league,
          market: c.market,
          side: c.side,
          tier,
          score: c.score,
          confidence: c.confidence,  // ✅ Now the actual calibrated probability!
          why: c.why,
          game_start_time: c.start_time,
          locked_at: now.toISOString(),
          run_date: runDate,
          source: source === "backtest" ? "backtest" : "live",
          home_team: c.home_team,
          away_team: c.away_team,
          selection_team: c.selection_team,
        };
      })
      .filter(Boolean) as Array<Record<string, unknown>>;

    let inserted = 0;
    if (inserts.length > 0) {
      const { error: insErr } = await supabase
        .from("pick_snapshots")
        .upsert(inserts, {
          onConflict: "run_date,event_id,market,tier",
          ignoreDuplicates: true,
        });

      if (insErr) throw new Error(insErr.message);
      inserted = inserts.length;
    }

    const bf = await backfillForRunDate();

    return new Response(
      JSON.stringify({
        ok: true,
        version: VERSION,
        now: isoNow(),
        run_date: runDate,
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
        lead_minutes: leadMinutes,
        grace_minutes: graceMinutes,
        attempted: candidatesToLock.length,
        unique_event_ids: eventIds.length,
        already_locked: alreadyLocked.size,
        inserted,
        backfilled_rows: bf.backfilled_rows,
        missing_in_slate: bf.missing_in_slate,
        filled_from_events: bf.filled_from_events,
        events_lookup_error: bf.events_lookup_error,
        debug: debug
          ? {
              slate_event_ids: slateEventIds.length,
              sample_still_missing_event_ids: bf.sample_missing,
            }
          : undefined,
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ ok: false, error: err instanceof Error ? err.message : String(err) }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
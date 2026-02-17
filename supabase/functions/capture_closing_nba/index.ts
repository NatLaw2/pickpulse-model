/// <reference lib="deno.ns" />
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

/**
 * capture_closing_nba
 *
 * Fills in closing moneyline + spread values on game_results rows that
 * are missing them, using the latest pre-tip FanDuel snapshot from
 * closing_lines.
 *
 * Designed to run every 5 minutes via cron. Does NOT call the Odds API
 * — it only reads closing_lines and patches game_results.
 *
 * Required env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

// ---------------------------------------------------------------------------
// Helpers (mirrors final_nba patterns)
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

async function supaFetch(path: string, init: RequestInit = {}) {
  const SUPABASE_URL = getEnv("SUPABASE_URL");
  const SERVICE_ROLE = getEnv("SUPABASE_SERVICE_ROLE_KEY");

  const url = `${SUPABASE_URL}${path}`;
  const headers = new Headers(init.headers || {});
  headers.set("Authorization", `Bearer ${SERVICE_ROLE}`);
  headers.set("apikey", SERVICE_ROLE);
  headers.set("Content-Type", "application/json");

  const resp = await fetch(url, { ...init, headers });
  const text = await resp.text();
  return { resp, text };
}

function parseIso(s: string) {
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type GameResultRow = {
  sport: string;
  event_id: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  closing_ml_home: number | null;
};

type ClosingLineRow = {
  event_id: string;
  captured_at: string;
  market: string;
  outcome_name: string;
  price: number | null;
  point: number | null;
};

// ---------------------------------------------------------------------------
// Core logic
// ---------------------------------------------------------------------------

async function fetchGamesNeedingClosing(): Promise<GameResultRow[]> {
  const select = "sport,event_id,commence_time,home_team,away_team,closing_ml_home";

  const path =
    `/rest/v1/game_results?select=${encodeURIComponent(select)}` +
    `&sport=eq.nba` +
    `&closing_ml_home=is.null` +
    `&order=commence_time.desc` +
    `&limit=200`;

  const { resp, text } = await supaFetch(path, { method: "GET" });
  if (!resp.ok) throw new Error(`game_results query failed (${resp.status}): ${text}`);

  return JSON.parse(text) as GameResultRow[];
}

async function fetchClosingSnapshot(
  eventId: string,
  commenceTimeIso: string,
  bookmakerKey: string,
): Promise<ClosingLineRow[]> {
  const select = "event_id,captured_at,market,outcome_name,price,point";

  const path =
    `/rest/v1/closing_lines?select=${encodeURIComponent(select)}` +
    `&sport=eq.nba` +
    `&event_id=eq.${encodeURIComponent(eventId)}` +
    `&bookmaker_key=eq.${encodeURIComponent(bookmakerKey)}` +
    `&market=in.(h2h,spreads)` +
    `&order=captured_at.desc` +
    `&limit=100`;

  const { resp, text } = await supaFetch(path, { method: "GET" });
  if (!resp.ok) {
    console.log(`[capture_closing_nba] closing_lines fetch failed for ${eventId}: ${resp.status}`);
    return [];
  }

  const rows = JSON.parse(text) as ClosingLineRow[];

  // Pick the latest captured_at that is <= commence_time (pre-tip)
  const commence = parseIso(commenceTimeIso);
  if (!commence || rows.length === 0) return rows;

  // Group by captured_at
  const byCap = new Map<string, ClosingLineRow[]>();
  for (const r of rows) {
    if (!r.captured_at) continue;
    if (!byCap.has(r.captured_at)) byCap.set(r.captured_at, []);
    byCap.get(r.captured_at)!.push(r);
  }

  // Find latest captured_at <= commence_time
  let bestTs: string | null = null;
  for (const capTs of byCap.keys()) {
    const cap = parseIso(capTs);
    if (!cap) continue;
    if (cap.getTime() <= commence.getTime()) {
      if (!bestTs || cap.getTime() > parseIso(bestTs)!.getTime()) {
        bestTs = capTs;
      }
    }
  }

  // Fall back to latest snapshot if nothing is pre-tip
  if (!bestTs) {
    let latest: string | null = null;
    for (const capTs of byCap.keys()) {
      const cap = parseIso(capTs);
      if (!cap) continue;
      if (!latest || cap.getTime() > parseIso(latest)!.getTime()) latest = capTs;
    }
    bestTs = latest;
  }

  return bestTs ? (byCap.get(bestTs) ?? []) : [];
}

function extractClosing(rows: ClosingLineRow[], homeTeam: string, awayTeam: string) {
  let mlHome: number | null = null;
  let mlAway: number | null = null;
  let spHomePoint: number | null = null;
  let spHomePrice: number | null = null;
  let spAwayPoint: number | null = null;
  let spAwayPrice: number | null = null;

  for (const r of rows) {
    if (!r.market || !r.outcome_name) continue;

    if (r.market === "h2h") {
      if (r.outcome_name === homeTeam) mlHome = r.price ?? mlHome;
      if (r.outcome_name === awayTeam) mlAway = r.price ?? mlAway;
    }
    if (r.market === "spreads") {
      if (r.outcome_name === homeTeam) {
        spHomePoint = (r.point ?? spHomePoint) as number | null;
        spHomePrice = (r.price ?? spHomePrice) as number | null;
      }
      if (r.outcome_name === awayTeam) {
        spAwayPoint = (r.point ?? spAwayPoint) as number | null;
        spAwayPrice = (r.price ?? spAwayPrice) as number | null;
      }
    }
  }

  const hasAny = mlHome !== null || mlAway !== null || spHomePoint !== null;

  return {
    hasAny,
    closing_ml_home: mlHome,
    closing_ml_away: mlAway,
    closing_spread_home_point: spHomePoint,
    closing_spread_home_price: spHomePrice,
    closing_spread_away_point: spAwayPoint,
    closing_spread_away_price: spAwayPrice,
  };
}

async function patchGameResult(eventId: string, closing: Record<string, unknown>): Promise<boolean> {
  // PATCH only closing columns — does not touch home_score / away_score
  const path =
    `/rest/v1/game_results?sport=eq.nba&event_id=eq.${encodeURIComponent(eventId)}`;

  const { resp, text } = await supaFetch(path, {
    method: "PATCH",
    headers: { Prefer: "return=minimal" },
    body: JSON.stringify(closing),
  });

  if (!resp.ok) {
    console.log(`[capture_closing_nba] PATCH failed for ${eventId}: ${resp.status} ${text}`);
    return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const bookmakerKey = (Deno.env.get("PREFERRED_BOOKMAKER") ?? "fanduel").toLowerCase();

    // Step 1: Find game_results rows missing closing odds
    const games = await fetchGamesNeedingClosing();

    if (games.length === 0) {
      return json({
        ok: true,
        games_checked: 0,
        games_updated: 0,
        note: "No game_results rows with null closing odds found.",
      });
    }

    // Step 2: For each, look up closing_lines and patch
    let updated = 0;
    let skipped = 0;

    for (const g of games) {
      const snapshot = await fetchClosingSnapshot(g.event_id, g.commence_time, bookmakerKey);
      if (snapshot.length === 0) {
        skipped++;
        continue;
      }

      const closing = extractClosing(snapshot, g.home_team, g.away_team);
      if (!closing.hasAny) {
        skipped++;
        continue;
      }

      // Build patch payload (only closing columns)
      const patch = {
        closing_ml_home: closing.closing_ml_home,
        closing_ml_away: closing.closing_ml_away,
        closing_spread_home_point: closing.closing_spread_home_point,
        closing_spread_home_price: closing.closing_spread_home_price,
        closing_spread_away_point: closing.closing_spread_away_point,
        closing_spread_away_price: closing.closing_spread_away_price,
      };

      const ok = await patchGameResult(g.event_id, patch);
      if (ok) updated++;
      else skipped++;
    }

    return json({
      ok: true,
      games_checked: games.length,
      games_updated: updated,
      games_skipped: skipped,
      bookmaker: bookmakerKey,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[capture_closing_nba] error:", msg);
    return json({ ok: false, error: msg }, 500);
  }
});

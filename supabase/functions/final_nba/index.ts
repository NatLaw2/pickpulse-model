/// <reference lib="deno.ns" />
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

type ClosingLineRow = {
  sport: string;
  event_id: string;
  captured_at: string;
  commence_time: string | null;
  home_team: string | null;
  away_team: string | null;
  bookmaker_key: string | null;
  bookmaker_title: string | null;
  market: string | null; // h2h | spreads | totals
  outcome_name: string | null;
  price: number | null;
  point: number | null;
};

type GameResultUpsert = {
  sport: string; // nba
  event_id: string;
  commence_time: string;
  home_team: string;
  away_team: string;

  closing_ml_home: number | null;
  closing_ml_away: number | null;

  closing_spread_home_point: number | null;
  closing_spread_home_price: number | null;
  closing_spread_away_point: number | null;
  closing_spread_away_price: number | null;

  home_score: number | null;
  away_score: number | null;

  created_at?: string;
};

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

function oddsScoresUrl(apiKey: string, daysFrom: number) {
  return `https://api.the-odds-api.com/v4/sports/basketball_nba/scores/?apiKey=${apiKey}&daysFrom=${daysFrom}&dateFormat=iso`;
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

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function parseIso(s: string) {
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function hoursBetween(a: Date, b: Date) {
  return Math.abs(a.getTime() - b.getTime()) / 36e5;
}

async function fetchClosingCandidates(params: {
  bookmakerKey: string;
  home: string;
  away: string;
  commenceTimeIso: string;
  windowHours: number;
}): Promise<ClosingLineRow[]> {
  const { bookmakerKey, home, away, commenceTimeIso, windowHours } = params;

  const ct = parseIso(commenceTimeIso);
  if (!ct) return [];

  const min = new Date(ct.getTime() - windowHours * 3600 * 1000).toISOString();
  const max = new Date(ct.getTime() + windowHours * 3600 * 1000).toISOString();

  const select =
    "sport,event_id,captured_at,commence_time,home_team,away_team,bookmaker_key,bookmaker_title,market,outcome_name,price,point";

  // We fetch a broad candidate set filtered by bookmaker + time window
  // Then we narrow to team match + choose closest commence_time group in code.
  const path =
    `/rest/v1/closing_lines?select=${encodeURIComponent(select)}` +
    `&sport=eq.nba` +
    `&bookmaker_key=eq.${encodeURIComponent(bookmakerKey)}` +
    `&commence_time=gte.${encodeURIComponent(min)}` +
    `&commence_time=lte.${encodeURIComponent(max)}` +
    `&order=captured_at.desc` +
    `&limit=2000`;

  const { resp, text } = await supaFetch(path, { method: "GET" });
  if (!resp.ok) throw new Error(`closing_lines fetch failed (${resp.status}): ${text}`);

  const rows = JSON.parse(text) as ClosingLineRow[];

  // Team match (exact) with swapped fallback
  const direct = rows.filter(
    (r) => r.home_team === home && r.away_team === away,
  );
  const swapped = rows.filter(
    (r) => r.home_team === away && r.away_team === home,
  );

  // prefer direct, but allow swapped if nothing else
  return direct.length > 0 ? direct : swapped;
}

function groupByCommenceTime(rows: ClosingLineRow[]) {
  const m = new Map<string, ClosingLineRow[]>();
  for (const r of rows) {
    const key = r.commence_time ?? "__null__";
    if (!m.has(key)) m.set(key, []);
    m.get(key)!.push(r);
  }
  return m;
}

function pickClosestCommenceGroup(rows: ClosingLineRow[], targetIso: string) {
  if (rows.length === 0) return { pickedCommence: null as string | null, group: [] as ClosingLineRow[] };

  const target = parseIso(targetIso);
  if (!target) return { pickedCommence: null, group: [] };

  const groups = groupByCommenceTime(rows);

  let bestKey: string | null = null;
  let bestDelta = Infinity;

  for (const [k] of groups.entries()) {
    if (k === "__null__") continue;
    const d = parseIso(k);
    if (!d) continue;

    const delta = hoursBetween(d, target);
    if (delta < bestDelta) {
      bestDelta = delta;
      bestKey = k;
    }
  }

  if (!bestKey) return { pickedCommence: null, group: [] };
  return { pickedCommence: bestKey, group: groups.get(bestKey)! };
}

function pickLatestPreTipSnapshot(rows: ClosingLineRow[], commenceIso: string) {
  // Choose latest captured_at that is <= commence_time (pre-tip).
  const commence = parseIso(commenceIso);
  if (!commence) return [] as ClosingLineRow[];

  let bestTs: string | null = null;
  let bestRows: ClosingLineRow[] = [];

  // group by captured_at
  const byCap = new Map<string, ClosingLineRow[]>();
  for (const r of rows) {
    if (!r.captured_at) continue;
    if (!byCap.has(r.captured_at)) byCap.set(r.captured_at, []);
    byCap.get(r.captured_at)!.push(r);
  }

  for (const [capTs, capRows] of byCap.entries()) {
    const cap = parseIso(capTs);
    if (!cap) continue;
    if (cap.getTime() <= commence.getTime()) {
      if (!bestTs || cap.getTime() > (parseIso(bestTs)!.getTime())) {
        bestTs = capTs;
        bestRows = capRows;
      }
    }
  }

  // If none are strictly pre-tip, fall back to latest captured snapshot
  if (bestRows.length === 0) {
    let latest: string | null = null;
    for (const capTs of byCap.keys()) {
      const cap = parseIso(capTs);
      if (!cap) continue;
      if (!latest || cap.getTime() > (parseIso(latest)!.getTime())) latest = capTs;
    }
    if (latest) bestRows = byCap.get(latest)!;
  }

  return bestRows;
}

function extractClosingFromRows(rows: ClosingLineRow[]) {
  const homeTeam = rows.find((r) => r.home_team)?.home_team ?? null;
  const awayTeam = rows.find((r) => r.away_team)?.away_team ?? null;

  let mlHome: number | null = null;
  let mlAway: number | null = null;

  let spHomePoint: number | null = null;
  let spHomePrice: number | null = null;
  let spAwayPoint: number | null = null;
  let spAwayPrice: number | null = null;

  for (const r of rows) {
    if (!r.market || !r.outcome_name) continue;

    if (r.market === "h2h") {
      if (homeTeam && r.outcome_name === homeTeam) mlHome = r.price ?? mlHome;
      if (awayTeam && r.outcome_name === awayTeam) mlAway = r.price ?? mlAway;
    }

    if (r.market === "spreads") {
      if (homeTeam && r.outcome_name === homeTeam) {
        spHomePoint = (r.point ?? spHomePoint) as number | null;
        spHomePrice = (r.price ?? spHomePrice) as number | null;
      }
      if (awayTeam && r.outcome_name === awayTeam) {
        spAwayPoint = (r.point ?? spAwayPoint) as number | null;
        spAwayPrice = (r.price ?? spAwayPrice) as number | null;
      }
    }
  }

  return {
    closing_ml_home: mlHome,
    closing_ml_away: mlAway,
    closing_spread_home_point: spHomePoint,
    closing_spread_home_price: spHomePrice,
    closing_spread_away_point: spAwayPoint,
    closing_spread_away_price: spAwayPrice,
  };
}

async function upsertGameResults(rows: GameResultUpsert[]) {
  if (rows.length === 0) return { upserted: 0 };

  const path = `/rest/v1/game_results?on_conflict=sport,event_id`;
  const { resp, text } = await supaFetch(path, {
    method: "POST",
    headers: {
      Prefer: "resolution=merge-duplicates,return=representation",
    },
    body: JSON.stringify(rows),
  });

  if (!resp.ok) throw new Error(`game_results upsert failed (${resp.status}): ${text}`);

  const returned = JSON.parse(text);
  return { upserted: Array.isArray(returned) ? returned.length : rows.length };
}

async function fetchScoresWithRetry(apiKey: string, requestedDaysFrom: number) {
  // Scores endpoint can be picky. We:
  // 1) clamp to a safe range
  // 2) if API still says invalid, retry with 2
  const clamped = clamp(requestedDaysFrom, 1, 2);

  const tryDays = async (d: number) => {
    const resp = await fetch(oddsScoresUrl(apiKey, d));
    const text = await resp.text();
    return { resp, text, daysFrom: d };
  };

  let first = await tryDays(clamped);
  if (first.resp.ok) return first;

  // If invalid daysFrom, retry with 2
  if (first.resp.status === 422 && first.text.includes("INVALID_SCORES_DAYS_FROM")) {
    const second = await tryDays(2);
    return second;
  }

  return first;
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const ODDS_API_KEY = getEnv("ODDS_API_KEY");

    const lookbackDaysRaw = Number(Deno.env.get("RESULTS_LOOKBACK_DAYS") ?? "2");
    const preferredBook = (Deno.env.get("PREFERRED_BOOKMAKER") ?? "fanduel").toLowerCase();
    const matchWindowHours = Number(Deno.env.get("MATCH_WINDOW_HOURS") ?? "6");

    const scoresResp = await fetchScoresWithRetry(ODDS_API_KEY, lookbackDaysRaw);
    if (!scoresResp.resp.ok) {
      return json(
        {
          ok: false,
          error: "Odds API error",
          status: scoresResp.resp.status,
          body: scoresResp.text,
          requested_daysFrom: lookbackDaysRaw,
          used_daysFrom: scoresResp.daysFrom,
        },
        500,
      );
    }

    const games = JSON.parse(scoresResp.text) as Array<{
      id: string;
      completed: boolean;
      commence_time: string;
      home_team: string;
      away_team: string;
      scores?: Array<{ name: string; score: string }>;
      last_update?: string;
    }>;

    const finals = (games ?? []).filter((g) => g.completed === true);

    let gamesWithClosing = 0;
    let gamesMissingClosing = 0;

    const upserts: GameResultUpsert[] = [];

    for (const g of finals) {
      const homeScoreStr = g.scores?.find((s) => s.name === g.home_team)?.score ?? null;
      const awayScoreStr = g.scores?.find((s) => s.name === g.away_team)?.score ?? null;

      const homeScore = homeScoreStr ? Number(homeScoreStr) : null;
      const awayScore = awayScoreStr ? Number(awayScoreStr) : null;

      // Find candidate closing_lines rows by bookmaker + teams within ± window
      const candidates = await fetchClosingCandidates({
        bookmakerKey: preferredBook,
        home: g.home_team,
        away: g.away_team,
        commenceTimeIso: g.commence_time,
        windowHours: matchWindowHours,
      });

      // From candidates, pick the closest commence_time group, then latest pre-tip captured snapshot
      let closing = {
        closing_ml_home: null,
        closing_ml_away: null,
        closing_spread_home_point: null,
        closing_spread_home_price: null,
        closing_spread_away_point: null,
        closing_spread_away_price: null,
      };

      if (candidates.length > 0) {
        const { pickedCommence, group } = pickClosestCommenceGroup(candidates, g.commence_time);
        if (pickedCommence && group.length > 0) {
          const snapRows = pickLatestPreTipSnapshot(group, pickedCommence);
          const extracted = extractClosingFromRows(snapRows);
          closing = extracted;

          const hasAny =
            extracted.closing_ml_home !== null ||
            extracted.closing_ml_away !== null ||
            extracted.closing_spread_home_point !== null ||
            extracted.closing_spread_away_point !== null;

          if (hasAny) gamesWithClosing++;
          else gamesMissingClosing++;
        } else {
          gamesMissingClosing++;
        }
      } else {
        gamesMissingClosing++;
      }

      upserts.push({
        sport: "nba",
        event_id: g.id,
        commence_time: g.commence_time,
        home_team: g.home_team,
        away_team: g.away_team,
        ...closing,
        home_score: homeScore,
        away_score: awayScore,
        created_at: new Date().toISOString(),
      });
    }

    const result = await upsertGameResults(upserts);

    return json({
      ok: true,
      requested_lookback_days: lookbackDaysRaw,
      used_daysFrom: scoresResp.daysFrom,
      finals_found: finals.length,
      finals_processed: finals.length,
      upserted: result.upserted,
      closing_snapshot_book: preferredBook,
      match_window_hours: matchWindowHours,
      games_with_any_closing: gamesWithClosing,
      games_missing_closing: gamesMissingClosing,
      note:
        "If you see INVALID_SCORES_DAYS_FROM, reduce RESULTS_LOOKBACK_DAYS. This function clamps & retries automatically.",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return json({ ok: false, error: msg }, 500);
  }
});
/// <reference lib="deno.ns" />
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
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

/**
 * Odds API types (v4 odds endpoint)
 */
type OddsOutcome = { name: string; price: number; point?: number };
type OddsMarket = { key: string; last_update?: string; outcomes: OddsOutcome[] };
type OddsBookmaker = { key: string; title: string; last_update: string; markets: OddsMarket[] };
type OddsGame = {
  id: string;
  sport_key: string;
  sport_title: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmakers: OddsBookmaker[];
};

type ModelPickRow = {
  sport: string;
  event_id: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  pick_market: "h2h" | "spreads";
  pick_side: string;
  confidence: number; // 0..1
  model_version: string;
  reasoning?: string | null;
  created_at?: string;
};

function americanToImpliedProb(odds: number): number {
  // odds: -150 or +130
  if (odds === 0) return 0.5;
  if (odds < 0) return (-odds) / ((-odds) + 100);
  return 100 / (odds + 100);
}

function normalizeNoVig(pA: number, pB: number) {
  const sum = pA + pB;
  if (sum <= 0) return { a: 0.5, b: 0.5 };
  return { a: pA / sum, b: pB / sum };
}

function clamp01(x: number) {
  if (Number.isNaN(x)) return 0.5;
  return Math.max(0, Math.min(1, x));
}

function pickFromMoneyline(homeTeam: string, awayTeam: string, homeOdds: number, awayOdds: number) {
  const pHome = americanToImpliedProb(homeOdds);
  const pAway = americanToImpliedProb(awayOdds);
  const nv = normalizeNoVig(pHome, pAway);

  const pickSide = nv.a >= nv.b ? homeTeam : awayTeam;
  const confidence = clamp01(Math.max(nv.a, nv.b));

  return {
    pick_side: pickSide,
    confidence,
    reasoning:
      `baseline_v1 ML: home ${homeOdds} (p=${nv.a.toFixed(3)}), away ${awayOdds} (p=${nv.b.toFixed(3)})`,
  };
}

function pickFromSpread(
  homeTeam: string,
  awayTeam: string,
  homePoint: number,
  homePrice: number,
  awayPoint: number,
  awayPrice: number,
) {
  // For spreads, prices are typically near -110 both sides.
  // Baseline: choose side with better (higher) no-vig implied probability from prices.
  const pHome = americanToImpliedProb(homePrice);
  const pAway = americanToImpliedProb(awayPrice);
  const nv = normalizeNoVig(pHome, pAway);

  const pickSide = nv.a >= nv.b ? homeTeam : awayTeam;
  const confidence = clamp01(Math.max(nv.a, nv.b));

  return {
    pick_side: pickSide,
    confidence,
    reasoning:
      `baseline_v1 ATS: ${homeTeam} ${homePoint} @${homePrice} (p=${nv.a.toFixed(3)}), ` +
      `${awayTeam} ${awayPoint} @${awayPrice} (p=${nv.b.toFixed(3)})`,
  };
}

function oddsUrl(apiKey: string, regions = "us", markets = "h2h,spreads", bookmakers = "fanduel") {
  // Upcoming odds endpoint (v4)
  // https://api.the-odds-api.com/v4/sports/basketball_nba/odds/?regions=us&markets=h2h,spreads&oddsFormat=american&bookmakers=fanduel&apiKey=...
  return `https://api.the-odds-api.com/v4/sports/basketball_nba/odds/?regions=${encodeURIComponent(
    regions,
  )}&markets=${encodeURIComponent(markets)}&oddsFormat=american&bookmakers=${encodeURIComponent(
    bookmakers,
  )}&dateFormat=iso&apiKey=${encodeURIComponent(apiKey)}`;
}

async function upsertModelPicks(rows: ModelPickRow[]) {
  if (rows.length === 0) return { upserted: 0 };

  const path = `/rest/v1/model_picks?on_conflict=sport,event_id,pick_market,model_version`;
  const { resp, text } = await supaFetch(path, {
    method: "POST",
    headers: { Prefer: "resolution=merge-duplicates,return=representation" },
    body: JSON.stringify(rows),
  });

  if (!resp.ok) {
    throw new Error(`model_picks upsert failed (${resp.status}): ${text}`);
  }

  const returned = JSON.parse(text);
  return { upserted: Array.isArray(returned) ? returned.length : rows.length };
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const ODDS_API_KEY = getEnv("ODDS_API_KEY");

    const preferredBook = (Deno.env.get("PREFERRED_BOOKMAKER") ?? "fanduel").toLowerCase();
    const modelVersion = Deno.env.get("MODEL_VERSION") ?? "baseline_v1";

    const r = await fetch(oddsUrl(ODDS_API_KEY, "us", "h2h,spreads", preferredBook));
    const t = await r.text();
    if (!r.ok) {
      return json({ ok: false, error: "Odds API error", status: r.status, body: t }, 500);
    }

    const games = (JSON.parse(t) as OddsGame[]) ?? [];

    const now = Date.now();
    const picks: ModelPickRow[] = [];

    for (const g of games) {
      // Ignore already-started games (small buffer)
      const commenceMs = Date.parse(g.commence_time);
      if (!Number.isFinite(commenceMs) || commenceMs < now - 2 * 60 * 1000) continue;

      const book = (g.bookmakers ?? []).find((b) => (b.key ?? "").toLowerCase() === preferredBook);
      if (!book) continue;

      const h2h = (book.markets ?? []).find((m) => m.key === "h2h");
      const spreads = (book.markets ?? []).find((m) => m.key === "spreads");

      // ---- Moneyline pick
      if (h2h?.outcomes?.length) {
        const homeRow = h2h.outcomes.find((o) => o.name === g.home_team);
        const awayRow = h2h.outcomes.find((o) => o.name === g.away_team);

        if (homeRow?.price != null && awayRow?.price != null) {
          const mlPick = pickFromMoneyline(g.home_team, g.away_team, homeRow.price, awayRow.price);
          picks.push({
            sport: "nba",
            event_id: g.id,
            commence_time: g.commence_time,
            home_team: g.home_team,
            away_team: g.away_team,
            pick_market: "h2h",
            pick_side: mlPick.pick_side,
            confidence: mlPick.confidence,
            model_version: modelVersion,
            reasoning: mlPick.reasoning,
            created_at: new Date().toISOString(),
          });
        }
      }

      // ---- Spread pick
      if (spreads?.outcomes?.length) {
        const homeRow = spreads.outcomes.find((o) => o.name === g.home_team);
        const awayRow = spreads.outcomes.find((o) => o.name === g.away_team);

        const homePoint = typeof homeRow?.point === "number" ? homeRow.point : null;
        const awayPoint = typeof awayRow?.point === "number" ? awayRow.point : null;
        const homePrice = typeof homeRow?.price === "number" ? homeRow.price : null;
        const awayPrice = typeof awayRow?.price === "number" ? awayRow.price : null;

        if (
          homePoint != null && awayPoint != null &&
          homePrice != null && awayPrice != null
        ) {
          const atsPick = pickFromSpread(
            g.home_team,
            g.away_team,
            homePoint,
            homePrice,
            awayPoint,
            awayPrice,
          );

          picks.push({
            sport: "nba",
            event_id: g.id,
            commence_time: g.commence_time,
            home_team: g.home_team,
            away_team: g.away_team,
            pick_market: "spreads",
            pick_side: atsPick.pick_side,
            confidence: atsPick.confidence,
            model_version: modelVersion,
            reasoning: atsPick.reasoning,
            created_at: new Date().toISOString(),
          });
        }
      }
    }

    const { upserted } = await upsertModelPicks(picks);

    return json({
      ok: true,
      preferred_bookmaker: preferredBook,
      model_version: modelVersion,
      games_seen: games.length,
      picks_built: picks.length,
      picks_upserted: upserted,
      note:
        "This is baseline_v1 (odds-derived). Once you have enough game_results rows, we'll swap model_version to nba_v1 and generate confidence from the trained model.",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return json({ ok: false, error: msg }, 500);
  }
});
// supabase/functions/decision-slate/index.ts

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
};

type DecisionPick = {
  game_id: string;
  league: string;
  start_time: string;
  market: "spread" | "moneyline" | "total";
  side: string;
  confidence: number;
  why: string[];
  signals?: {
    line_move?: string;
    public_lean?: string;
    steam?: "for" | "against" | "neutral";
  };
};

type DecisionResponse = {
  date: string;
  generated_at: string;
  top_pick: DecisionPick | null;
  strong_leans: DecisionPick[];
  watchlist: DecisionPick[];
  meta: { version: string; notes?: string };
};

type SlatePickOut = {
  status: "pick" | "no_bet";
  selection?: string;
  confidence?: "low" | "medium" | "high";
  score?: number;
  rationale?: string[];
  reason?: string;
};

type SlateGame = {
  id: string;
  sport: string;
  startTime: string;
  picks: {
    moneyline: SlatePickOut;
    spread: SlatePickOut;
    total: SlatePickOut;
  };
};

function isoNow() {
  return new Date().toISOString();
}

function getDayParam(url: URL) {
  return (url.searchParams.get("day") || "today").toLowerCase();
}

function dayToResponseDate(day: string) {
  if (day === "today") return new Date().toISOString().slice(0, 10);
  return day;
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

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

/**
 * Calibrate 0..100 score into a realistic confidence, with league caps.
 * This prevents "everything is 0.95" when upstream scoring is too hot.
 */
function calibrateConfidence(score: number, league: string): number {
  const s = clamp(score, 0, 100) / 100; // 0..1
  const curved = Math.pow(s, 1.35);

  // Base mapping to [0.52, 0.95]
  let conf = 0.52 + 0.43 * curved;

  // League caps (temporary sanity guard)
  const leagueCap =
    league === "NBA" ? 0.90 :
    league === "NFL" ? 0.92 :
    league === "NCAAF" ? 0.91 :
    league === "NCAAB" ? 0.91 :
    league === "MLB" ? 0.91 :
    league === "NHL" ? 0.92 :
    0.92;

  conf = clamp(conf, 0.52, leagueCap);

  // Round for UI stability (prevents ugly floats)
  return Math.round(conf * 100) / 100;
}

function pickToCandidate(params: {
  game: SlateGame;
  league: string;
  market: "moneyline" | "spread" | "total";
  pick: SlatePickOut;
}): (DecisionPick & { _score: number; _game_id: string }) | null {
  const { game, league, market, pick } = params;

  if (pick.status !== "pick") return null;
  if (!pick.selection) return null;
  if (typeof pick.score !== "number") return null;

  const score = clamp(pick.score, 0, 100);

  return {
    game_id: game.id,
    _game_id: game.id,
    league,
    start_time: game.startTime,
    market,
    side: pick.selection,
    confidence: calibrateConfidence(score, league),
    why: Array.isArray(pick.rationale) ? pick.rationale.slice(0, 5) : [],
    _score: score,
  };
}

function extractAllCandidates(rawSlate: Record<string, SlateGame[]>): Array<DecisionPick & { _score: number; _game_id: string }> {
  const out: Array<DecisionPick & { _score: number; _game_id: string }> = [];

  for (const sportKey of Object.keys(rawSlate || {})) {
    const league = leagueLabelFromSportKey(sportKey);
    const games = rawSlate[sportKey] || [];

    for (const game of games) {
      const markets: Array<"moneyline" | "spread" | "total"> = ["moneyline", "spread", "total"];

      for (const m of markets) {
        const pick = game?.picks?.[m];
        if (!pick) continue;

        const cand = pickToCandidate({
          game,
          league,
          market: normalizeMarket(m),
          pick,
        });

        if (cand) out.push(cand);
      }
    }
  }

  return out;
}

// Option A: ONE pick per game always.
function bestPickPerGame(
  candidates: Array<DecisionPick & { _score: number; _game_id: string }>
): Array<DecisionPick & { _score: number; _game_id: string }> {
  const bestByGame = new Map<string, DecisionPick & { _score: number; _game_id: string }>();

  for (const c of candidates) {
    const existing = bestByGame.get(c._game_id);
    if (!existing || c._score > existing._score) bestByGame.set(c._game_id, c);
  }

  return Array.from(bestByGame.values());
}

const THRESHOLDS = {
  TOP_PICK_MIN_SCORE: 74,
  STRONG_LEAN_MIN_SCORE: 66,
  WATCHLIST_MIN_SCORE: 60,
  MAX_STRONG_LEANS: 5,
  MAX_WATCHLIST: 10,
};

function stripInternal(p: DecisionPick & { _score?: number; _game_id?: string }): DecisionPick {
  // @ts-ignore
  const { _score, _game_id, ...rest } = p;
  return rest;
}

function buildDecisionResponse(params: { day: string; rawSlate: Record<string, SlateGame[]> }): DecisionResponse {
  const { day, rawSlate } = params;

  const all = extractAllCandidates(rawSlate);
  const uniqueByGame = bestPickPerGame(all).sort((a, b) => b._score - a._score);

  const topEligible = uniqueByGame.filter((c) => c._score >= THRESHOLDS.TOP_PICK_MIN_SCORE);
  const strongEligible = uniqueByGame.filter((c) => c._score >= THRESHOLDS.STRONG_LEAN_MIN_SCORE);
  const watchEligible = uniqueByGame.filter((c) => c._score >= THRESHOLDS.WATCHLIST_MIN_SCORE);

  const top_pick = topEligible.length ? stripInternal(topEligible[0]) : null;

  const topGameId = top_pick?.game_id ?? null;

  const strong_leans = strongEligible
    .filter((c) => (topGameId ? c.game_id !== topGameId : true))
    .slice(0, THRESHOLDS.MAX_STRONG_LEANS)
    .map(stripInternal);

  const usedGameIds = new Set<string>();
  if (topGameId) usedGameIds.add(topGameId);
  for (const p of strong_leans) usedGameIds.add(p.game_id);

  const watchlist = watchEligible
    .filter((c) => !usedGameIds.has(c.game_id))
    .slice(0, THRESHOLDS.MAX_WATCHLIST)
    .map(stripInternal);

  return {
    date: dayToResponseDate(day),
    generated_at: isoNow(),
    top_pick,
    strong_leans,
    watchlist,
    meta: {
      version: "decision-slate/v1",
      notes: "live_from_slate-with-picks|one-pick-per-game|league-capped-confidence",
    },
  };
}

async function fetchSlateWithPicks(day: string): Promise<Record<string, SlateGame[]>> {
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRole = Deno.env.get("SERVICE_ROLE_KEY");

  if (!supabaseUrl) throw new Error("SUPABASE_URL not configured in Edge Function env");
  if (!serviceRole) throw new Error('Missing SERVICE_ROLE_KEY. Set via: supabase secrets set SERVICE_ROLE_KEY="..."');

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
    const text = await res.text();
    throw new Error(`slate-with-picks failed: ${res.status} ${text}`);
  }

  return await res.json();
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const url = new URL(req.url);
    const day = getDayParam(url);

    const rawSlate = await fetchSlateWithPicks(day);
    const res = buildDecisionResponse({ day, rawSlate });

    return new Response(JSON.stringify(res), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ error: "decision-slate failed", message: err instanceof Error ? err.message : String(err) }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
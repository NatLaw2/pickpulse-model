import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};

// UI sport keys to Odds API sport keys mapping
const SPORT_MAPPING: Record<string, string> = {
  nba: "basketball_nba",
  mlb: "baseball_mlb",
  nhl: "icehockey_nhl",
  ncaab: "basketball_ncaab",
  ncaaf: "americanfootball_ncaaf",
  nfl: "americanfootball_nfl",
};

const UI_SPORTS = ["nba", "mlb", "nhl", "ncaab", "ncaaf", "nfl"] as const;

type UISport = (typeof UI_SPORTS)[number];
type ConfidenceTier = "low" | "medium" | "high";
type MarketStatus = "pick" | "no_bet";

interface OddsApiEvent {
  id: string;
  sport_key: string;
  sport_title: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmakers: Array<{
    key: string;
    title: string;
    markets: Array<{
      key: string;
      outcomes: Array<{
        name: string;
        price: number;
        point?: number;
      }>;
    }>;
  }>;
}

interface PickOut {
  status: MarketStatus;
  selection?: string;
  confidence?: ConfidenceTier;
  score?: number;
  rationale?: string[];
  reason?: string;
}

interface TransformedGame {
  id: string;
  sport: UISport;
  homeTeam: { name: string; abbreviation: string };
  awayTeam: { name: string; abbreviation: string };
  startTime: string;
  odds: {
    moneyline: { home: number | null; away: number | null } | null;
    spread: {
      home: { point: number; price: number } | null;
      away: { point: number; price: number } | null;
    } | null;
    total: {
      over: { point: number; price: number } | null;
      under: { point: number; price: number } | null;
    } | null;
  };
  picks: {
    moneyline: PickOut;
    spread: PickOut;
    total: PickOut;
  };
}

// ---------------------------
// Helpers: ET day filtering
// ---------------------------
function etDateKey(date: Date): string {
  // Returns YYYY-MM-DD in America/New_York (DST-safe)
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);

  const y = parts.find((p) => p.type === "year")?.value ?? "0000";
  const m = parts.find((p) => p.type === "month")?.value ?? "01";
  const d = parts.find((p) => p.type === "day")?.value ?? "01";
  return `${y}-${m}-${d}`;
}

function addDaysToEtDateKey(baseEtKey: string, addDays: number): string {
  // baseEtKey: YYYY-MM-DD. We interpret this as a date-only and add days in UTC safely.
  // Then we re-render to ET date key. This avoids DST issues because we only care about date.
  const [y, m, d] = baseEtKey.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d, 12, 0, 0)); // noon UTC avoids edge issues
  dt.setUTCDate(dt.getUTCDate() + addDays);
  return etDateKey(dt);
}

function targetEtDayKey(day: string): string {
  const todayEt = etDateKey(new Date());
  if (day === "tomorrow") return addDaysToEtDateKey(todayEt, 1);
  if (day === "nextDay") return addDaysToEtDateKey(todayEt, 2);
  return todayEt;
}

// ---------------------------
// Helpers: abbreviations
// ---------------------------
function getTeamAbbreviation(teamName: string): string {
  const abbreviations: Record<string, string> = {
    "Los Angeles Lakers": "LAL",
    "Golden State Warriors": "GSW",
    "Boston Celtics": "BOS",
    "Miami Heat": "MIA",
    "Phoenix Suns": "PHX",
    "Denver Nuggets": "DEN",
    "Milwaukee Bucks": "MIL",
    "Philadelphia 76ers": "PHI",
    "New York Yankees": "NYY",
    "Los Angeles Dodgers": "LAD",
    "Houston Astros": "HOU",
    "Atlanta Braves": "ATL",
    "San Diego Padres": "SD",
    "Philadelphia Phillies": "PHI",
    "Colorado Avalanche": "COL",
    "Tampa Bay Lightning": "TBL",
    "Toronto Maple Leafs": "TOR",
    "Vegas Golden Knights": "VGK",
    "Boston Bruins": "BOS",
    "Edmonton Oilers": "EDM",
    "Kansas City Chiefs": "KC",
    "Philadelphia Eagles": "PHI",
    "Buffalo Bills": "BUF",
    "San Francisco 49ers": "SF",
    "Dallas Cowboys": "DAL",
    "Cincinnati Bengals": "CIN",
  };

  return (
    abbreviations[teamName] ||
    teamName
      .split(" ")
      .map((w) => w[0])
      .join("")
      .slice(0, 4)
      .toUpperCase()
  );
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

function tier(score: number): ConfidenceTier {
  if (score >= 75) return "high";
  if (score >= 60) return "medium";
  return "low";
}

// ---------------------------
// Odds aggregation across books (for model signals)
// ---------------------------
const preferredBooks = ["fanduel", "draftkings", "betmgm", "bovada"];

function getPreferredBookmakers(bookmakers: OddsApiEvent["bookmakers"]) {
  if (!bookmakers?.length) return [];
  const ordered = [...bookmakers].sort((a, b) => {
    const ai = preferredBooks.indexOf(a.key);
    const bi = preferredBooks.indexOf(b.key);
    const ar = ai === -1 ? 999 : ai;
    const br = bi === -1 ? 999 : bi;
    return ar - br;
  });
  return ordered;
}

function extractMoneylineAcrossBooks(event: OddsApiEvent) {
  const lines: Array<{ book: string; home: number | null; away: number | null }> = [];
  for (const b of event.bookmakers || []) {
    const m = b.markets?.find((x) => x.key === "h2h");
    if (!m) continue;
    const homeOutcome = m.outcomes.find((o) => o.name === event.home_team);
    const awayOutcome = m.outcomes.find((o) => o.name === event.away_team);
    lines.push({
      book: b.key,
      home: homeOutcome?.price ?? null,
      away: awayOutcome?.price ?? null,
    });
  }
  return lines;
}

function extractSpreadAcrossBooks(event: OddsApiEvent) {
  const lines: Array<{
    book: string;
    homePoint: number | null;
    homePrice: number | null;
    awayPoint: number | null;
    awayPrice: number | null;
  }> = [];
  for (const b of event.bookmakers || []) {
    const m = b.markets?.find((x) => x.key === "spreads");
    if (!m) continue;
    const homeOutcome = m.outcomes.find((o) => o.name === event.home_team);
    const awayOutcome = m.outcomes.find((o) => o.name === event.away_team);
    lines.push({
      book: b.key,
      homePoint: homeOutcome?.point ?? null,
      homePrice: homeOutcome?.price ?? null,
      awayPoint: awayOutcome?.point ?? null,
      awayPrice: awayOutcome?.price ?? null,
    });
  }
  return lines;
}

function extractTotalAcrossBooks(event: OddsApiEvent) {
  const lines: Array<{ book: string; point: number | null; overPrice: number | null; underPrice: number | null }> = [];
  for (const b of event.bookmakers || []) {
    const m = b.markets?.find((x) => x.key === "totals");
    if (!m) continue;
    const overOutcome = m.outcomes.find((o) => o.name === "Over");
    const underOutcome = m.outcomes.find((o) => o.name === "Under");
    lines.push({
      book: b.key,
      point: overOutcome?.point ?? underOutcome?.point ?? null,
      overPrice: overOutcome?.price ?? null,
      underPrice: underOutcome?.price ?? null,
    });
  }
  return lines;
}

// Basic signals for v1
function scoreMarket(params: { variance: number | null; juice: number | null; bestEdge: number; pickText: string }): {
  score: number;
  rationale: string[];
} {
  let score = 50;
  const rationale: string[] = [];

  const { variance, juice, bestEdge } = params;

  // Book agreement / disagreement
  if (variance !== null) {
    if (variance <= 0.5) {
      score += 10;
      rationale.push("Books largely agree on this line");
    } else if (variance >= 1.5) {
      score -= 10;
      rationale.push("Books disagree (high variance)");
    }
  }

  // Juice sanity
  if (typeof juice === "number") {
    if (juice <= -130) {
      score -= 10;
      rationale.push("Heavily juiced price reduces value");
    } else if (juice >= -120 && juice <= -105) {
      score += 5;
      rationale.push("Standard pricing (~-110)");
    }
  }

  // Line-shopping edge
  if (bestEdge >= 0.5) {
    score += 5;
    rationale.push("Meaningful line-shopping edge available");
  }

  score = clamp(score, 0, 100);
  return { score, rationale: rationale.slice(0, 5) };
}

// ---------------------------
// Decide picks (v1 heuristics)
// ---------------------------
function buildRecommendation(event: OddsApiEvent): { moneyline: PickOut; spread: PickOut; total: PickOut } {
  // Moneyline: choose side with better (less negative / more positive) price among preferred books (if available)
  const mlLines = extractMoneylineAcrossBooks(event);

  const bestBookOrder = getPreferredBookmakers(event.bookmakers);
  const preferred = bestBookOrder[0]?.key;

  // For UI odds display, we keep a single book (preferred) but model uses all books
  // Compute moneyline pick
  let moneyline: PickOut = { status: "no_bet", reason: "Market unavailable" };
  const mlValid = mlLines.filter((x) => x.home !== null && x.away !== null);
  if (mlValid.length > 0) {
    // compute "variance" as spread between best and worst for the chosen side
    // pick side by comparing average prices (simple)
    const homePrices = mlValid.map((x) => x.home as number);
    const awayPrices = mlValid.map((x) => x.away as number);

    const avg = (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length;
    const avgHome = avg(homePrices);
    const avgAway = avg(awayPrices);

    const pickSide = avgHome >= avgAway ? "home" : "away"; // higher is better for bettor (e.g., -105 > -120)
    const juice = pickSide === "home" ? Math.max(...homePrices) : Math.max(...awayPrices); // best price
    const variance =
      pickSide === "home"
        ? Math.max(...homePrices) - Math.min(...homePrices)
        : Math.max(...awayPrices) - Math.min(...awayPrices);

    // bestEdge is 0 for ML in v1
    const pickText =
      pickSide === "home" ? `${getTeamAbbreviation(event.home_team)} ML` : `${getTeamAbbreviation(event.away_team)} ML`;
    const { score, rationale } = scoreMarket({ variance, juice, bestEdge: 0, pickText });

    if (score < 60) {
      moneyline = { status: "no_bet", reason: "Insufficient edge / conflicting market signals", score };
    } else {
      moneyline = { status: "pick", selection: pickText, confidence: tier(score), score, rationale };
    }
  }

  // Spread: choose the side with the better number (more points) using average lines; assess variance + bestEdge vs average
  let spread: PickOut = { status: "no_bet", reason: "Market unavailable" };
  const spLines = extractSpreadAcrossBooks(event);
  const spValid = spLines.filter((x) => x.homePoint !== null && x.awayPoint !== null);

  if (spValid.length > 0) {
    const homePoints = spValid.map((x) => x.homePoint as number);
    const awayPoints = spValid.map((x) => x.awayPoint as number);

    const avg = (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length;
    const avgHome = avg(homePoints);
    const avgAway = avg(awayPoints);

    // Prefer the side getting more points (higher number)
    const pickSide = avgHome >= avgAway ? "home" : "away";
    const pickPointsAvg = pickSide === "home" ? avgHome : avgAway;

    // Best edge: best available point (max) - average point, if >= 0.5
    const bestPoint = pickSide === "home" ? Math.max(...homePoints) : Math.max(...awayPoints);

    const bestEdge = bestPoint - pickPointsAvg;

    // Juice: best price from preferred books for that side (fallback any)
    const priceCandidates = spValid
      .map((x) => (pickSide === "home" ? x.homePrice : x.awayPrice))
      .filter((p) => typeof p === "number") as number[];

    const juice = priceCandidates.length ? Math.max(...priceCandidates) : null;

    // Variance on points across books
    const variance =
      pickSide === "home"
        ? Math.max(...homePoints) - Math.min(...homePoints)
        : Math.max(...awayPoints) - Math.min(...awayPoints);

    const teamAbbr = pickSide === "home" ? getTeamAbbreviation(event.home_team) : getTeamAbbreviation(event.away_team);
    const pointStr = bestPoint > 0 ? `+${bestPoint}` : `${bestPoint}`;
    const pickText = `${teamAbbr} ${pointStr}`;

    const { score, rationale } = scoreMarket({ variance, juice, bestEdge, pickText });

    if (score < 60) {
      spread = { status: "no_bet", reason: "Insufficient edge / conflicting market signals", score };
    } else {
      spread = { status: "pick", selection: pickText, confidence: tier(score), score, rationale };
    }
  }

  // Total: choose over/under based on better price at the consensus point, use variance on point; bestEdge vs average
  let total: PickOut = { status: "no_bet", reason: "Market unavailable" };
  const totLines = extractTotalAcrossBooks(event);
  const totValid = totLines.filter((x) => x.point !== null);

  if (totValid.length > 0) {
    const points = totValid.map((x) => x.point as number);
    const avg = (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length;
    const avgPoint = avg(points);

    const maxPoint = Math.max(...points);
    const bestEdge = maxPoint - avgPoint; // if one book offers a higher total (edge if you like under, but v1 treats as generic edge)

    // Determine pick direction by price: if under price is better than over price on average => pick under, else over
    const overPrices = totValid.map((x) => x.overPrice).filter((p) => typeof p === "number") as number[];
    const underPrices = totValid.map((x) => x.underPrice).filter((p) => typeof p === "number") as number[];

    const avgOver = overPrices.length ? avg(overPrices) : null;
    const avgUnder = underPrices.length ? avg(underPrices) : null;

    let pickSide: "over" | "under" = "under";
    if (avgOver !== null && avgUnder !== null) {
      pickSide = avgUnder >= avgOver ? "under" : "over";
    } else if (avgOver !== null && avgUnder === null) {
      pickSide = "over";
    } else if (avgUnder !== null && avgOver === null) {
      pickSide = "under";
    }

    // Use best price (max) for chosen side
    const juice =
      pickSide === "under"
        ? underPrices.length
          ? Math.max(...underPrices)
          : null
        : overPrices.length
          ? Math.max(...overPrices)
          : null;

    const variance = Math.max(...points) - Math.min(...points);

    const pointToUse = maxPoint; // show best available point
    const pickText = pickSide === "under" ? `UNDER ${pointToUse}` : `OVER ${pointToUse}`;

    const { score, rationale } = scoreMarket({ variance, juice, bestEdge, pickText });

    if (score < 60) {
      total = { status: "no_bet", reason: "Insufficient edge / conflicting market signals", score };
    } else {
      total = { status: "pick", selection: pickText, confidence: tier(score), score, rationale };
    }
  }

  return { moneyline, spread, total };
}

// For display odds, pick preferred bookmaker then fallback
function extractDisplayOdds(event: OddsApiEvent) {
  const orderedBooks = getPreferredBookmakers(event.bookmakers);
  const book = orderedBooks[0] || event.bookmakers?.[0];

  let moneyline = null;
  let spread = null;
  let total = null;

  if (book) {
    const h2hMarket = book.markets.find((m) => m.key === "h2h");
    if (h2hMarket) {
      const homeOutcome = h2hMarket.outcomes.find((o) => o.name === event.home_team);
      const awayOutcome = h2hMarket.outcomes.find((o) => o.name === event.away_team);
      moneyline = { home: homeOutcome?.price ?? null, away: awayOutcome?.price ?? null };
    }

    const spreadMarket = book.markets.find((m) => m.key === "spreads");
    if (spreadMarket) {
      const homeOutcome = spreadMarket.outcomes.find((o) => o.name === event.home_team);
      const awayOutcome = spreadMarket.outcomes.find((o) => o.name === event.away_team);
      spread = {
        home: homeOutcome ? { point: homeOutcome.point ?? 0, price: homeOutcome.price } : null,
        away: awayOutcome ? { point: awayOutcome.point ?? 0, price: awayOutcome.price } : null,
      };
    }

    const totalsMarket = book.markets.find((m) => m.key === "totals");
    if (totalsMarket) {
      const overOutcome = totalsMarket.outcomes.find((o) => o.name === "Over");
      const underOutcome = totalsMarket.outcomes.find((o) => o.name === "Under");
      total = {
        over: overOutcome ? { point: overOutcome.point ?? 0, price: overOutcome.price } : null,
        under: underOutcome ? { point: underOutcome.point ?? 0, price: underOutcome.price } : null,
      };
    }
  }

  return { moneyline, spread, total };
}

function transformEvent(event: OddsApiEvent, uiSport: UISport): TransformedGame {
  const odds = extractDisplayOdds(event);
  const recommendation = buildRecommendation(event);

  return {
    id: event.id,
    sport: uiSport,
    homeTeam: { name: event.home_team, abbreviation: getTeamAbbreviation(event.home_team) },
    awayTeam: { name: event.away_team, abbreviation: getTeamAbbreviation(event.away_team) },
    startTime: event.commence_time,
    odds,
    picks: recommendation, // Use 'picks' to match frontend type expectations
  };
}

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    console.log("slate-with-picks: Request received", req.method);
    
    // Read day from body (POST) or query params (GET)
    let day = "today";
    if (req.method === "POST") {
      try {
        const body = await req.json();
        day = body?.day || body?.dateFilter || "today";
        console.log("slate-with-picks: Parsed body, day =", day);
      } catch {
        console.log("slate-with-picks: No body or invalid JSON, using default day");
      }
    } else {
      const url = new URL(req.url);
      day = url.searchParams.get("day") || "today";
    }
    
    const targetDayKey = targetEtDayKey(day);
    console.log("slate-with-picks: Target day key =", targetDayKey);

    const ODDS_API_KEY = Deno.env.get("ODDS_API_KEY");
    if (!ODDS_API_KEY) throw new Error("ODDS_API_KEY not configured");

    const results: Record<UISport, TransformedGame[]> = {
      nba: [],
      mlb: [],
      nhl: [],
      ncaab: [],
      ncaaf: [],
      nfl: [],
    };

    const fetchPromises = UI_SPORTS.map(async (uiSport) => {
      const apiSport = SPORT_MAPPING[uiSport];
      const apiUrl =
        `https://api.the-odds-api.com/v4/sports/${apiSport}/odds/?apiKey=${ODDS_API_KEY}` +
        `&regions=us&markets=h2h,spreads,totals&oddsFormat=american&dateFormat=iso`;

      try {
        const response = await fetch(apiUrl);
        if (!response.ok) {
          console.error(`Failed to fetch ${uiSport}: ${response.status}`);
          return { sport: uiSport, games: [] as TransformedGame[] };
        }

        const events: OddsApiEvent[] = await response.json();

        const filteredGames = events
          .filter((event) => etDateKey(new Date(event.commence_time)) === targetDayKey)
          .map((event) => transformEvent(event, uiSport));

        return { sport: uiSport, games: filteredGames };
      } catch (err) {
        console.error(`Error fetching ${uiSport}:`, err);
        return { sport: uiSport, games: [] as TransformedGame[] };
      }
    });

    const all = await Promise.all(fetchPromises);
    for (const r of all) results[r.sport] = r.games;

    return new Response(JSON.stringify(results), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (error: unknown) {
    console.error("Slate-with-picks error:", error);
    const message = error instanceof Error ? error.message : "Internal server error";
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});

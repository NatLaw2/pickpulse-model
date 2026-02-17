import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
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

const LEAGUE_LABELS: Record<string, string> = {
  nba: "NBA",
  mlb: "MLB",
  nhl: "NHL",
  ncaab: "NCAAB",
  ncaaf: "NCAAF",
  nfl: "NFL",
};

const UI_SPORTS = ["nba", "mlb", "nhl", "ncaab", "ncaaf", "nfl"] as const;

// ============= Team Signals Data (editable in-function for now) =============
// Status: normal | key_out | questionable_qb | injury_concerns
// Impact: 0-15 adjustment to score
interface TeamSignal {
  status: string;
  impact: number;
  notes: string[];
}

const TEAM_SIGNALS: Record<string, Record<string, TeamSignal>> = {
  NBA: {
    LAL: { status: "normal", impact: 0, notes: [] },
    BOS: { status: "normal", impact: 0, notes: [] },
  },
  NFL: {
    BUF: { status: "normal", impact: 0, notes: [] },
    KC: { status: "normal", impact: 0, notes: [] },
  },
  MLB: {},
  NHL: {},
  NCAAB: {},
  NCAAF: {},
};

// ============= Types =============
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

interface PickResult {
  status: "pick" | "no_bet";
  selection?: string;
  confidence?: "low" | "medium" | "high";
  score?: number;
  rationale?: string[];
  reason?: string;
}

interface TransformedGame {
  id: string;
  sport: string;
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
    moneyline: PickResult | null;
    spread: PickResult | null;
    total: PickResult | null;
  };
}

interface MarketAnalysis {
  selectionText: string;
  leanTeam: "home" | "away" | null;
  variance: number;
  juice: number;
  bestEdge: number;
  bestPrice: number;
  avgPrice: number;
  allPrices: number[];
  allPoints?: number[];
}

// This is what your Render service returns (per openapi.json)
interface ModelRecommendResponse {
  byGameId: Record<
    string,
    {
      moneyline: PickResult;
      spread: PickResult;
      total: PickResult;
    }
  >;
}

// ============= Utility Functions =============
function getTeamAbbreviation(teamName: string): string {
  const abbreviations: Record<string, string> = {
    // NBA
    "Los Angeles Lakers": "LAL",
    "Golden State Warriors": "GSW",
    "Boston Celtics": "BOS",
    "Miami Heat": "MIA",
    "Phoenix Suns": "PHX",
    "Denver Nuggets": "DEN",
    "Milwaukee Bucks": "MIL",
    "Philadelphia 76ers": "PHI",
    "New York Knicks": "NYK",
    "Brooklyn Nets": "BKN",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Detroit Pistons": "DET",
    "Indiana Pacers": "IND",
    "Atlanta Hawks": "ATL",
    "Charlotte Hornets": "CHA",
    "Orlando Magic": "ORL",
    "Washington Wizards": "WAS",
    "Toronto Raptors": "TOR",
    "Dallas Mavericks": "DAL",
    "Houston Rockets": "HOU",
    "Memphis Grizzlies": "MEM",
    "New Orleans Pelicans": "NOP",
    "San Antonio Spurs": "SAS",
    "Minnesota Timberwolves": "MIN",
    "Oklahoma City Thunder": "OKC",
    "Portland Trail Blazers": "POR",
    "Utah Jazz": "UTA",
    "Sacramento Kings": "SAC",
    "Los Angeles Clippers": "LAC",

    // NFL (partial)
    "Kansas City Chiefs": "KC",
    "Philadelphia Eagles": "PHI",
    "Buffalo Bills": "BUF",
    "San Francisco 49ers": "SF",
    "Dallas Cowboys": "DAL",
    "Cincinnati Bengals": "CIN",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Green Bay Packers": "GB",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "New England Patriots": "NE",
    "Baltimore Ravens": "BAL",
    "Pittsburgh Steelers": "PIT",
    "Cleveland Browns": "CLE",
    "Denver Broncos": "DEN",
    "Minnesota Vikings": "MIN",
    "Chicago Bears": "CHI",
    "Detroit Lions": "DET",
    "Arizona Cardinals": "ARI",
    "Carolina Panthers": "CAR",
    "Jacksonville Jaguars": "JAX",
    "Tennessee Titans": "TEN",
    "Indianapolis Colts": "IND",
    "Houston Texans": "HOU",
    "Miami Dolphins": "MIA",
    "New Orleans Saints": "NO",
    "Atlanta Falcons": "ATL",
    "Washington Commanders": "WSH",

    // NHL (partial)
    "Colorado Avalanche": "COL",
    "Tampa Bay Lightning": "TBL",
    "Toronto Maple Leafs": "TOR",
    "Vegas Golden Knights": "VGK",
    "Boston Bruins": "BOS",
    "Edmonton Oilers": "EDM",
    "Anaheim Ducks": "ANA",
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

function isGameInWindow(
  gameTime: string,
  windowStart: Date,
  windowEnd: Date,
): boolean {
  const gameDate = new Date(gameTime);
  return gameDate >= windowStart && gameDate < windowEnd;
}

// Each "day" runs from 4 AM ET to 4 AM ET next day (9 AM UTC to 9 AM UTC)
function getDateWindow(day: string): { start: Date; end: Date } {
  const now = new Date();
  const estOffset = -5;
  const dayStartHourUTC = 4 - estOffset;

  const todayStart = new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate(),
      dayStartHourUTC,
      0,
      0,
      0,
    ),
  );

  if (now < todayStart) {
    todayStart.setUTCDate(todayStart.getUTCDate() - 1);
  }

  const todayEnd = new Date(todayStart);
  todayEnd.setUTCDate(todayEnd.getUTCDate() + 1);

  switch (day) {
    case "tomorrow": {
      const start = new Date(todayEnd);
      const end = new Date(start);
      end.setUTCDate(end.getUTCDate() + 1);
      return { start, end };
    }
    case "nextDay": {
      const start = new Date(todayEnd);
      start.setUTCDate(start.getUTCDate() + 1);
      const end = new Date(start);
      end.setUTCDate(end.getUTCDate() + 1);
      return { start, end };
    }
    case "today":
    default:
      return { start: todayStart, end: todayEnd };
  }
}

// ============= Market Analysis Functions =============
function analyzeMoneyline(
  event: OddsApiEvent,
): { home: MarketAnalysis | null; away: MarketAnalysis | null } {
  const homePrices: number[] = [];
  const awayPrices: number[] = [];

  for (const book of event.bookmakers) {
    const market = book.markets.find((m) => m.key === "h2h");
    if (!market) continue;

    const homeOutcome = market.outcomes.find((o) => o.name === event.home_team);
    const awayOutcome = market.outcomes.find((o) => o.name === event.away_team);

    if (homeOutcome) homePrices.push(homeOutcome.price);
    if (awayOutcome) awayPrices.push(awayOutcome.price);
  }

  if (homePrices.length === 0 || awayPrices.length === 0) {
    return { home: null, away: null };
  }

  const homeAbbr = getTeamAbbreviation(event.home_team);
  const awayAbbr = getTeamAbbreviation(event.away_team);

  const homeBest = Math.max(...homePrices);
  const homeAvg = homePrices.reduce((a, b) => a + b, 0) / homePrices.length;
  const homeVariance = Math.max(...homePrices) - Math.min(...homePrices);

  const awayBest = Math.max(...awayPrices);
  const awayAvg = awayPrices.reduce((a, b) => a + b, 0) / awayPrices.length;
  const awayVariance = Math.max(...awayPrices) - Math.min(...awayPrices);

  return {
    home: {
      selectionText: `${homeAbbr} ML`,
      leanTeam: "home",
      variance: homeVariance,
      juice: homeBest,
      bestEdge: Math.abs(homeBest - homeAvg),
      bestPrice: homeBest,
      avgPrice: homeAvg,
      allPrices: homePrices,
    },
    away: {
      selectionText: `${awayAbbr} ML`,
      leanTeam: "away",
      variance: awayVariance,
      juice: awayBest,
      bestEdge: Math.abs(awayBest - awayAvg),
      bestPrice: awayBest,
      avgPrice: awayAvg,
      allPrices: awayPrices,
    },
  };
}

function analyzeSpread(
  event: OddsApiEvent,
): { home: MarketAnalysis | null; away: MarketAnalysis | null } {
  const homePoints: number[] = [];
  const homePrices: number[] = [];
  const awayPoints: number[] = [];
  const awayPrices: number[] = [];

  for (const book of event.bookmakers) {
    const market = book.markets.find((m) => m.key === "spreads");
    if (!market) continue;

    const homeOutcome = market.outcomes.find((o) => o.name === event.home_team);
    const awayOutcome = market.outcomes.find((o) => o.name === event.away_team);

    if (homeOutcome && homeOutcome.point !== undefined) {
      homePoints.push(homeOutcome.point);
      homePrices.push(homeOutcome.price);
    }
    if (awayOutcome && awayOutcome.point !== undefined) {
      awayPoints.push(awayOutcome.point);
      awayPrices.push(awayOutcome.price);
    }
  }

  if (homePoints.length === 0 || awayPoints.length === 0) {
    return { home: null, away: null };
  }

  const homeAbbr = getTeamAbbreviation(event.home_team);
  const awayAbbr = getTeamAbbreviation(event.away_team);

  const homeAvgPoint = homePoints.reduce((a, b) => a + b, 0) / homePoints.length;
  const homeBestPrice = Math.max(...homePrices);
  const homePointVariance = Math.max(...homePoints) - Math.min(...homePoints);
  const homeBestPoint = homeAvgPoint < 0 ? Math.min(...homePoints) : Math.max(...homePoints);
  const homeBestEdge = Math.abs(homeBestPoint - homeAvgPoint);

  const awayAvgPoint = awayPoints.reduce((a, b) => a + b, 0) / awayPoints.length;
  const awayBestPrice = Math.max(...awayPrices);
  const awayPointVariance = Math.max(...awayPoints) - Math.min(...awayPoints);
  const awayBestPoint = awayAvgPoint < 0 ? Math.min(...awayPoints) : Math.max(...awayPoints);
  const awayBestEdge = Math.abs(awayBestPoint - awayAvgPoint);

  return {
    home: {
      selectionText: `${homeAbbr} ${homeAvgPoint > 0 ? "+" : ""}${homeAvgPoint.toFixed(1)}`,
      leanTeam: "home",
      variance: homePointVariance,
      juice: homeBestPrice,
      bestEdge: homeBestEdge,
      bestPrice: homeBestPrice,
      avgPrice: homePrices.reduce((a, b) => a + b, 0) / homePrices.length,
      allPrices: homePrices,
      allPoints: homePoints,
    },
    away: {
      selectionText: `${awayAbbr} ${awayAvgPoint > 0 ? "+" : ""}${awayAvgPoint.toFixed(1)}`,
      leanTeam: "away",
      variance: awayPointVariance,
      juice: awayBestPrice,
      bestEdge: awayBestEdge,
      bestPrice: awayBestPrice,
      avgPrice: awayPrices.reduce((a, b) => a + b, 0) / awayPrices.length,
      allPrices: awayPrices,
      allPoints: awayPoints,
    },
  };
}

function analyzeTotal(
  event: OddsApiEvent,
): { over: MarketAnalysis | null; under: MarketAnalysis | null } {
  const overPoints: number[] = [];
  const overPrices: number[] = [];
  const underPoints: number[] = [];
  const underPrices: number[] = [];

  for (const book of event.bookmakers) {
    const market = book.markets.find((m) => m.key === "totals");
    if (!market) continue;

    const overOutcome = market.outcomes.find((o) => o.name === "Over");
    const underOutcome = market.outcomes.find((o) => o.name === "Under");

    if (overOutcome && overOutcome.point !== undefined) {
      overPoints.push(overOutcome.point);
      overPrices.push(overOutcome.price);
    }
    if (underOutcome && underOutcome.point !== undefined) {
      underPoints.push(underOutcome.point);
      underPrices.push(underOutcome.price);
    }
  }

  if (overPoints.length === 0 || underPoints.length === 0) {
    return { over: null, under: null };
  }

  const overAvgPoint = overPoints.reduce((a, b) => a + b, 0) / overPoints.length;
  const overBestPrice = Math.max(...overPrices);
  const overPointVariance = Math.max(...overPoints) - Math.min(...overPoints);
  const overBestPoint = Math.min(...overPoints); // Lower total = better for over
  const overBestEdge = Math.abs(overBestPoint - overAvgPoint);

  const underAvgPoint = underPoints.reduce((a, b) => a + b, 0) / underPoints.length;
  const underBestPrice = Math.max(...underPrices);
  const underPointVariance = Math.max(...underPoints) - Math.min(...underPoints);
  const underBestPoint = Math.max(...underPoints); // Higher total = better for under
  const underBestEdge = Math.abs(underBestPoint - underAvgPoint);

  return {
    over: {
      selectionText: `OVER ${overAvgPoint.toFixed(1)}`,
      leanTeam: null,
      variance: overPointVariance,
      juice: overBestPrice,
      bestEdge: overBestEdge,
      bestPrice: overBestPrice,
      avgPrice: overPrices.reduce((a, b) => a + b, 0) / overPrices.length,
      allPrices: overPrices,
      allPoints: overPoints,
    },
    under: {
      selectionText: `UNDER ${underAvgPoint.toFixed(1)}`,
      leanTeam: null,
      variance: underPointVariance,
      juice: underBestPrice,
      bestEdge: underBestEdge,
      bestPrice: underBestPrice,
      avgPrice: underPrices.reduce((a, b) => a + b, 0) / underPrices.length,
      allPrices: underPrices,
      allPoints: underPoints,
    },
  };
}

// ============= Scoring Logic =============
function getTeamSignal(league: string, teamAbbr: string): TeamSignal {
  const leagueSignals = TEAM_SIGNALS[league] || {};
  return leagueSignals[teamAbbr] || { status: "normal", impact: 0, notes: [] };
}

function evaluateMarket(
  analysis: MarketAnalysis,
  league: string,
  homeAbbr: string,
  awayAbbr: string,
  marketType: "moneyline" | "spread" | "total",
): PickResult {
  let score = 50; // Base score
  const rationale: string[] = [];

  // 1. Book agreement analysis
  if (analysis.variance < 10) {
    score += 10;
    rationale.push("Strong book consensus on line");
  } else if (analysis.variance > 30) {
    score -= 10;
    rationale.push("High variance between books - uncertain market");
  }

  // 2. Juice analysis (American odds)
  const juice = analysis.juice;
  if (juice >= -110 && juice <= -105) {
    score += 5;
    rationale.push("Standard juice indicates fair line");
  } else if (juice <= -130) {
    score -= 10;
    rationale.push("Heavy juice on this selection");
  } else if (juice > -105) {
    score += 8;
    rationale.push("Plus-money or light juice value");
  }

  // 3. Line-shopping edge
  if (analysis.bestEdge >= 0.5) {
    score += 5;
    rationale.push(`Line-shopping edge: ${analysis.bestEdge.toFixed(1)} pts available`);
  }

  // 4. Apply team signals
  if (marketType === "total") {
    const homeSignal = getTeamSignal(league, homeAbbr);
    const awaySignal = getTeamSignal(league, awayAbbr);
    const totalImpact = Math.round((homeSignal.impact + awaySignal.impact) / 2);
    if (totalImpact !== 0) {
      score -= totalImpact;
      const notes = [...homeSignal.notes, ...awaySignal.notes];
      rationale.push(...notes.slice(0, 2));
    }
  } else if (analysis.leanTeam) {
    const teamAbbr = analysis.leanTeam === "home" ? homeAbbr : awayAbbr;
    const signal = getTeamSignal(league, teamAbbr);
    if (signal.impact !== 0) {
      score -= signal.impact;
      rationale.push(...signal.notes.slice(0, 2));
    }
  }

  score = Math.max(0, Math.min(100, score));

  if (score < 60) {
    return {
      status: "no_bet",
      reason: score < 40
        ? "Significant concerns with this market"
        : "Not enough edge to justify a play",
      score,
    };
  }

  let confidence: "low" | "medium" | "high";
  if (score >= 75) confidence = "high";
  else if (score >= 60) confidence = "medium";
  else confidence = "low";

  return {
    status: "pick",
    selection: analysis.selectionText,
    confidence,
    score,
    rationale: rationale.slice(0, 5),
  };
}

function generatePicks(
  event: OddsApiEvent,
  uiSport: string,
): { moneyline: PickResult | null; spread: PickResult | null; total: PickResult | null } {
  const league = LEAGUE_LABELS[uiSport];
  const homeAbbr = getTeamAbbreviation(event.home_team);
  const awayAbbr = getTeamAbbreviation(event.away_team);

  const mlAnalysis = analyzeMoneyline(event);
  const spreadAnalysis = analyzeSpread(event);
  const totalAnalysis = analyzeTotal(event);

  let moneylinePick: PickResult | null = null;
  let spreadPick: PickResult | null = null;
  let totalPick: PickResult | null = null;

  if (mlAnalysis.home && mlAnalysis.away) {
    const homeIsFavorite = mlAnalysis.home.bestPrice < mlAnalysis.away.bestPrice;
    const favoriteAnalysis = homeIsFavorite ? mlAnalysis.home : mlAnalysis.away;
    const underdogAnalysis = homeIsFavorite ? mlAnalysis.away : mlAnalysis.home;

    if (underdogAnalysis.bestPrice > 0 && underdogAnalysis.bestPrice <= 200) {
      moneylinePick = evaluateMarket(underdogAnalysis, league, homeAbbr, awayAbbr, "moneyline");
    } else {
      moneylinePick = evaluateMarket(favoriteAnalysis, league, homeAbbr, awayAbbr, "moneyline");
    }
  }

  if (spreadAnalysis.home) {
    spreadPick = evaluateMarket(spreadAnalysis.home, league, homeAbbr, awayAbbr, "spread");
  }

  if (totalAnalysis.over && totalAnalysis.under) {
    const overPick = evaluateMarket(totalAnalysis.over, league, homeAbbr, awayAbbr, "total");
    const underPick = evaluateMarket(totalAnalysis.under, league, homeAbbr, awayAbbr, "total");

    if (overPick.status === "pick" && underPick.status === "pick") {
      totalPick = (overPick.score || 0) >= (underPick.score || 0) ? overPick : underPick;
    } else if (overPick.status === "pick") totalPick = overPick;
    else if (underPick.status === "pick") totalPick = underPick;
    else totalPick = overPick;
  }

  return { moneyline: moneylinePick, spread: spreadPick, total: totalPick };
}

// ============= Transform Event =============
function transformEvent(event: OddsApiEvent, uiSport: string): TransformedGame {
  const preferredBooks = ["fanduel", "draftkings", "betmgm", "bovada"];
  const bookmaker =
    event.bookmakers.find((b) => preferredBooks.includes(b.key)) || event.bookmakers[0];

  let moneyline = null;
  let spread = null;
  let total = null;

  if (bookmaker) {
    const h2hMarket = bookmaker.markets.find((m) => m.key === "h2h");
    if (h2hMarket) {
      const homeOutcome = h2hMarket.outcomes.find((o) => o.name === event.home_team);
      const awayOutcome = h2hMarket.outcomes.find((o) => o.name === event.away_team);
      moneyline = { home: homeOutcome?.price ?? null, away: awayOutcome?.price ?? null };
    }

    const spreadMarket = bookmaker.markets.find((m) => m.key === "spreads");
    if (spreadMarket) {
      const homeOutcome = spreadMarket.outcomes.find((o) => o.name === event.home_team);
      const awayOutcome = spreadMarket.outcomes.find((o) => o.name === event.away_team);
      spread = {
        home: homeOutcome ? { point: homeOutcome.point!, price: homeOutcome.price } : null,
        away: awayOutcome ? { point: awayOutcome.point!, price: awayOutcome.price } : null,
      };
    }

    const totalsMarket = bookmaker.markets.find((m) => m.key === "totals");
    if (totalsMarket) {
      const overOutcome = totalsMarket.outcomes.find((o) => o.name === "Over");
      const underOutcome = totalsMarket.outcomes.find((o) => o.name === "Under");
      total = {
        over: overOutcome ? { point: overOutcome.point!, price: overOutcome.price } : null,
        under: underOutcome ? { point: underOutcome.point!, price: underOutcome.price } : null,
      };
    }
  }

  const picks = generatePicks(event, uiSport);

  return {
    id: event.id,
    sport: uiSport,
    homeTeam: { name: event.home_team, abbreviation: getTeamAbbreviation(event.home_team) },
    awayTeam: { name: event.away_team, abbreviation: getTeamAbbreviation(event.away_team) },
    startTime: event.commence_time,
    odds: { moneyline, spread, total },
    picks,
  };
}

// ============= Model Call =============
async function enrichWithModelNBA(
  games: TransformedGame[],
): Promise<Record<string, { moneyline: PickResult; spread: PickResult; total: PickResult }>> {
  const MODEL_API_URL = Deno.env.get("MODEL_API_URL");
  const MODEL_API_KEY = Deno.env.get("MODEL_API_KEY");

  if (!MODEL_API_URL) {
    console.info("[model] MODEL_API_URL not set; skipping model");
    return {};
  }
  if (!MODEL_API_KEY) {
    console.info("[model] MODEL_API_KEY not set; skipping model");
    return {};
  }

  const url = `${MODEL_API_URL.replace(/\/$/, "")}/v1/nba/recommendations`;

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-model-key": MODEL_API_KEY,
      },
      body: JSON.stringify(games),
    });

    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      console.info(`[model] non-200 from model: ${resp.status} ${resp.statusText} body=${body}`);
      return {};
    }

    const data = (await resp.json()) as ModelRecommendResponse;
    return data?.byGameId ?? {};
  } catch (e) {
    console.info("[model] call failed:", e);
    return {};
  }
}

// ============= Main Handler =============
serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const url = new URL(req.url);
    const day = url.searchParams.get("day") || "today";

    const ODDS_API_KEY = Deno.env.get("ODDS_API_KEY");
    if (!ODDS_API_KEY) {
      throw new Error("ODDS_API_KEY not configured");
    }

    const { start: windowStart, end: windowEnd } = getDateWindow(day);

    const results: Record<string, TransformedGame[]> = {
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
        `https://api.the-odds-api.com/v4/sports/${apiSport}/odds/?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals&oddsFormat=american&dateFormat=iso`;

      try {
        const response = await fetch(apiUrl);
        if (!response.ok) {
          console.info(`[odds] failed ${uiSport}: ${response.status}`);
          return { sport: uiSport, games: [] as TransformedGame[] };
        }

        const events: OddsApiEvent[] = await response.json();

        console.info(
          `[odds] ${uiSport} events=${events.length} inWindow=${
            events.filter((e) => isGameInWindow(e.commence_time, windowStart, windowEnd)).length
          }`,
        );

        const filteredGames = events
          .filter((event) => isGameInWindow(event.commence_time, windowStart, windowEnd))
          .map((event) => transformEvent(event, uiSport));

        return { sport: uiSport, games: filteredGames };
      } catch (error) {
        console.info(`[odds] error ${uiSport}:`, error);
        return { sport: uiSport, games: [] as TransformedGame[] };
      }
    });

    const allResults = await Promise.all(fetchPromises);
    for (const r of allResults) results[r.sport] = r.games;

    // ✅ Call model for NBA only (for now) and merge picks
    const nbaGames = results.nba;
    if (nbaGames.length > 0) {
      console.info(`[model] nba games to model: ${nbaGames.length}`);
      const byGameId = await enrichWithModelNBA(nbaGames);

      results.nba = nbaGames.map((g) => {
        const modelPicks = byGameId[g.id];
        if (!modelPicks) return g;
        return { ...g, picks: modelPicks };
      });
    }

    console.info(`[slate] request day=${day} window=${windowStart.toISOString()}..${windowEnd.toISOString()}`);

    return new Response(JSON.stringify(results), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (error: unknown) {
    console.error("Slate API error:", error);
    const message = error instanceof Error ? error.message : "Internal server error";
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
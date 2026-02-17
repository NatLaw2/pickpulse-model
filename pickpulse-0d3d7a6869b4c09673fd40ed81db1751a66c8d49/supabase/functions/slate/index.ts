import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const SPORT_MAPPING: Record<string, string> = {
  nba: "basketball_nba",
  mlb: "baseball_mlb",
  nhl: "icehockey_nhl",
  ncaab: "basketball_ncaab",
  ncaaf: "americanfootball_ncaaf",
  nfl: "americanfootball_nfl",
};

const UI_SPORTS = ["nba", "mlb", "nhl", "ncaab", "ncaaf", "nfl"] as const;

type UiSport = (typeof UI_SPORTS)[number];

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

type ConfidenceTier = "low" | "medium" | "high";

interface PickResult {
  status: "pick" | "no_bet";
  selection?: string;
  confidence?: ConfidenceTier;
  score?: number; // optional if your model returns it
  rationale?: string[];
  reason?: string;
}

interface TransformedGame {
  id: string;
  sport: UiSport;
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
  // Up to THREE picks, one per market. Each can be "no_bet".
  picks: {
    moneyline: PickResult | null;
    spread: PickResult | null;
    total: PickResult | null;
  };
}

function getTeamAbbreviation(teamName: string): string {
  const abbreviations: Record<string, string> = {
    // NBA (common)
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

    // NFL quick examples
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

function isGameInWindow(gameTime: string, windowStart: Date, windowEnd: Date) {
  const gameDate = new Date(gameTime);
  return gameDate >= windowStart && gameDate < windowEnd;
}

/**
 * Returns {start, end} window for the given day filter
 * Window is 4 AM ET → 4 AM ET next day.
 * NOTE: This uses a fixed ET offset (-5) to match your existing logic.
 * If you want DST-accurate behavior later, we can upgrade it.
 */
function getDateWindow(day: string): { start: Date; end: Date } {
  const now = new Date();

  const estOffset = -5; // hours
  const dayStartHourUTC = 4 - estOffset; // 4 AM ET => 9 AM UTC

  const todayStart = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), dayStartHourUTC, 0, 0, 0),
  );

  // If current time is before 4 AM ET, we are in yesterday’s slate window
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

function pickPreferredBook(event: OddsApiEvent) {
  const preferredBooks = ["fanduel", "draftkings", "betmgm", "bovada"];
  return event.bookmakers.find((b) => preferredBooks.includes(b.key)) || event.bookmakers[0] || null;
}

function extractOddsFromPreferredBook(event: OddsApiEvent) {
  const bookmaker = pickPreferredBook(event);

  let moneyline: { home: number | null; away: number | null } | null = null;
  let spread: {
    home: { point: number; price: number } | null;
    away: { point: number; price: number } | null;
  } | null = null;
  let total: {
    over: { point: number; price: number } | null;
    under: { point: number; price: number } | null;
  } | null = null;

  if (!bookmaker) return { moneyline, spread, total };

  const h2hMarket = bookmaker.markets.find((m) => m.key === "h2h");
  if (h2hMarket) {
    const homeOutcome = h2hMarket.outcomes.find((o) => o.name === event.home_team);
    const awayOutcome = h2hMarket.outcomes.find((o) => o.name === event.away_team);
    moneyline = {
      home: homeOutcome?.price ?? null,
      away: awayOutcome?.price ?? null,
    };
  }

  const spreadMarket = bookmaker.markets.find((m) => m.key === "spreads");
  if (spreadMarket) {
    const homeOutcome = spreadMarket.outcomes.find((o) => o.name === event.home_team);
    const awayOutcome = spreadMarket.outcomes.find((o) => o.name === event.away_team);
    spread = {
      home:
        homeOutcome && homeOutcome.point !== undefined ? { point: homeOutcome.point, price: homeOutcome.price } : null,
      away:
        awayOutcome && awayOutcome.point !== undefined ? { point: awayOutcome.point, price: awayOutcome.price } : null,
    };
  }

  const totalsMarket = bookmaker.markets.find((m) => m.key === "totals");
  if (totalsMarket) {
    const overOutcome = totalsMarket.outcomes.find((o) => o.name === "Over");
    const underOutcome = totalsMarket.outcomes.find((o) => o.name === "Under");
    total = {
      over:
        overOutcome && overOutcome.point !== undefined ? { point: overOutcome.point, price: overOutcome.price } : null,
      under:
        underOutcome && underOutcome.point !== undefined
          ? { point: underOutcome.point, price: underOutcome.price }
          : null,
    };
  }

  return { moneyline, spread, total };
}

function noBet(reason: string): PickResult {
  return { status: "no_bet", reason };
}

/**
 * Calls your Render model for NBA picks.
 *
 * Required env vars in Supabase:
 *  - MODEL_API_URL   e.g. https://pickpulse-model.onrender.com
 *  - MODEL_API_KEY   (same token you set in Render env)
 *
 * Expected model output can be any of these shapes:
 *  A) { picks: { moneyline, spread, total } }
 *  B) { moneyline, spread, total }
 *
 * Each pick should look like:
 *  { status: "pick"|"no_bet", selection?, confidence?, rationale?, reason?, score? }
 *
 * If model errors, we return safe no_bet objects.
 */
async function getNbaModelPicks(input: {
  id: string;
  startTime: string;
  homeTeam: { name: string; abbreviation: string };
  awayTeam: { name: string; abbreviation: string };
  odds: TransformedGame["odds"];
}): Promise<TransformedGame["picks"]> {
  const baseUrl = Deno.env.get("MODEL_API_URL");
  const apiKey = Deno.env.get("MODEL_API_KEY");

  if (!baseUrl) {
    return {
      moneyline: noBet("Model service not configured"),
      spread: noBet("Model service not configured"),
      total: noBet("Model service not configured"),
    };
  }

  // Normalize base URL (strip trailing slash)
  const normalizedBase = baseUrl.replace(/\/+$/, "");

  // We try a couple common endpoints so you don’t get stuck on a mismatch.
  const candidatePaths = ["/predict/nba", "/nba/predict", "/predict"];

  const payload = {
    sport: "nba",
    eventId: input.id,
    startTime: input.startTime,
    home: input.homeTeam,
    away: input.awayTeam,
    odds: input.odds,
  };

  let lastError = "Unknown model error";

  for (const path of candidatePaths) {
    try {
      const res = await fetch(`${normalizedBase}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        lastError = `Model HTTP ${res.status}`;
        continue;
      }

      const data = await res.json();

      // Accept both shapes
      const picks = data?.picks ?? data;

      const moneyline: PickResult | null = picks?.moneyline ?? null;
      const spread: PickResult | null = picks?.spread ?? null;
      const total: PickResult | null = picks?.total ?? null;

      // Enforce “up to 3 picks (one per market) with no_bet allowed”
      return {
        moneyline: moneyline ?? noBet("No moneyline recommendation"),
        spread: spread ?? noBet("No spread recommendation"),
        total: total ?? noBet("No total recommendation"),
      };
    } catch (e) {
      lastError = e instanceof Error ? e.message : "Model call failed";
    }
  }

  // If all endpoints fail, return safe no_bet
  return {
    moneyline: noBet(`Model unavailable (${lastError})`),
    spread: noBet(`Model unavailable (${lastError})`),
    total: noBet(`Model unavailable (${lastError})`),
  };
}

async function transformEvent(event: OddsApiEvent, uiSport: UiSport): Promise<TransformedGame> {
  const homeAbbr = getTeamAbbreviation(event.home_team);
  const awayAbbr = getTeamAbbreviation(event.away_team);

  const odds = extractOddsFromPreferredBook(event);

  // Default picks for non-NBA until you expand the model by sport
  let picks: TransformedGame["picks"] = {
    moneyline: null,
    spread: null,
    total: null,
  };

  if (uiSport === "nba") {
    picks = await getNbaModelPicks({
      id: event.id,
      startTime: event.commence_time,
      homeTeam: { name: event.home_team, abbreviation: homeAbbr },
      awayTeam: { name: event.away_team, abbreviation: awayAbbr },
      odds,
    });
  }

  return {
    id: event.id,
    sport: uiSport,
    homeTeam: { name: event.home_team, abbreviation: homeAbbr },
    awayTeam: { name: event.away_team, abbreviation: awayAbbr },
    startTime: event.commence_time,
    odds,
    picks,
  };
}

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

    const results: Record<UiSport, TransformedGame[]> = {
      nba: [],
      mlb: [],
      nhl: [],
      ncaab: [],
      ncaaf: [],
      nfl: [],
    };

    const fetchPromises = UI_SPORTS.map(async (uiSport) => {
      const apiSport = SPORT_MAPPING[uiSport];
      const apiUrl = `https://api.the-odds-api.com/v4/sports/${apiSport}/odds/?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals&oddsFormat=american&dateFormat=iso`;

      try {
        const response = await fetch(apiUrl);

        if (!response.ok) {
          console.error(`Failed to fetch ${uiSport}: ${response.status}`);
          return { sport: uiSport, games: [] as TransformedGame[] };
        }

        const events: OddsApiEvent[] = await response.json();

        // Filter to the desired “day” window (4AM ET -> 4AM ET)
        const inWindow = events.filter((event) => isGameInWindow(event.commence_time, windowStart, windowEnd));

        // Transform with model calls (NBA only)
        const games = await Promise.all(inWindow.map((event) => transformEvent(event, uiSport)));

        return { sport: uiSport, games };
      } catch (error) {
        console.error(`Error fetching ${uiSport}:`, error);
        return { sport: uiSport, games: [] as TransformedGame[] };
      }
    });

    const allResults = await Promise.all(fetchPromises);

    for (const r of allResults) {
      results[r.sport] = r.games;
    }

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

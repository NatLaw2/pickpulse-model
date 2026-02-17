import type { Sport, ConfidenceTier, MarketRecommendation } from "./sports";

/**
 * Row shape for model picks as returned from the slate-with-picks edge function
 */
export interface ModelPickRow {
  id: string;
  sport: Sport;
  home_team: string;
  away_team: string;
  commence_time: string;
  pick_market: "moneyline" | "spread" | "total";
  pick_side: string;
  confidence: ConfidenceTier;
  score?: number;
  rationale?: string[];
}
export type ModelPick = {
  id: number;
  sport: string;
  event_id: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  pick_market: "h2h" | "spreads" | "totals";
  pick_side: string;
  confidence: number;
  model_version: string;
  reasoning: string;
  created_at: string;
};

/**
 * Transformed game with picks from the slate-with-picks edge function
 */
export interface GameWithPicks {
  id: string;
  sport: Sport;
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
    moneyline: MarketRecommendation;
    spread: MarketRecommendation;
    total: MarketRecommendation;
  };
}

/**
 * Response shape from the slate-with-picks edge function
 */
export type SlateWithPicksResponse = Record<Sport, GameWithPicks[]>;

/**
 * Extract flat model pick rows from a GameWithPicks object
 */
export function extractPickRows(game: GameWithPicks): ModelPickRow[] {
  const rows: ModelPickRow[] = [];
  const markets = ["moneyline", "spread", "total"] as const;

  for (const market of markets) {
    const pick = game.picks[market];
    if (pick.status === "pick") {
      rows.push({
        id: `${game.id}-${market}`,
        sport: game.sport,
        home_team: game.homeTeam.name,
        away_team: game.awayTeam.name,
        commence_time: game.startTime,
        pick_market: market,
        pick_side: pick.selection,
        confidence: pick.confidence,
        score: pick.score,
        rationale: pick.rationale,
      });
    }
  }

  return rows;
}

/**
 * Extract all picks from a slate response as flat rows
 */
export function extractAllPickRows(slate: SlateWithPicksResponse): ModelPickRow[] {
  const allPicks: ModelPickRow[] = [];

  for (const sport of Object.keys(slate) as Sport[]) {
    const games = slate[sport] ?? [];
    for (const game of games) {
      allPicks.push(...extractPickRows(game));
    }
  }

  // Sort by score descending
  return allPicks.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
}

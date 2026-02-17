// src/types/sports.ts

export type Sport = "nba" | "mlb" | "nhl" | "ncaab" | "ncaaf" | "nfl";
export type ConfidenceTier = "low" | "medium" | "high";

/**
 * DateFilter values used across the app (DateTabs, hooks, pages).
 * Keep this in sync with your UI tabs + any comparisons in code.
 */
export type DateFilter = "today" | "tomorrow" | "nextDay" | "week";

export interface Team {
  name: string;
  abbreviation: string;
  logo?: string;
}

export interface OddsData {
  moneyline: { home: number | null; away: number | null } | null;
  spread: {
    home: { point: number; price: number } | null;
    away: { point: number; price: number } | null;
  } | null;
  total: {
    over: { point: number; price: number } | null;
    under: { point: number; price: number } | null;
  } | null;
}

export type MarketStatus = "pick" | "no_bet";

export type MarketRecommendation =
  | {
      status: "pick";
      selection: string;
      confidence: ConfidenceTier;
      rationale: string[];
      score?: number;
    }
  | {
      status: "no_bet";
      reason: string;
      score?: number;
    };

export interface GameRecommendation {
  moneyline: MarketRecommendation;
  spread: MarketRecommendation;
  total: MarketRecommendation;
}

export interface Game {
  id: string;
  sport: Sport;
  homeTeam: Team;
  awayTeam: Team;
  startTime: string;
  odds: OddsData;
  recommendation: GameRecommendation;
}

export interface PropLine {
  player: string;
  line: number | null;
  over: number | null;
  under: number | null;
}

export interface PropMarket {
  market: string;
  marketLabel: string;
  props: PropLine[];
}

export interface PerformanceStats {
  wins: number;
  losses: number;
  percentage: number;
}

export interface SportPerformance {
  sport: Sport;
  overall: PerformanceStats;
  moneyline: PerformanceStats;
  spread: PerformanceStats;
  overUnder: PerformanceStats;
  parlays: PerformanceStats;
  totalPicks: number;
}

export const SPORT_LABELS: Record<Sport, string> = {
  nba: "NBA",
  mlb: "MLB",
  nhl: "NHL",
  ncaab: "NCAA Basketball",
  ncaaf: "NCAA Football",
  nfl: "NFL",
};

// Type guards for MarketRecommendation
export function isPick(rec: MarketRecommendation): rec is Extract<MarketRecommendation, { status: "pick" }> {
  return rec.status === "pick";
}

export function isNoBet(rec: MarketRecommendation): rec is Extract<MarketRecommendation, { status: "no_bet" }> {
  return rec.status === "no_bet";
}

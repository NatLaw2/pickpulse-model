// src/lib/api.ts

import { Sport, Game, PropMarket, SportPerformance, DateFilter } from "@/types/sports";

const DAY_PARAM_MAP: Record<DateFilter, string> = {
  today: "today",
  tomorrow: "tomorrow",
  nextDay: "nextDay",
  week: "today", // fallback for week
};

export async function fetchSlate(day: DateFilter): Promise<Record<Sport, Game[]> & { topPicks?: any[] }> {
  const response = await fetch(`${import.meta.env.VITE_SUPABASE_URL}/functions/v1/slate?day=${DAY_PARAM_MAP[day]}`, {
    method: "GET",
    headers: {
      apikey: import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
      authorization: `Bearer ${import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Failed to fetch slate");
  }

  const slateData = await response.json();

  const sports: Sport[] = ["nba", "mlb", "nhl", "ncaab", "ncaaf", "nfl"];

  const result: Record<Sport, Game[]> & { topPicks?: any[] } = {
    nba: [],
    mlb: [],
    nhl: [],
    ncaab: [],
    ncaaf: [],
    nfl: [],
    topPicks: Array.isArray(slateData.topPicks) ? slateData.topPicks : [],
  };

  for (const sport of sports) {
    if (slateData[sport]) {
      result[sport] = slateData[sport].map((game: any) => {
        const picks = game?.picks ?? {};

        return {
          ...game,
          sport: sport as Sport,

          // ✅ Always provide all 3 markets, even if backend returns partial picks
          recommendation: {
            moneyline: picks.moneyline ?? { status: "no_bet", reason: "No data available" },
            spread: picks.spread ?? { status: "no_bet", reason: "No data available" },
            total: picks.total ?? { status: "no_bet", reason: "No data available" },
          },
        };
      });
    }
  }

  return result;
}

export async function fetchProps(sportKey: Sport, eventId: string): Promise<PropMarket[]> {
  const response = await fetch(
    `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/props?sportKey=${sportKey}&eventId=${eventId}`,
    {
      method: "GET",
      headers: {
        apikey: import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
        Authorization: `Bearer ${import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
        "Content-Type": "application/json",
      },
    },
  );

  if (!response.ok) {
    throw new Error("Failed to fetch props");
  }

  const data = await response.json();
  return data.props || [];
}

// Placeholder performance data (DB later)
export function getPerformanceData(): SportPerformance[] {
  const sports: Sport[] = ["nba", "mlb", "nhl", "ncaab", "ncaaf", "nfl"];

  return sports.map((sport) => ({
    sport,
    overall: { wins: 0, losses: 0, percentage: 0 },
    moneyline: { wins: 0, losses: 0, percentage: 0 },
    spread: { wins: 0, losses: 0, percentage: 0 },
    overUnder: { wins: 0, losses: 0, percentage: 0 },
    parlays: { wins: 0, losses: 0, percentage: 0 },
    totalPicks: 0,
  }));
}

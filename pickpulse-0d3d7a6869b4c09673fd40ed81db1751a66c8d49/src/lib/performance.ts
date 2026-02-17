// src/lib/performance.ts
export type PerformanceSource = "live" | "backtest";
export type PerformanceRange = "7d" | "30d" | "season";

export type PerformanceStats = {
  wins: number;
  losses: number;
  percentage: number;
  units?: number;
};

export type SportPerformance = {
  sport: string;
  overall: PerformanceStats;
  moneyline: PerformanceStats;
  spread: PerformanceStats;
  overUnder: PerformanceStats;
  parlays: PerformanceStats;
  totalPicks: number;
};

export type TopPickPerformance = {
  wins: number;
  losses: number;
  pushes: number;
  picks: number;
  percentage: number;
  units: number;
};

export type PerformanceSummaryResponse = {
  ok: boolean;
  source: PerformanceSource;
  range: PerformanceRange;
  overall: { wins: number; losses: number; picks: number; percentage: number; units?: number };
  topPick?: TopPickPerformance;
  sports: SportPerformance[];
};

export type ModelHealth = {
  ok: boolean;
  source: PerformanceSource;

  /**
   * Live only: how many pick_snapshots exist for today's run_date
   * (includes top_pick + strong_lean across moneyline/spread/total)
   */
  trackedToday: number;

  /**
   * How many graded picks exist in pick_snapshots (result not null), anytime.
   * This is a better "is grading happening?" proxy than NBA-only views.
   */
  gradedGames: number;

  /**
   * Last injury update timestamp (best-effort).
   * Keep as-is for now (NBA injuries table).
   */
  lastUpdatedAt: string | null;
};

/**
 * UI decision: Keep thresholds as-is (done in model),
 * but include these tiers/markets in tracking and health.
 */
const INCLUDED_TIERS = ["top_pick", "strong_lean"] as const;
const INCLUDED_MARKETS = ["moneyline", "spread", "total"] as const;

function getSupabaseEnv() {
  const baseUrl = import.meta.env.VITE_SUPABASE_URL;
  const anonKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

  if (!baseUrl || !anonKey) {
    throw new Error("Missing Supabase env vars (VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY).");
  }

  return { baseUrl, anonKey };
}

// Supabase REST count comes back in Content-Range when using Prefer: count=exact
function parseCountFromContentRange(cr: string | null): number {
  // Example: "0-0/123" or "*/0"
  if (!cr) return 0;
  const parts = cr.split("/");
  if (parts.length !== 2) return 0;
  const total = Number(parts[1]);
  return Number.isFinite(total) ? total : 0;
}

function ymdLocal(d = new Date()): string {
  // Local date (not UTC) to match Postgres current_date behavior more closely
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

async function supabaseCount(path: string): Promise<number> {
  const { baseUrl, anonKey } = getSupabaseEnv();

  const res = await fetch(`${baseUrl}/rest/v1/${path}`, {
    method: "GET",
    headers: {
      apikey: anonKey,
      authorization: `Bearer ${anonKey}`,
      Prefer: "count=exact",
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Supabase count failed: ${res.status} ${text}`);
  }

  const contentRange = res.headers.get("content-range");
  return parseCountFromContentRange(contentRange);
}

async function supabaseSelectJson<T>(path: string): Promise<T> {
  const { baseUrl, anonKey } = getSupabaseEnv();

  const res = await fetch(`${baseUrl}/rest/v1/${path}`, {
    method: "GET",
    headers: {
      apikey: anonKey,
      authorization: `Bearer ${anonKey}`,
      "content-type": "application/json",
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Supabase select failed: ${res.status} ${text}`);
  }

  return (await res.json()) as T;
}

export async function fetchPerformanceSummary(
  source: PerformanceSource,
  range: PerformanceRange,
): Promise<PerformanceSummaryResponse> {
  const { baseUrl, anonKey } = getSupabaseEnv();

  const url = `${baseUrl}/functions/v1/performance-summary?source=${encodeURIComponent(
    source,
  )}&range=${encodeURIComponent(range)}`;

  const res = await fetch(url, {
    method: "GET",
    headers: {
      apikey: anonKey,
      authorization: `Bearer ${anonKey}`,
      "content-type": "application/json",
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`performance-summary failed: ${res.status} ${text}`);
  }

  return (await res.json()) as PerformanceSummaryResponse;
}

/**
 * Lightweight "is the system alive?" strip for Performance page.
 *
 * UPDATED to support your new reality:
 * - Picks tracked are now written to pick_snapshots (top_pick + strong_lean; moneyline/spread/total)
 * - Grading will also be reflected on pick_snapshots (result column), not just NBA-only views
 *
 * NOTE: This still doesn't require any new SQL objects.
 */
export async function fetchModelHealth(source: PerformanceSource): Promise<ModelHealth> {
  const today = ymdLocal();

  // 1) trackedToday (LIVE only): count today's pick_snapshots across tiers + markets
  // Using REST filters:
  //   run_date=eq.YYYY-MM-DD
  //   source=eq.live
  //   tier=in.(...)
  //   market=in.(...)
  const tiers = INCLUDED_TIERS.join(",");
  const markets = INCLUDED_MARKETS.join(",");

  const trackedToday =
    source === "live"
      ? await supabaseCount(
          `pick_snapshots?select=id&run_date=eq.${today}&source=eq.live&tier=in.(${tiers})&market=in.(${markets})&limit=1`,
        )
      : 0;

  // 2) gradedGames: count graded picks from pick_results table (populated by grade_picks edge function)
  // Falls back to pick_snapshots if pick_results is empty (backwards compat)
  let gradedGames = await supabaseCount(`pick_results?select=id&result=in.(win,loss,push)&limit=1`);
  if (gradedGames === 0) {
    gradedGames = await supabaseCount(`pick_snapshots?select=id&result=not.is.null&limit=1`);
  }

  // 3) lastUpdatedAt (best-effort, unchanged)
  let lastUpdatedAt: string | null = null;
  try {
    const rows = await supabaseSelectJson<Array<{ pulled_at: string }>>(
      `injury_snapshots_nba?select=pulled_at&order=pulled_at.desc&limit=1`,
    );
    lastUpdatedAt = rows?.[0]?.pulled_at ?? null;
  } catch {
    lastUpdatedAt = null;
  }

  return {
    ok: true,
    source,
    trackedToday,
    gradedGames,
    lastUpdatedAt,
  };
}

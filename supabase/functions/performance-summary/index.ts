// supabase/functions/performance-summary/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
};

type Source = "live" | "backtest";
type Range = "7d" | "30d" | "season";

function rangeToStart(range: Range): string {
  const now = new Date();
  if (range === "7d") now.setDate(now.getDate() - 7);
  else if (range === "30d") now.setDate(now.getDate() - 30);
  else now.setDate(now.getDate() - 180);
  return now.toISOString();
}

function pct(w: number, l: number) {
  const t = w + l;
  return t > 0 ? Math.round((w / t) * 1000) / 10 : 0;
}

function roundUnits(u: number): number {
  return Math.round(u * 1000) / 1000;
}

const SPORTS = ["nba", "mlb", "nhl", "ncaab", "ncaaf", "nfl"];

// ---------------------------------------------------------------------------
// Confidence bucket classification
// ---------------------------------------------------------------------------

type ConfidenceBucket = "top" | "high" | "medium";

function classifyBucket(
  tier: string | null,
  confidence: number | null,
): ConfidenceBucket | null {
  // Tier-based classification takes priority
  if (tier === "top_pick") return "top";
  if (tier === "strong_lean") return "high";
  if (tier === "watchlist") return "medium";

  // Fallback to confidence number
  if (typeof confidence === "number") {
    if (confidence >= 0.80) return "top";
    if (confidence >= 0.65) return "high";
    if (confidence >= 0.55) return "medium";
  }

  return null; // Exclude from confidence breakdown
}

type BucketStats = {
  wins: number;
  losses: number;
  pushes: number;
  picks: number;
  percentage: number;
  units: number;
};

function emptyBucket(): BucketStats {
  return { wins: 0, losses: 0, pushes: 0, picks: 0, percentage: 0, units: 0 };
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

serve(async (req) => {
  // Preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const url = new URL(req.url);
    const source = (url.searchParams.get("source") || "live") as Source;
    const range = (url.searchParams.get("range") || "30d") as Range;

    // Validate inputs
    const validSource = source === "live" || source === "backtest";
    const validRange = range === "7d" || range === "30d" || range === "season";
    if (!validSource || !validRange) {
      return new Response(
        JSON.stringify({
          ok: false,
          error: "Invalid query params. Use source=live|backtest and range=7d|30d|season",
        }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
    const SERVICE_ROLE_KEY =
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ||
      Deno.env.get("SERVICE_ROLE_KEY");

    if (!SUPABASE_URL) throw new Error("Missing SUPABASE_URL");
    if (!SERVICE_ROLE_KEY) throw new Error("Missing SUPABASE_SERVICE_ROLE_KEY (or SERVICE_ROLE_KEY)");

    // Service role client
    const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
      auth: { persistSession: false },
    });

    const startTime = rangeToStart(range);

    // Pull graded picks — now also selecting confidence for bucket classification
    const { data, error } = await supabase
      .from("pick_results")
      .select("sport, market, result, tier, units, confidence")
      .eq("source", source)
      .gte("start_time", startTime)
      .in("result", ["win", "loss", "push"]);

    if (error) throw new Error(error.message);

    const rows = data ?? [];

    // Initialize aggregates
    const bySport: Record<string, any> = {};
    for (const s of SPORTS) {
      bySport[s] = {
        sport: s,
        overall: { wins: 0, losses: 0, percentage: 0, units: 0 },
        moneyline: { wins: 0, losses: 0, percentage: 0, units: 0 },
        spread: { wins: 0, losses: 0, percentage: 0, units: 0 },
        overUnder: { wins: 0, losses: 0, percentage: 0, units: 0 },
        parlays: { wins: 0, losses: 0, percentage: 0 },
        totalPicks: 0,
      };
    }

    // Top Pick aggregates (kept for backwards compat)
    let topPickWins = 0;
    let topPickLosses = 0;
    let topPickPushes = 0;
    let topPickUnits = 0;

    // Confidence bucket aggregates
    const buckets: Record<ConfidenceBucket, BucketStats> = {
      top: emptyBucket(),
      high: emptyBucket(),
      medium: emptyBucket(),
    };

    // Accumulate
    for (const r of rows) {
      const s = r.sport;
      if (!bySport[s]) continue;

      const u = typeof r.units === "number" ? r.units : 0;

      // Top Pick tracking (backwards compat)
      if (r.tier === "top_pick") {
        if (r.result === "win") { topPickWins++; topPickUnits += u; }
        else if (r.result === "loss") { topPickLosses++; topPickUnits += u; }
        else { topPickPushes++; }
      }

      // Confidence bucket tracking
      const bucket = classifyBucket(r.tier, r.confidence);
      if (bucket) {
        buckets[bucket].picks++;
        if (r.result === "win") { buckets[bucket].wins++; buckets[bucket].units += u; }
        else if (r.result === "loss") { buckets[bucket].losses++; buckets[bucket].units += u; }
        else { buckets[bucket].pushes++; }
      }

      if (r.result === "push") {
        bySport[s].totalPicks += 1;
        continue;
      }

      const isWin = r.result === "win";
      bySport[s].overall.wins += isWin ? 1 : 0;
      bySport[s].overall.losses += isWin ? 0 : 1;
      bySport[s].overall.units += u;
      bySport[s].totalPicks += 1;

      if (r.market === "moneyline") {
        bySport[s].moneyline.wins += isWin ? 1 : 0;
        bySport[s].moneyline.losses += isWin ? 0 : 1;
        bySport[s].moneyline.units += u;
      } else if (r.market === "spread") {
        bySport[s].spread.wins += isWin ? 1 : 0;
        bySport[s].spread.losses += isWin ? 0 : 1;
        bySport[s].spread.units += u;
      } else if (r.market === "total") {
        bySport[s].overUnder.wins += isWin ? 1 : 0;
        bySport[s].overUnder.losses += isWin ? 0 : 1;
        bySport[s].overUnder.units += u;
      }
    }

    // Finalize percentages + totals
    let totalW = 0;
    let totalL = 0;
    let totalPicks = 0;
    let totalUnits = 0;

    const sportList = SPORTS.map((s) => {
      const o = bySport[s];

      o.overall.percentage = pct(o.overall.wins, o.overall.losses);
      o.overall.units = roundUnits(o.overall.units);
      o.moneyline.percentage = pct(o.moneyline.wins, o.moneyline.losses);
      o.moneyline.units = roundUnits(o.moneyline.units);
      o.spread.percentage = pct(o.spread.wins, o.spread.losses);
      o.spread.units = roundUnits(o.spread.units);
      o.overUnder.percentage = pct(o.overUnder.wins, o.overUnder.losses);
      o.overUnder.units = roundUnits(o.overUnder.units);

      totalW += o.overall.wins;
      totalL += o.overall.losses;
      totalPicks += o.totalPicks;
      totalUnits += o.overall.units;

      return o;
    });

    const overall = {
      wins: totalW,
      losses: totalL,
      picks: totalPicks,
      percentage: pct(totalW, totalL),
      units: roundUnits(totalUnits),
    };

    const topPick = {
      wins: topPickWins,
      losses: topPickLosses,
      pushes: topPickPushes,
      picks: topPickWins + topPickLosses + topPickPushes,
      percentage: pct(topPickWins, topPickLosses),
      units: roundUnits(topPickUnits),
    };

    // Finalize confidence bucket percentages
    const confidenceBuckets: Record<string, BucketStats> = {};
    for (const [key, b] of Object.entries(buckets)) {
      confidenceBuckets[key] = {
        ...b,
        percentage: pct(b.wins, b.losses),
        units: roundUnits(b.units),
      };
    }

    return new Response(
      JSON.stringify({
        ok: true,
        source,
        range,
        overall,
        topPick,
        confidenceBuckets,
        sports: sportList,
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    return new Response(
      JSON.stringify({
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
})

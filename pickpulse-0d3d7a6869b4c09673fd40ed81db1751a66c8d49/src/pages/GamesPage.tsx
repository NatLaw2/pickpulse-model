// src/pages/GamesPage.tsx
import { useEffect, useMemo, useState } from "react";
import { DateFilter, Sport, MarketRecommendation } from "@/types/sports";
import { GameWithPicks, SlateWithPicksResponse } from "@/types/modelPicks";
import { DateTabs } from "@/components/games/DateTabs";
import { getSlateWithPicks, getDecisionSlate, DecisionSlateResponse, DecisionPick } from "@/integrations/supabase/getModelPicks";
import { getNbaLogo } from "@/lib/nbaLogos";
import { TierBadge, tierFromScore, TierKey } from "@/components/games/TierBadge";
import { ConfidenceBar } from "@/components/games/ConfidenceBar";
import {
  Loader2,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  AlertCircle,
  Clock,
  Target,
  Zap,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

function marketLabel(m: string): string {
  if (m === "moneyline") return "Moneyline";
  if (m === "spread") return "Spread";
  if (m === "total") return "Total";
  return m;
}

function fmtOdds(price: number | null): string {
  if (price === null || price === undefined) return "—";
  return price >= 0 ? `+${price}` : `${price}`;
}

function scoreToConfidence(score: number): number {
  return Math.min(score, 100) / 100;
}

function impliedProb(americanOdds: number): number {
  if (americanOdds >= 100) return 100 / (americanOdds + 100);
  return Math.abs(americanOdds) / (Math.abs(americanOdds) + 100);
}

// ---------------------------------------------------------------------------
// Types for flattened picks
// ---------------------------------------------------------------------------

type FlatPick = {
  game: GameWithPicks;
  market: "moneyline" | "spread" | "total";
  pick: Extract<MarketRecommendation, { status: "pick" }>;
  tier: TierKey;
  score: number;
  confidence: number;
};

function flattenPicks(slate: SlateWithPicksResponse): FlatPick[] {
  const picks: FlatPick[] = [];
  const sports: Sport[] = ["nba", "mlb", "nhl", "ncaab", "ncaaf", "nfl"];
  const markets: Array<"moneyline" | "spread" | "total"> = ["moneyline", "spread", "total"];

  for (const sport of sports) {
    const games = slate[sport] ?? [];
    for (const game of games) {
      for (const m of markets) {
        const rec = game.picks?.[m];
        if (rec?.status === "pick" && typeof rec.score === "number" && rec.score >= 65) {
          const score = rec.score;
          picks.push({
            game,
            market: m,
            pick: rec as Extract<MarketRecommendation, { status: "pick" }>,
            tier: tierFromScore(score),
            score,
            confidence: scoreToConfidence(score),
          });
        }
      }
    }
  }

  // Sort: top picks first, then by score desc
  picks.sort((a, b) => b.score - a.score);
  return picks;
}

// Group picks by start time bucket
function groupByTime(picks: FlatPick[]): Map<string, FlatPick[]> {
  const groups = new Map<string, FlatPick[]>();
  for (const p of picks) {
    const key = fmtTime(p.game.startTime) || "TBD";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(p);
  }
  return groups;
}

// ---------------------------------------------------------------------------
// Team Logo
// ---------------------------------------------------------------------------

function TeamLogo({ name, abbreviation }: { name: string; abbreviation?: string }) {
  const [err, setErr] = useState(false);
  const src = getNbaLogo(abbreviation || name);

  if (err) {
    return (
      <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-[10px] font-bold text-gray-400">
        {(abbreviation || name || "?").slice(0, 3).toUpperCase()}
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={name}
      className="w-8 h-8 object-contain"
      onError={() => setErr(true)}
    />
  );
}

// ---------------------------------------------------------------------------
// Pick Card Component
// ---------------------------------------------------------------------------

function PickCard({ fp }: { fp: FlatPick }) {
  const [expanded, setExpanded] = useState(false);
  const { game, market, pick, tier, score, confidence } = fp;

  const isTopPick = tier === "top_pick";

  // Edge calculation (model confidence vs implied market prob)
  let edgePct: number | null = null;
  let marketImplied: number | null = null;
  const modelProb = confidence;

  if (market === "moneyline" && game.odds?.moneyline) {
    const sel = pick.selection.toLowerCase();
    const homeName = game.homeTeam?.name?.toLowerCase() ?? "";
    const awayName = game.awayTeam?.name?.toLowerCase() ?? "";
    const homeAbbr = game.homeTeam?.abbreviation?.toLowerCase() ?? "";
    const awayAbbr = game.awayTeam?.abbreviation?.toLowerCase() ?? "";

    let odds: number | null = null;
    if (sel.includes(homeName) || sel.includes(homeAbbr) || homeName.includes(sel.split(" ")[0]?.toLowerCase() ?? "")) {
      odds = game.odds.moneyline.home;
    } else if (sel.includes(awayName) || sel.includes(awayAbbr) || awayName.includes(sel.split(" ")[0]?.toLowerCase() ?? "")) {
      odds = game.odds.moneyline.away;
    }

    if (odds !== null) {
      marketImplied = impliedProb(odds);
      edgePct = (modelProb - marketImplied) * 100;
    }
  }

  return (
    <div
      className={`
        bg-slate-900/70 backdrop-blur-md border rounded-xl p-5 shadow-lg
        hover:shadow-2xl hover:scale-[1.02] transition-all duration-300 cursor-pointer
        ${isTopPick
          ? "border-emerald-500/30 ring-1 ring-emerald-500/20"
          : "border-slate-800"
        }
      `}
      onClick={() => setExpanded(!expanded)}
    >
      {/* Header Row: Teams + Tier */}
      <div className="flex items-center justify-between mb-4">
        {/* Matchup */}
        <div className="flex items-center gap-3 min-w-0">
          <TeamLogo
            name={game.awayTeam?.name ?? ""}
            abbreviation={game.awayTeam?.abbreviation}
          />
          <div className="flex flex-col items-center">
            <span className="text-[10px] text-gray-500 uppercase tracking-widest">vs</span>
          </div>
          <TeamLogo
            name={game.homeTeam?.name ?? ""}
            abbreviation={game.homeTeam?.abbreviation}
          />
          <div className="ml-2 min-w-0">
            <p className="text-sm font-semibold text-white truncate">
              {game.awayTeam?.name ?? "Away"}{" "}
              <span className="text-gray-500">@</span>{" "}
              {game.homeTeam?.name ?? "Home"}
            </p>
            <p className="text-xs text-gray-500 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {fmtTime(game.startTime)}
            </p>
          </div>
        </div>

        {/* Tier + Market Badge */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs text-gray-500 bg-slate-800 px-2 py-0.5 rounded-md">
            {marketLabel(market)}
          </span>
          <TierBadge tier={tier} />
        </div>
      </div>

      {/* Selection Line */}
      <div className="mb-3">
        <p className="text-lg font-bold text-white tracking-tight">
          {pick.selection}
        </p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        {/* Confidence */}
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Confidence</p>
          <p className="text-xl font-bold text-white">
            {(confidence * 100).toFixed(0)}%
          </p>
        </div>

        {/* Model Prob */}
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Model Prob</p>
          <p className="text-xl font-bold text-white">
            {(modelProb * 100).toFixed(1)}%
          </p>
        </div>

        {/* Market Implied */}
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Market Implied</p>
          <p className="text-xl font-bold text-gray-400">
            {marketImplied !== null ? `${(marketImplied * 100).toFixed(1)}%` : "—"}
          </p>
        </div>

        {/* Edge */}
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Edge</p>
          <p className={`text-xl font-bold ${
            edgePct !== null
              ? edgePct >= 0
                ? "text-emerald-400"
                : "text-red-400"
              : "text-gray-500"
          }`}>
            {edgePct !== null
              ? `${edgePct >= 0 ? "+" : ""}${edgePct.toFixed(1)}%`
              : "—"}
          </p>
        </div>
      </div>

      {/* Confidence Bar */}
      <ConfidenceBar value={confidence} className="mb-3" />

      {/* Expand indicator */}
      <div className="flex items-center gap-1 text-gray-500 text-xs">
        {expanded ? (
          <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronRight className="w-3 h-3" />
        )}
        <span>{expanded ? "Hide analysis" : "Show analysis"}</span>
      </div>

      {/* Expanded: Why section */}
      {expanded && pick.rationale && pick.rationale.length > 0 && (
        <div className="mt-4 pt-4 border-t border-slate-800">
          <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-2">Model Analysis</p>
          <ul className="space-y-1.5">
            {pick.rationale.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                <Zap className="w-3 h-3 mt-1 text-emerald-400 flex-shrink-0" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export const GamesPage = () => {
  const [dateFilter, setDateFilter] = useState<DateFilter>("today");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [slate, setSlate] = useState<SlateWithPicksResponse | null>(null);
  const [decisionSlate, setDecisionSlate] = useState<DecisionSlateResponse | null>(null);

  // Fetch slate and decision slate
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const [slateData, dsData] = await Promise.allSettled([
          getSlateWithPicks(dateFilter),
          getDecisionSlate(dateFilter),
        ]);

        if (cancelled) return;

        if (slateData.status === "fulfilled") {
          setSlate(slateData.value);
        }
        if (dsData.status === "fulfilled") {
          setDecisionSlate(dsData.value);
        }
        if (slateData.status === "rejected" && dsData.status === "rejected") {
          setError("Failed to load game data");
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [dateFilter]);

  // Flatten picks
  const allPicks = useMemo(() => {
    if (!slate) return [];
    return flattenPicks(slate);
  }, [slate]);

  const topPicks = useMemo(() => allPicks.filter((p) => p.tier === "top_pick"), [allPicks]);
  const strongLeans = useMemo(() => allPicks.filter((p) => p.tier === "strong_lean"), [allPicks]);
  const watchlist = useMemo(() => allPicks.filter((p) => p.tier === "watchlist"), [allPicks]);

  // Group all picks by start time
  const timeGroups = useMemo(() => groupByTime(allPicks), [allPicks]);

  // Count games
  const totalGames = useMemo(() => {
    if (!slate) return 0;
    return Object.values(slate).reduce(
      (sum, games) => sum + (Array.isArray(games) ? games.length : 0),
      0,
    );
  }, [slate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-black">
      {/* Sticky Header */}
      <div className="sticky top-0 z-30 bg-slate-950/80 backdrop-blur-xl border-b border-slate-800/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
                GAMES TODAY
              </h1>
              <p className="text-sm text-gray-400 mt-0.5">
                AI-ranked opportunities based on model edge
              </p>
            </div>
            <DateTabs selected={dateFilter} onChange={setDateFilter} />
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-24">
            <Loader2 className="h-8 w-8 text-emerald-400 animate-spin mb-4" />
            <p className="text-gray-400 text-sm">Loading today's slate...</p>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="flex flex-col items-center justify-center py-24">
            <AlertCircle className="h-10 w-10 text-red-400 mb-4" />
            <p className="text-white font-semibold mb-2">Failed to load games</p>
            <p className="text-gray-400 text-sm">{error}</p>
          </div>
        )}

        {/* No Games */}
        {!loading && !error && totalGames === 0 && (
          <div className="flex flex-col items-center justify-center py-24">
            <Target className="h-10 w-10 text-gray-600 mb-4" />
            <p className="text-white font-semibold mb-2">No games on this slate</p>
            <p className="text-gray-400 text-sm">Check back when games are scheduled.</p>
          </div>
        )}

        {/* Picks Content */}
        {!loading && !error && allPicks.length > 0 && (
          <>
            {/* Summary Strip */}
            <div className="mb-6 grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-900/70 backdrop-blur-md border border-slate-800 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-white">{totalGames}</p>
                <p className="text-[10px] uppercase tracking-widest text-gray-500">Games</p>
              </div>
              <div className="bg-slate-900/70 backdrop-blur-md border border-emerald-500/20 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-emerald-400">{topPicks.length}</p>
                <p className="text-[10px] uppercase tracking-widest text-gray-500">Top Picks</p>
              </div>
              <div className="bg-slate-900/70 backdrop-blur-md border border-yellow-400/20 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-yellow-400">{strongLeans.length}</p>
                <p className="text-[10px] uppercase tracking-widest text-gray-500">Strong Leans</p>
              </div>
              <div className="bg-slate-900/70 backdrop-blur-md border border-slate-800 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-gray-300">{watchlist.length}</p>
                <p className="text-[10px] uppercase tracking-widest text-gray-500">Watchlist</p>
              </div>
            </div>

            {/* Top Picks Section */}
            {topPicks.length > 0 && (
              <div className="mb-8">
                <div className="flex items-center gap-2 mb-4">
                  <TrendingUp className="w-5 h-5 text-emerald-400" />
                  <h2 className="text-lg font-bold text-white tracking-tight">Top Picks</h2>
                  <span className="text-xs text-gray-500 ml-1">Highest conviction plays</span>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {topPicks.map((fp, i) => (
                    <PickCard key={`${fp.game.id}-${fp.market}-${i}`} fp={fp} />
                  ))}
                </div>
              </div>
            )}

            {/* Strong Leans Section */}
            {strongLeans.length > 0 && (
              <div className="mb-8">
                <div className="flex items-center gap-2 mb-4">
                  <Target className="w-5 h-5 text-yellow-400" />
                  <h2 className="text-lg font-bold text-white tracking-tight">Strong Leans</h2>
                  <span className="text-xs text-gray-500 ml-1">Above-average edge identified</span>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {strongLeans.map((fp, i) => (
                    <PickCard key={`${fp.game.id}-${fp.market}-${i}`} fp={fp} />
                  ))}
                </div>
              </div>
            )}

            {/* Watchlist Section */}
            {watchlist.length > 0 && (
              <div className="mb-8">
                <div className="flex items-center gap-2 mb-4">
                  <Clock className="w-5 h-5 text-gray-400" />
                  <h2 className="text-lg font-bold text-white tracking-tight">Watchlist</h2>
                  <span className="text-xs text-gray-500 ml-1">Monitor for line movement</span>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {watchlist.map((fp, i) => (
                    <PickCard key={`${fp.game.id}-${fp.market}-${i}`} fp={fp} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* Has games but no qualifying picks */}
        {!loading && !error && totalGames > 0 && allPicks.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24">
            <Target className="h-10 w-10 text-gray-600 mb-4" />
            <p className="text-white font-semibold mb-2">{totalGames} games on the board</p>
            <p className="text-gray-400 text-sm text-center max-w-md">
              No plays meet the confidence threshold right now.
              The model requires score 65+ to surface a pick.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default GamesPage;

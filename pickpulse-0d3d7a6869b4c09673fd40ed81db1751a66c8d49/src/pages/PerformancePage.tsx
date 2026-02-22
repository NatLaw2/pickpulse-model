// src/pages/PerformancePage.tsx
import { useEffect, useMemo, useState } from "react";
import {
  fetchPerformanceSummary,
  fetchModelHealth,
  PerformanceRange,
  PerformanceSource,
  ModelHealth,
  ConfidenceBucketPerformance,
  SportPerformance,
} from "@/lib/performance";
import {
  Trophy,
  Target,
  BarChart3,
  Activity,
  Clock,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Loader2,
  Zap,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function pctColor(pct: number): string {
  if (pct >= 55) return "text-emerald-400";
  if (pct >= 50) return "text-yellow-400";
  return "text-red-400";
}

function unitsColor(u: number): string {
  if (u > 0) return "text-emerald-400";
  if (u < 0) return "text-red-400";
  return "text-gray-400";
}

function fmtUnits(u: number): string {
  return `${u >= 0 ? "+" : ""}${u.toFixed(2)}`;
}

// ---------------------------------------------------------------------------
// Animated Percentage Ring
// ---------------------------------------------------------------------------

function PercentRing({
  value,
  size = 80,
  stroke = 6,
  color = "emerald",
}: {
  value: number;
  size?: number;
  stroke?: number;
  color?: string;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.min(value, 100) / 100) * circumference;

  const colorMap: Record<string, string> = {
    emerald: "stroke-emerald-400",
    yellow: "stroke-yellow-400",
    slate: "stroke-slate-400",
    red: "stroke-red-400",
  };

  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth={stroke}
        className="text-slate-800"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        className={`${colorMap[color] ?? colorMap.emerald} transition-all duration-1000 ease-out`}
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RangeSelector({
  selected,
  onChange,
}: {
  selected: PerformanceRange;
  onChange: (r: PerformanceRange) => void;
}) {
  const options: { value: PerformanceRange; label: string }[] = [
    { value: "7d", label: "7D" },
    { value: "30d", label: "30D" },
    { value: "season", label: "Season" },
  ];

  return (
    <div className="inline-flex rounded-lg bg-slate-900/70 border border-slate-800 p-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${
            selected === opt.value
              ? "bg-emerald-500 text-black"
              : "text-gray-400 hover:text-white"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function SourceToggle({
  selected,
  onChange,
}: {
  selected: PerformanceSource;
  onChange: (s: PerformanceSource) => void;
}) {
  return (
    <div className="inline-flex rounded-lg bg-slate-900/70 border border-slate-800 p-1">
      <button
        onClick={() => onChange("live")}
        className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${
          selected === "live"
            ? "bg-white text-black"
            : "text-gray-400 hover:text-white"
        }`}
      >
        Live
      </button>
      <button
        onClick={() => onChange("backtest")}
        className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${
          selected === "backtest"
            ? "bg-white text-black"
            : "text-gray-400 hover:text-white"
        }`}
      >
        Backtest
      </button>
    </div>
  );
}

function StatTile({
  label,
  value,
  sub,
  icon: Icon,
  valueClass = "text-white",
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ComponentType<{ className?: string }>;
  valueClass?: string;
}) {
  return (
    <div className="bg-slate-900/70 backdrop-blur-md border border-slate-800 rounded-xl p-5 shadow-lg hover:shadow-2xl transition-all duration-300">
      <div className="flex items-center gap-2 mb-3">
        <div className="p-2 rounded-lg bg-slate-800">
          <Icon className="h-4 w-4 text-emerald-400" />
        </div>
        <span className="text-[10px] uppercase tracking-widest text-gray-500">{label}</span>
      </div>
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

function BucketCard({
  title,
  bucket,
  accent,
  icon: Icon,
}: {
  title: string;
  bucket: ConfidenceBucketPerformance | undefined;
  accent: "emerald" | "yellow" | "slate";
  icon: React.ComponentType<{ className?: string }>;
}) {
  const borderMap = {
    emerald: "border-emerald-500/30",
    yellow: "border-yellow-400/30",
    slate: "border-slate-700",
  };
  const bgMap = {
    emerald: "bg-emerald-500/5",
    yellow: "bg-yellow-400/5",
    slate: "bg-slate-800/30",
  };
  const iconColor = {
    emerald: "text-emerald-400",
    yellow: "text-yellow-400",
    slate: "text-gray-400",
  };

  const wins = bucket?.wins ?? 0;
  const losses = bucket?.losses ?? 0;
  const pushes = bucket?.pushes ?? 0;
  const pct = bucket?.percentage ?? 0;
  const units = bucket?.units ?? 0;
  const picks = bucket?.picks ?? 0;
  const hasData = picks > 0;

  return (
    <div
      className={`
        backdrop-blur-md rounded-xl p-5 shadow-lg hover:shadow-2xl transition-all duration-300
        border ${borderMap[accent]} ${bgMap[accent]}
      `}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Icon className={`h-5 w-5 ${iconColor[accent]}`} />
          <h3 className="text-sm font-bold text-white">{title}</h3>
        </div>
        {hasData && (
          <div className="relative">
            <PercentRing value={pct} size={52} stroke={4} color={accent} />
            <span className="absolute inset-0 flex items-center justify-center text-[11px] font-bold text-white">
              {pct.toFixed(0)}%
            </span>
          </div>
        )}
      </div>

      {!hasData ? (
        <p className="text-sm text-gray-500">No graded picks</p>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-2xl font-bold text-white">
              {wins}<span className="text-gray-600">-</span>{losses}
            </p>
            <p className="text-[10px] uppercase tracking-widest text-gray-500">Record</p>
          </div>
          <div>
            <p className={`text-2xl font-bold ${unitsColor(units)}`}>
              {fmtUnits(units)}u
            </p>
            <p className="text-[10px] uppercase tracking-widest text-gray-500">Units</p>
          </div>
          <div>
            <p className="text-lg font-bold text-gray-300">{picks}</p>
            <p className="text-[10px] uppercase tracking-widest text-gray-500">Picks</p>
          </div>
          {pushes > 0 && (
            <div>
              <p className="text-lg font-bold text-gray-400">{pushes}</p>
              <p className="text-[10px] uppercase tracking-widest text-gray-500">Pushes</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SportCard({ sport }: { sport: SportPerformance }) {
  const label = sport.sport?.toUpperCase() ?? "—";
  const o = sport.overall;
  const total = o.wins + o.losses;
  if (total === 0 && sport.totalPicks === 0) return null;

  const markets = [
    { key: "moneyline", label: "ML", data: sport.moneyline },
    { key: "spread", label: "Spread", data: sport.spread },
    { key: "overUnder", label: "O/U", data: sport.overUnder },
  ];

  return (
    <div className="bg-slate-900/70 backdrop-blur-md border border-slate-800 rounded-xl p-5 shadow-lg hover:shadow-2xl transition-all duration-300">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-white">{label}</h3>
        <span className={`text-sm font-bold ${pctColor(o.percentage)}`}>
          {o.percentage}%
        </span>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <span className="text-xl font-bold text-white">
          {o.wins}<span className="text-gray-600">-</span>{o.losses}
        </span>
        {typeof (o as any).units === "number" && (
          <span className={`text-sm font-bold ${unitsColor((o as any).units)}`}>
            {fmtUnits((o as any).units)}u
          </span>
        )}
        <span className="text-xs text-gray-500">{sport.totalPicks} picks</span>
      </div>

      {/* Market breakdown */}
      <div className="space-y-2">
        {markets.map((m) => {
          const w = m.data.wins;
          const l = m.data.losses;
          const t = w + l;
          if (t === 0) return null;
          return (
            <div key={m.key} className="flex items-center justify-between">
              <span className="text-xs text-gray-500 w-14">{m.label}</span>
              <div className="flex-1 mx-3 bg-slate-800 rounded-full h-1.5">
                <div
                  className="bg-emerald-400 h-1.5 rounded-full transition-all duration-700"
                  style={{ width: `${t > 0 ? (w / t) * 100 : 0}%` }}
                />
              </div>
              <span className="text-xs text-gray-400 font-mono w-16 text-right">
                {w}-{l} ({m.data.percentage}%)
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export const PerformancePage = () => {
  const [timeRange, setTimeRange] = useState<PerformanceRange>("30d");
  const [source, setSource] = useState<PerformanceSource>("live");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof fetchPerformanceSummary>> | null>(null);

  const [healthLoading, setHealthLoading] = useState(false);
  const [health, setHealth] = useState<ModelHealth | null>(null);

  // Load performance summary
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchPerformanceSummary(source, timeRange);
        if (!cancelled) setSummary(data);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "Failed to load performance");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [source, timeRange]);

  // Load model health
  useEffect(() => {
    let cancelled = false;
    async function loadHealth() {
      setHealthLoading(true);
      try {
        const data = await fetchModelHealth(source);
        if (!cancelled) setHealth(data);
      } catch {
        // silently fail
      } finally {
        if (!cancelled) setHealthLoading(false);
      }
    }
    loadHealth();
    return () => { cancelled = true; };
  }, [source]);

  const overall = useMemo(() => {
    if (!summary?.ok) return { wins: 0, losses: 0, picks: 0, percentage: 0, units: 0 };
    return summary.overall;
  }, [summary]);

  const hasData = overall.picks > 0;

  const sportsWithData = useMemo(() => {
    if (!summary?.ok) return [];
    return (summary.sports ?? []).filter(
      (s) => s.totalPicks > 0 || s.overall.wins + s.overall.losses > 0,
    );
  }, [summary]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-black">
      {/* Header */}
      <div className="sticky top-0 z-30 bg-slate-950/80 backdrop-blur-xl border-b border-slate-800/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
                PERFORMANCE
              </h1>
              <p className="text-sm text-gray-400 mt-0.5">
                Historical accuracy and results tracking
              </p>
            </div>
            <div className="flex items-center gap-3">
              <SourceToggle selected={source} onChange={setSource} />
              <RangeSelector selected={timeRange} onChange={setTimeRange} />
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-24">
            <Loader2 className="h-8 w-8 text-emerald-400 animate-spin mb-4" />
            <p className="text-gray-400 text-sm">Loading performance data...</p>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="flex flex-col items-center justify-center py-24">
            <AlertCircle className="h-10 w-10 text-red-400 mb-4" />
            <p className="text-white font-semibold mb-2">Failed to load performance</p>
            <p className="text-gray-400 text-sm">{error}</p>
          </div>
        )}

        {!loading && !error && (
          <>
            {/* Model Health Strip */}
            <div className="mb-6 bg-slate-900/70 backdrop-blur-md border border-slate-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <Activity className="h-4 w-4 text-emerald-400" />
                <span className="text-[10px] uppercase tracking-widest text-gray-500">System Status</span>
                {health?.ok && (
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Picks Today</p>
                  <p className="text-lg font-bold text-white font-mono">
                    {healthLoading ? "—" : source === "live" ? (health?.trackedToday ?? "—") : "—"}
                  </p>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Graded Games</p>
                  <p className="text-lg font-bold text-white font-mono">
                    {healthLoading ? "—" : (health?.gradedGames ?? "—")}
                  </p>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Last Updated</p>
                  <p className="text-sm font-mono text-white">
                    {healthLoading ? "—" : fmtDateTime(health?.lastUpdatedAt ?? null)}
                  </p>
                </div>
              </div>
            </div>

            {/* Hero Metrics */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
              <div className="col-span-2 lg:col-span-1 bg-slate-900/70 backdrop-blur-md border border-emerald-500/20 rounded-xl p-5 shadow-lg flex flex-col items-center justify-center">
                <div className="relative mb-2">
                  <PercentRing value={hasData ? overall.percentage : 0} size={88} stroke={6} color={overall.percentage >= 50 ? "emerald" : "red"} />
                  <span className="absolute inset-0 flex items-center justify-center text-xl font-bold text-white">
                    {hasData ? `${overall.percentage}%` : "—"}
                  </span>
                </div>
                <p className="text-[10px] uppercase tracking-widest text-gray-500">Win Rate</p>
              </div>

              <StatTile
                label="Record"
                value={hasData ? `${overall.wins}-${overall.losses}` : "—"}
                icon={Trophy}
              />
              <StatTile
                label="Total Picks"
                value={hasData ? `${overall.picks}` : "—"}
                icon={BarChart3}
              />
              <StatTile
                label="Units P/L"
                value={
                  hasData && typeof overall.units === "number"
                    ? fmtUnits(overall.units)
                    : "—"
                }
                icon={
                  hasData && typeof overall.units === "number" && overall.units >= 0
                    ? TrendingUp
                    : TrendingDown
                }
                valueClass={
                  hasData && typeof overall.units === "number"
                    ? unitsColor(overall.units)
                    : "text-gray-500"
                }
              />
              <StatTile
                label="Last Graded"
                value={summary?.updatedAt ? fmtDateTime(summary.updatedAt) : "—"}
                icon={Clock}
              />
            </div>

            {/* No Data State */}
            {!hasData && (
              <div className="bg-slate-900/70 backdrop-blur-md border border-slate-800 rounded-xl p-8 text-center mb-6">
                <Target className="h-10 w-10 text-gray-600 mx-auto mb-4" />
                <p className="text-white font-semibold mb-2">No performance data yet</p>
                <p className="text-gray-400 text-sm max-w-md mx-auto">
                  {source === "live"
                    ? "Performance metrics will appear once live picks are recorded and graded."
                    : "Backtest metrics will appear once a historical backtest run is completed."}
                </p>
              </div>
            )}

            {/* Confidence Buckets */}
            {summary?.confidenceBuckets && hasData && (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <Zap className="w-5 h-5 text-emerald-400" />
                  <h2 className="text-lg font-bold text-white tracking-tight">By Confidence Tier</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <BucketCard
                    title="Top Picks"
                    bucket={summary.confidenceBuckets.top}
                    accent="emerald"
                    icon={Trophy}
                  />
                  <BucketCard
                    title="High Confidence"
                    bucket={summary.confidenceBuckets.high}
                    accent="yellow"
                    icon={TrendingUp}
                  />
                  <BucketCard
                    title="Medium Confidence"
                    bucket={summary.confidenceBuckets.medium}
                    accent="slate"
                    icon={Target}
                  />
                </div>
              </div>
            )}

            {/* Sports Breakdown */}
            {sportsWithData.length > 0 && (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <BarChart3 className="w-5 h-5 text-emerald-400" />
                  <h2 className="text-lg font-bold text-white tracking-tight">By Sport</h2>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {sportsWithData.map((sp) => (
                    <SportCard key={sp.sport} sport={sp} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default PerformancePage;

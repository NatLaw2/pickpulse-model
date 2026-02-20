// src/pages/PerformancePage.tsx
import { useEffect, useMemo, useState } from "react";
import { TimeRangeSelector } from "@/components/performance/TimeRangeSelector";
import { SportPerformanceCard } from "@/components/performance/SportPerformanceCard";
import { BarChart3, Trophy, Target, AlertCircle, Activity } from "lucide-react";
import {
  fetchPerformanceSummary,
  fetchModelHealth,
  PerformanceRange,
  PerformanceSource,
  ModelHealth,
  ConfidenceBucketPerformance,
} from "@/lib/performance";

function fmtDateTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

export const PerformancePage = () => {
  const [timeRange, setTimeRange] = useState<PerformanceRange>("30d");
  const [source, setSource] = useState<PerformanceSource>("live");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [summary, setSummary] = useState<Awaited<ReturnType<typeof fetchPerformanceSummary>> | null>(null);

  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);
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
    return () => {
      cancelled = true;
    };
  }, [source, timeRange]);

  // Load model health (read-only system status)
  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      setHealthLoading(true);
      setHealthError(null);

      try {
        const data = await fetchModelHealth(source);
        if (!cancelled) setHealth(data);
      } catch (e: any) {
        if (!cancelled) setHealthError(e?.message ?? "Failed to load model health");
      } finally {
        if (!cancelled) setHealthLoading(false);
      }
    }

    loadHealth();
    return () => {
      cancelled = true;
    };
  }, [source]);

  const overallStats = useMemo(() => {
    if (!summary?.ok) {
      return { wins: 0, losses: 0, picks: 0, percentage: 0 };
    }
    return summary.overall;
  }, [summary]);

  const performanceData = useMemo(() => (summary?.ok ? summary.sports : []), [summary]);

  const hasData = overallStats.picks > 0;

  return (
    <div className="container py-8">
      <div className="mb-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-3xl font-bold text-foreground mb-2">Performance</h1>
            <p className="text-muted-foreground">Historical accuracy and results tracking</p>

            {/* Source toggle */}
            <div className="mt-3 inline-flex rounded-lg border border-border bg-card p-1">
              <button
                type="button"
                onClick={() => setSource("live")}
                className={[
                  "px-3 py-1.5 text-sm rounded-md transition-colors",
                  source === "live"
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                ].join(" ")}
                title="Tracked results from live picks"
              >
                Live
              </button>

              <button
                type="button"
                onClick={() => setSource("backtest")}
                className={[
                  "px-3 py-1.5 text-sm rounded-md transition-colors",
                  source === "backtest"
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                ].join(" ")}
                title="Simulated results from historical backtest"
              >
                Backtest <span className="ml-1 text-xs opacity-80">(simulated)</span>
              </button>
            </div>
          </div>

          <TimeRangeSelector selected={timeRange} onChange={setTimeRange} />
        </div>

        {/* Model Health Strip */}
        <div className="mb-6 bg-card rounded-2xl border border-border p-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Activity className="h-4 w-4 text-primary" />
            </div>
            <h3 className="text-sm font-semibold text-foreground">Model Health</h3>
            {healthError ? <span className="text-xs text-destructive ml-2">{healthError}</span> : null}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="rounded-xl border border-border p-3">
              <p className="text-xs text-muted-foreground mb-1">Picks tracked today</p>
              <p className="text-lg font-bold font-mono">
                {healthLoading ? "—" : source === "live" ? (health?.trackedToday ?? "—") : "—"}
              </p>
            </div>

            <div className="rounded-xl border border-border p-3">
              <p className="text-xs text-muted-foreground mb-1">Graded games</p>
              <p className="text-lg font-bold font-mono">{healthLoading ? "—" : (health?.gradedGames ?? "—")}</p>
            </div>

            <div className="rounded-xl border border-border p-3">
              <p className="text-xs text-muted-foreground mb-1">Last injury update</p>
              <p className="text-sm font-mono text-foreground">
                {healthLoading ? "—" : fmtDateTime(health?.lastUpdatedAt ?? null)}
              </p>
            </div>
          </div>

          {!hasData && !loading ? (
            <div className="mt-4 text-xs text-muted-foreground">
              <p className="mb-1">No graded results yet. That’s normal right now.</p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Once games finish and are graded, win/loss stats will populate automatically.</li>
                <li>In the meantime, “Model Health” confirms the pipeline is live and recording.</li>
              </ul>
            </div>
          ) : null}
        </div>

        {/* Confidence Breakdown Cards */}
        {summary?.confidenceBuckets ? (() => {
          const bucketConfig: Array<{
            key: keyof NonNullable<typeof summary.confidenceBuckets>;
            label: string;
            borderColor: string;
            bgColor: string;
          }> = [
            { key: "top", label: "Top Picks", borderColor: "border-primary/30", bgColor: "bg-primary/5" },
            { key: "high", label: "High Confidence", borderColor: "border-emerald-500/20", bgColor: "bg-emerald-500/5" },
            { key: "medium", label: "Medium Confidence", borderColor: "border-amber-500/20", bgColor: "bg-amber-500/5" },
          ];
          const hasBucketData = bucketConfig.some(
            (b) => (summary.confidenceBuckets?.[b.key]?.picks ?? 0) > 0,
          );
          if (!hasBucketData) return null;
          return (
            <div className="mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              {bucketConfig.map((cfg) => {
                const b: ConfidenceBucketPerformance | undefined = summary.confidenceBuckets?.[cfg.key];
                if (!b || b.picks === 0) return (
                  <div key={cfg.key} className={`rounded-2xl border ${cfg.borderColor} ${cfg.bgColor} p-5`}>
                    <div className="flex items-center gap-2 mb-3">
                      <Trophy className="h-4 w-4 text-muted-foreground" />
                      <h3 className="text-sm font-semibold text-foreground">{cfg.label}</h3>
                    </div>
                    <p className="text-sm text-muted-foreground">No graded picks</p>
                  </div>
                );
                return (
                  <div key={cfg.key} className={`rounded-2xl border ${cfg.borderColor} ${cfg.bgColor} p-5`}>
                    <div className="flex items-center gap-2 mb-3">
                      <Trophy className="h-4 w-4 text-primary" />
                      <h3 className="text-sm font-semibold text-foreground">{cfg.label}</h3>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-2xl font-bold font-mono text-foreground">
                          {b.wins}-{b.losses}
                        </p>
                        <p className="text-xs text-muted-foreground">Record</p>
                      </div>
                      <div>
                        <p className={`text-2xl font-bold font-mono ${b.percentage >= 50 ? "text-emerald-600" : "text-red-500"}`}>
                          {b.percentage}%
                        </p>
                        <p className="text-xs text-muted-foreground">Win Rate</p>
                      </div>
                      <div>
                        <p className={`text-lg font-bold font-mono ${b.units >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                          {b.units >= 0 ? "+" : ""}{b.units.toFixed(2)}u
                        </p>
                        <p className="text-xs text-muted-foreground">Units</p>
                      </div>
                      <div>
                        <p className="text-lg font-bold font-mono text-foreground">{b.picks}</p>
                        <p className="text-xs text-muted-foreground">Picks</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })() : null}

        {/* Overall Stats Banner */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="stat-card border-primary/30 glow-primary">
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <Trophy className="h-5 w-5 text-primary" />
              </div>
              <span className="text-sm font-medium text-muted-foreground">Overall Win Rate</span>
            </div>
            <p className="text-3xl font-bold font-mono text-success">
              {loading ? "—" : hasData ? `${overallStats.percentage}%` : "—"}
            </p>
          </div>

          <div className="stat-card">
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <Target className="h-5 w-5 text-primary" />
              </div>
              <span className="text-sm font-medium text-muted-foreground">Total Record</span>
            </div>
            <p className="text-3xl font-bold font-mono text-foreground">
              {loading ? (
                "—"
              ) : hasData ? (
                <>
                  {overallStats.wins}
                  <span className="text-muted-foreground">-</span>
                  {overallStats.losses}
                </>
              ) : (
                "—"
              )}
            </p>
          </div>

          <div className="stat-card">
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <BarChart3 className="h-5 w-5 text-primary" />
              </div>
              <span className="text-sm font-medium text-muted-foreground">Total Picks</span>
            </div>
            <p className="text-3xl font-bold font-mono text-foreground">
              {loading ? "—" : hasData ? overallStats.picks : "—"}
            </p>
          </div>

          {typeof overallStats.units === "number" ? (
            <div className="stat-card">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 rounded-lg bg-primary/10">
                  <BarChart3 className="h-5 w-5 text-primary" />
                </div>
                <span className="text-sm font-medium text-muted-foreground">Units P/L</span>
              </div>
              <p className={`text-3xl font-bold font-mono ${overallStats.units >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                {loading ? "—" : hasData ? `${overallStats.units >= 0 ? "+" : ""}${overallStats.units.toFixed(2)}` : "—"}
              </p>
            </div>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="flex flex-col items-center justify-center py-16 bg-card rounded-2xl border border-border">
          <AlertCircle className="h-12 w-12 text-destructive mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-2">Failed to load performance</h3>
          <p className="text-muted-foreground text-center max-w-md">{error}</p>
        </div>
      ) : !hasData && !loading ? (
        <div className="flex flex-col items-center justify-center py-16 bg-card rounded-2xl border border-border">
          <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-2">No performance data yet</h3>
          <p className="text-muted-foreground text-center max-w-md">
            {source === "live"
              ? "Performance metrics will appear once live picks are recorded and graded."
              : "Backtest metrics will appear once a historical backtest run is completed."}
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          <h2 className="text-xl font-semibold text-foreground">Performance by Sport</h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {performanceData.map((performance) => (
              <SportPerformanceCard key={performance.sport} performance={performance as any} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default PerformancePage;

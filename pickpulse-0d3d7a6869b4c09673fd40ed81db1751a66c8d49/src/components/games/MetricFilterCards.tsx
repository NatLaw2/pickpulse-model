// src/components/games/MetricFilterCards.tsx
import { TrendingUp, Target, Clock, LayoutGrid, X } from "lucide-react";

export type PickFilter = "all" | "top" | "strong" | "watchlist";

interface MetricCard {
  filter: PickFilter;
  label: string;
  count: number;
  icon: React.ComponentType<{ className?: string }>;
  accentBorder: string;
  accentText: string;
  accentGlow: string;
}

interface MetricFilterCardsProps {
  totalGames: number;
  topCount: number;
  strongCount: number;
  watchlistCount: number;
  active: PickFilter;
  onChange: (filter: PickFilter) => void;
}

export function MetricFilterCards({
  totalGames,
  topCount,
  strongCount,
  watchlistCount,
  active,
  onChange,
}: MetricFilterCardsProps) {
  const cards: MetricCard[] = [
    {
      filter: "all",
      label: "Games",
      count: totalGames,
      icon: LayoutGrid,
      accentBorder: "border-slate-600/40",
      accentText: "text-white",
      accentGlow: "shadow-slate-500/5",
    },
    {
      filter: "top",
      label: "Top Picks",
      count: topCount,
      icon: TrendingUp,
      accentBorder: "border-emerald-500/30",
      accentText: "text-emerald-400",
      accentGlow: "shadow-emerald-500/10",
    },
    {
      filter: "strong",
      label: "Strong Leans",
      count: strongCount,
      icon: Target,
      accentBorder: "border-yellow-400/30",
      accentText: "text-yellow-400",
      accentGlow: "shadow-yellow-400/10",
    },
    {
      filter: "watchlist",
      label: "Watchlist",
      count: watchlistCount,
      icon: Clock,
      accentBorder: "border-slate-700",
      accentText: "text-gray-300",
      accentGlow: "shadow-slate-500/5",
    },
  ];

  return (
    <div className="relative">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {cards.map((c) => {
          const isActive = active === c.filter;
          const Icon = c.icon;
          return (
            <button
              key={c.filter}
              onClick={() => {
                onChange(c.filter);
                document.getElementById("picks-list")?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className={`
                group relative text-left rounded-xl p-4 border transition-all duration-200
                backdrop-blur-md cursor-pointer
                ${isActive
                  ? `${c.accentBorder} bg-slate-800/80 ring-1 ring-white/10 shadow-lg ${c.accentGlow}`
                  : `border-slate-800/60 bg-slate-900/50 hover:bg-slate-800/60 hover:border-slate-700`
                }
              `}
            >
              <div className="flex items-center justify-between mb-2">
                <Icon className={`w-4 h-4 ${isActive ? c.accentText : "text-gray-500"} transition-colors`} />
                {isActive && c.filter !== "all" && (
                  <span className="text-gray-500 hover:text-gray-300 transition-colors">
                    <X className="w-3 h-3" />
                  </span>
                )}
              </div>
              <p className={`text-2xl font-bold tracking-tight ${isActive ? c.accentText : "text-white"} transition-colors`}>
                {c.count}
              </p>
              <p className="text-[10px] uppercase tracking-widest text-gray-500 mt-0.5">
                {c.label}
              </p>
            </button>
          );
        })}
      </div>

      {/* Clear filter pill */}
      {active !== "all" && (
        <div className="mt-3 flex justify-center">
          <button
            onClick={() => onChange("all")}
            className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white bg-slate-800/60 hover:bg-slate-700/60 rounded-full px-3 py-1 transition-colors"
          >
            <X className="w-3 h-3" />
            Clear filter
          </button>
        </div>
      )}
    </div>
  );
}

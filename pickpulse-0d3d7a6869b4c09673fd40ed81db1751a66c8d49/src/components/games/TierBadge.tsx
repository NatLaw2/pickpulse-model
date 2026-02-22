// src/components/games/TierBadge.tsx

type TierKey = "top_pick" | "strong_lean" | "watchlist";

interface TierBadgeProps {
  tier: TierKey | string;
  className?: string;
}

const TIER_CONFIG: Record<TierKey, { label: string; classes: string }> = {
  top_pick: {
    label: "TOP PICK",
    classes: "bg-emerald-500 text-black font-bold",
  },
  strong_lean: {
    label: "STRONG LEAN",
    classes: "bg-yellow-400 text-black font-bold",
  },
  watchlist: {
    label: "WATCHLIST",
    classes: "bg-slate-700 text-white font-medium",
  },
};

export function TierBadge({ tier, className = "" }: TierBadgeProps) {
  const config = TIER_CONFIG[tier as TierKey] ?? {
    label: tier.toUpperCase().replace(/_/g, " "),
    classes: "bg-slate-700 text-white",
  };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-[10px] uppercase tracking-widest ${config.classes} ${className}`}
    >
      {config.label}
    </span>
  );
}

export function tierFromScore(score: number): TierKey {
  if (score >= 74) return "top_pick";
  if (score >= 66) return "strong_lean";
  return "watchlist";
}

export type { TierKey };

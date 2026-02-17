import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  percentage: number;
  wins: number;
  losses: number;
  variant?: "default" | "highlight";
}

export const StatCard = ({ label, percentage, wins, losses, variant = "default" }: StatCardProps) => {
  // Treat "no graded games yet" as neutral
  const total = (wins ?? 0) + (losses ?? 0);
  const hasData = total > 0;

  const safePct =
    typeof percentage === "number" && Number.isFinite(percentage) ? Math.max(0, Math.min(100, percentage)) : 0;

  const isPositive = hasData && safePct >= 50;

  const pctText = hasData ? `${safePct}%` : "—";
  const recordText = hasData ? `${wins}W - ${losses}L` : "No graded games";

  return (
    <div className={cn("stat-card", variant === "highlight" && "border-primary/30 glow-primary")}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <h4 className="text-sm font-medium text-muted-foreground truncate">{label}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{recordText}</p>
        </div>

        <span
          className={cn(
            "text-2xl font-bold font-mono tabular-nums",
            !hasData && "text-muted-foreground",
            hasData && (isPositive ? "text-success" : "text-destructive"),
          )}
          aria-label={`${label} win rate`}
        >
          {pctText}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1">
          <div className="h-2.5 bg-muted/70 rounded-full overflow-hidden border border-border">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                !hasData && "bg-muted",
                hasData && (isPositive ? "bg-success" : "bg-destructive"),
              )}
              style={{ width: hasData ? `${safePct}%` : "0%" }}
            />
          </div>
        </div>

        <span className="text-xs font-mono text-muted-foreground tabular-nums">{hasData ? `${total} games` : "—"}</span>
      </div>
    </div>
  );
};

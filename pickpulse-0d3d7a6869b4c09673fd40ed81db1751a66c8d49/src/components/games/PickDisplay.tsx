import { MarketRecommendation } from "@/types/sports";
import { ConfidenceBadge } from "./ConfidenceBadge";

type PickDisplayProps = {
  title: string;
  recommendation: MarketRecommendation;
  oddsLine?: string;
};

export const PickDisplay = ({ title, recommendation, oddsLine }: PickDisplayProps) => {
  return (
    <div className="p-4 rounded-lg bg-muted/50 border border-border">
      <div className="flex items-start justify-between gap-4 mb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <span className="text-sm font-semibold text-foreground">{title}</span>
            {oddsLine && <span className="text-sm font-mono text-primary font-medium">{oddsLine}</span>}
          </div>
        </div>

        {recommendation.status === "pick" && <ConfidenceBadge confidence={recommendation.confidence} />}
      </div>

      {recommendation.status === "pick" ? (
        <div className="text-sm text-muted-foreground leading-relaxed">
          <p>
            <span className="text-foreground font-medium">{recommendation.selection}</span>
          </p>

          {recommendation.rationale && recommendation.rationale.length > 0 && (
            <ul className="mt-2 list-disc pl-5 space-y-1">
              {recommendation.rationale.slice(0, 5).map((reason, idx) => (
                <li key={idx}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground italic">No bet — {recommendation.reason}</p>
      )}
    </div>
  );
};

export default PickDisplay;

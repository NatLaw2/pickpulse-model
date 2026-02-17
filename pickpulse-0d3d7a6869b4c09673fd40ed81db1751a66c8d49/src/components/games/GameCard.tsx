import { useMemo, useState } from "react";
import { Game, Sport, MarketRecommendation } from "@/types/sports";
import { format } from "date-fns";
import { ChevronDown, ChevronUp, ExternalLink, Clock, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { useProps } from "@/hooks/useProps";

interface GameCardProps {
  game: Game;
}

const NO_BET: MarketRecommendation = {
  status: "no_bet",
  reason: "Model not available yet",
};

function pct(n: number) {
  return `${Math.round(n * 100)}%`;
}

export const GameCard = ({ game }: GameCardProps) => {
  const [expanded, setExpanded] = useState(false);
  const { data: propsData, isLoading: propsLoading } = useProps(game.sport as Sport, game.id, expanded);

  /**
   * ✅ primary source is `game.picks`
   * fallback to legacy `game.recommendation` if present
   */
  const recommendation = useMemo(() => {
    const picks = (game as any).picks;
    const rec = (game as any).recommendation;
    const src = picks ?? rec;

    return {
      moneyline: src?.moneyline ?? NO_BET,
      spread: src?.spread ?? NO_BET,
      total: src?.total ?? NO_BET,
    };
  }, [game]);

  const formatOdds = (odds: number | null) => {
    if (odds === null) return "N/A";
    return odds > 0 ? `+${odds}` : odds.toString();
  };

  const hasOdds = !!(game.odds && (game.odds.moneyline || game.odds.spread || game.odds.total));

  const renderModelMeta = (rec: any) => {
    if (!rec || rec.status !== "pick") return null;

    const confidencePct = typeof rec.confidence_pct === "number" ? rec.confidence_pct : null;
    const gbp = typeof rec.good_bet_prob === "number" ? rec.good_bet_prob : null;

    if (confidencePct === null && gbp === null) return null;

    // ✅ De-emphasized meta: smaller, muted, and visually "secondary"
    return (
      <div className="mt-3 border-t border-border/40 pt-2 flex flex-wrap gap-3 text-[10px] text-muted-foreground/80">
        {confidencePct !== null ? (
          <span className="font-mono">
            Model conf: <span className="text-muted-foreground">{confidencePct}%</span>
          </span>
        ) : null}

        {gbp !== null ? (
          <span className="font-mono">
            Good bet prob: <span className="text-muted-foreground">{pct(gbp)}</span>
          </span>
        ) : null}
      </div>
    );
  };

  const renderMarket = (title: string, oddsLine: string, rec: MarketRecommendation) => (
    <div className="p-4 rounded-lg bg-muted/50 border border-border">
      <div className="flex items-center justify-between gap-4 mb-2">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-foreground">{title}</span>
          <span className="text-sm font-mono text-primary font-medium">{oddsLine}</span>
        </div>

        {rec.status === "pick" ? <ConfidenceBadge confidence={rec.confidence} /> : null}
      </div>

      {rec.status === "pick" ? (
        <div className="text-sm text-muted-foreground leading-relaxed">
          <p>
            <span className="text-foreground font-medium">{rec.selection}</span>
          </p>

          {renderModelMeta(rec as any)}

          {rec.rationale?.length ? (
            <ul className="mt-2 list-disc pl-5 space-y-1">
              {rec.rationale.slice(0, 5).map((r, idx) => (
                <li key={idx}>{r}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground italic">No bet — {rec.reason}</p>
      )}
    </div>
  );

  return (
    // ✅ Anchor for scroll-to-game
    <div id={`game-${game.id}`} className="game-card scroll-mt-24">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 flex items-center justify-between gap-4 text-left"
        type="button"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-4 mb-2">
            <div className="flex-1 flex items-center gap-3">
              <span className="font-semibold text-foreground truncate">{game.awayTeam.name}</span>
              <span className="text-xs text-muted-foreground font-medium px-2 py-0.5 bg-muted rounded">@</span>
              <span className="font-semibold text-foreground truncate">{game.homeTeam.name}</span>
            </div>
          </div>

          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            <span>{format(new Date(game.startTime), "h:mm a")}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span
            className={cn(
              "text-sm font-medium px-3 py-1.5 rounded-lg transition-colors",
              expanded ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
            )}
          >
            {expanded ? "Hide Analysis" : "View Picks"}
          </span>
          {expanded ? (
            <ChevronUp className="h-5 w-5 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-5 w-5 text-muted-foreground" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border p-4 animate-fade-in">
          {hasOdds ? (
            <div className="space-y-4 mb-4">
              {game.odds.moneyline &&
                renderMarket(
                  "Moneyline",
                  `${game.awayTeam.abbreviation} ${formatOdds(game.odds.moneyline.away)} / ${game.homeTeam.abbreviation} ${formatOdds(
                    game.odds.moneyline.home,
                  )}`,
                  recommendation.moneyline,
                )}

              {game.odds.spread &&
                (game.odds.spread.home || game.odds.spread.away) &&
                renderMarket(
                  "Spread",
                  `${game.awayTeam.abbreviation} ${game.odds.spread.away?.point ?? "N/A"} (${formatOdds(
                    game.odds.spread.away?.price ?? null,
                  )}) / ${game.homeTeam.abbreviation} ${game.odds.spread.home?.point ?? "N/A"} (${formatOdds(
                    game.odds.spread.home?.price ?? null,
                  )})`,
                  recommendation.spread,
                )}

              {game.odds.total &&
                (game.odds.total.over || game.odds.total.under) &&
                renderMarket(
                  "Over/Under",
                  `O/U ${game.odds.total.over?.point ?? game.odds.total.under?.point ?? "N/A"} (${formatOdds(
                    game.odds.total.over?.price ?? null,
                  )}/${formatOdds(game.odds.total.under?.price ?? null)})`,
                  recommendation.total,
                )}
            </div>
          ) : (
            <div className="p-4 rounded-lg bg-muted/50 border border-border mb-4">
              <p className="text-sm text-muted-foreground italic text-center">No odds data available for this game</p>
            </div>
          )}

          <div className="mb-4">
            <h4 className="text-sm font-semibold text-foreground mb-3">Player Props</h4>

            {propsLoading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                <span className="ml-2 text-sm text-muted-foreground">Loading props...</span>
              </div>
            ) : propsData && propsData.length > 0 ? (
              <div className="space-y-3">
                {propsData.slice(0, 3).map((propMarket) => (
                  <div key={propMarket.market} className="p-3 rounded-lg bg-muted/30 border border-border">
                    <p className="text-xs font-medium text-muted-foreground mb-2">{propMarket.marketLabel}</p>
                    <div className="space-y-1">
                      {propMarket.props.slice(0, 3).map((prop, idx) => (
                        <div key={idx} className="flex items-center justify-between text-sm">
                          <span className="text-foreground">{prop.player}</span>
                          <span className="font-mono text-muted-foreground">
                            {prop.line !== null ? `${prop.line}` : "N/A"}
                            {prop.over !== null && ` (${formatOdds(prop.over)})`}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground italic text-center py-4">No player props available</p>
            )}
          </div>

          <div className="pt-4 border-t border-border flex flex-wrap gap-3">
            <a
              href="https://www.fanduel.com"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-secondary text-secondary-foreground text-sm font-medium hover:bg-secondary/80 transition-colors"
            >
              View on FanDuel
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
            <a
              href="https://www.draftkings.com"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-secondary text-secondary-foreground text-sm font-medium hover:bg-secondary/80 transition-colors"
            >
              View on DraftKings
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      )}
    </div>
  );
};

export default GameCard;

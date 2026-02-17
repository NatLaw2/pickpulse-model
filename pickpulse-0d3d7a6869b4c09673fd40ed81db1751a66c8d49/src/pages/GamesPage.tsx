import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { DateFilter, Sport } from "@/types/sports";
import { DateTabs } from "@/components/games/DateTabs";
import { SportSection } from "@/components/games/SportSection";
import { useSlate } from "@/hooks/useSlate";
import { getDecisionSlate, DecisionSlateResponse } from "@/integrations/supabase/getModelPicks";
import { fetchPerformanceSummary, PerformanceSummaryResponse } from "@/lib/performance";
import { Calendar, TrendingUp, Loader2, AlertCircle, ChevronDown, ChevronRight, AlertTriangle, Trophy, ArrowRight, Mail } from "lucide-react";
import WhyPickPulseModal from "@/components/WhyPickPulseModal";

const sports: Sport[] = ["nba", "mlb", "nhl", "ncaab", "ncaaf", "nfl"];

/** -----------------------------
 * Helpers
 * ----------------------------- */
function capConfidence(conf: number, tier: "top" | "strong" | "watch") {
  if (tier === "top") return Math.min(conf, 0.92);
  if (tier === "strong") return Math.min(conf, 0.88);
  return Math.min(conf, 0.82);
}

function confidenceLabel(conf: number) {
  if (conf >= 0.88) return "high";
  if (conf >= 0.75) return "medium";
  return "low";
}

function confidencePillClasses(label?: string | null) {
  if (label === "high") return "bg-emerald-500/15 text-emerald-600 border-emerald-500/20";
  if (label === "medium") return "bg-amber-500/15 text-amber-600 border-amber-500/20";
  return "bg-muted text-muted-foreground border-border";
}

function marketLabel(m: string) {
  if (m === "moneyline") return "ML";
  if (m === "spread") return "Spread";
  if (m === "total") return "Total";
  return m;
}

function leagueLabel(sport: Sport) {
  const map: Record<Sport, string> = {
    nba: "NBA",
    mlb: "MLB",
    nhl: "NHL",
    ncaab: "NCAAB",
    ncaaf: "NCAAF",
    nfl: "NFL",
  };
  return map[sport] ?? sport.toUpperCase();
}

/** -----------------------------
 * Matchup Logos (Option B)
 * ----------------------------- */

// ESPN NBA logo CDN uses lowercase abbreviations: ind, cha, lal, etc.
function nbaLogoUrl(abbr: string) {
  const a = (abbr || "").trim().toLowerCase();
  return `https://a.espncdn.com/i/teamlogos/nba/500/${a}.png`;
}

function safeAbbr(abbr?: string | null) {
  const a = (abbr || "").trim().toUpperCase();
  return a.length ? a : null;
}

/**
 * Best-effort to find team abbreviations from the pick object.
 * We try a few common property names first, then attempt to parse from "side"
 * when it looks like "IND ML" or "CHA Spread" etc.
 */
function getPickAbbrs(p: any): { homeAbbr: string | null; awayAbbr: string | null } {
  // common property names (depending on how decision-slate is shaped)
  const home =
    safeAbbr(p?.home_abbr) || safeAbbr(p?.home_team_abbr) || safeAbbr(p?.homeAbbr) || safeAbbr(p?.homeTeamAbbr);

  const away =
    safeAbbr(p?.away_abbr) || safeAbbr(p?.away_team_abbr) || safeAbbr(p?.awayAbbr) || safeAbbr(p?.awayTeamAbbr);

  if (home && away) return { homeAbbr: home, awayAbbr: away };

  // fallback: parse "side" if it starts with an abbreviation (e.g. "IND ML")
  // This won't always give both, but it prevents breaking and still adds life when possible.
  const side = typeof p?.side === "string" ? p.side.trim() : "";
  const token = side.split(/\s+/)[0]?.toUpperCase();
  const maybeTeam = token && token.length <= 4 ? token : null;

  // If we only have one, return it as "home" and keep away null
  // (component will render nothing unless both exist)
  return { homeAbbr: home ?? maybeTeam, awayAbbr: away ?? null };
}

function MatchupLogos({
  homeAbbr,
  awayAbbr,
  className,
}: {
  homeAbbr: string | null;
  awayAbbr: string | null;
  className?: string;
}) {
  const [homeOk, setHomeOk] = useState(true);
  const [awayOk, setAwayOk] = useState(true);

  if (!homeAbbr || !awayAbbr) return null;

  return (
    <div className={["flex items-center gap-2", className].filter(Boolean).join(" ")}>
      {homeOk ? (
        <img
          src={nbaLogoUrl(homeAbbr)}
          alt={`${homeAbbr} logo`}
          className="w-7 h-7 object-contain"
          loading="lazy"
          onError={() => setHomeOk(false)}
        />
      ) : (
        <div className="w-7 h-7" />
      )}

      <span className="text-xs text-muted-foreground">vs</span>

      {awayOk ? (
        <img
          src={nbaLogoUrl(awayAbbr)}
          alt={`${awayAbbr} logo`}
          className="w-7 h-7 object-contain opacity-60"
          loading="lazy"
          onError={() => setAwayOk(false)}
        />
      ) : (
        <div className="w-7 h-7" />
      )}
    </div>
  );
}

/** -----------------------------
 * Health banner (silent unless broken)
 * ----------------------------- */
type HealthStatus = { ok: true } | { ok: false; reason: string; detail?: string };

function HealthBanner({ reason, detail }: { reason: string; detail?: string }) {
  return (
    <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-700">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4" />
        <span className="font-medium">{reason}</span>
      </div>
      {detail ? <div className="mt-1 text-xs opacity-70">{detail}</div> : null}
    </div>
  );
}

function useSupabaseHealthCheck() {
  const [status, setStatus] = useState<HealthStatus>({ ok: true });

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const baseUrl = import.meta.env.VITE_SUPABASE_URL;
        const anonKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

        if (!baseUrl || !anonKey) {
          throw new Error("Missing Supabase env vars (VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY)");
        }

        const res = await fetch(`${baseUrl}/functions/v1/decision-slate?day=today`, {
          method: "GET",
          headers: {
            apikey: anonKey,
            authorization: `Bearer ${anonKey}`,
          },
        });

        if (!res.ok) {
          const hint =
            res.status === 401 || res.status === 403
              ? "Auth rejected (likely project ref / key mismatch)."
              : res.status === 404
                ? "Function not found on this project."
                : `HTTP ${res.status}`;

          throw new Error(hint);
        }

        if (!cancelled) setStatus({ ok: true });
      } catch (err: any) {
        if (!cancelled) {
          setStatus({
            ok: false,
            reason: "Connection issue: Picks service unavailable",
            detail: err?.message ? String(err.message) : "Unknown error",
          });
        }
      }
    }

    check();
    return () => {
      cancelled = true;
    };
  }, []);

  return status;
}

/** -----------------------------
 * Line movement ticker (Top Pick only)
 * ----------------------------- */
type LineMoveState = "tracking" | "up" | "down" | "flat" | "stale";

function LineMovementTicker(props: {
  state: LineMoveState;
  marketLabel?: string;
  openText?: string;
  currentText?: string;
  updatedAtText?: string;
}) {
  const { state, marketLabel, openText, currentText, updatedAtText } = props;

  const base = "mt-3 inline-flex flex-wrap items-center gap-2 rounded-md border px-2 py-1 text-xs font-mono";
  const neutral = "border-border text-muted-foreground bg-background/30";
  const up = "border-emerald-500/20 text-emerald-600 bg-emerald-500/10";
  const down = "border-amber-500/20 text-amber-600 bg-amber-500/10";

  const cls = state === "up" ? `${base} ${up}` : state === "down" ? `${base} ${down}` : `${base} ${neutral}`;

  if (state === "tracking") {
    return (
      <div className={cls} title="Line movement for Top Pick (coming next)">
        <span>Line movement:</span>
        <span className="text-foreground/90">{marketLabel ?? "Market"}</span>
        <span>tracking…</span>
      </div>
    );
  }

  if (state === "flat") {
    return (
      <div className={cls} title="Line movement since open">
        <span>Line movement:</span>
        <span className="text-foreground/90">{marketLabel ?? "Market"}</span>
        <span>unchanged</span>
      </div>
    );
  }

  if (state === "stale") {
    return (
      <div className={cls} title="Line movement since open">
        <span>Line movement:</span>
        <span className="text-foreground/90">{marketLabel ?? "Market"}</span>
        <span>market stale</span>
      </div>
    );
  }

  const arrow = state === "up" ? "▲" : "▼";

  return (
    <div className={cls} title="Line movement since open">
      <span>Line movement:</span>
      <span className="text-foreground/90">{marketLabel ?? "Market"}</span>
      <span>
        {openText ?? "open"} → {currentText ?? "now"} {arrow}
      </span>
      {updatedAtText ? <span className="opacity-70">({updatedAtText})</span> : null}
    </div>
  );
}

function getTopPickLineMove(topPick: any): {
  state: LineMoveState;
  marketLabel?: string;
  openText?: string;
  currentText?: string;
  updatedAtText?: string;
} {
  if (!topPick) return { state: "tracking" };

  const lm = topPick?.signals?.line_movement;
  const mkt = marketLabel(topPick.market);

  if (!lm) {
    return { state: "tracking", marketLabel: mkt };
  }

  const dir = lm.direction as string | undefined;
  const updatedAt = lm.updated_at ? new Date(lm.updated_at).toLocaleTimeString() : undefined;

  const open =
    typeof lm.open?.price === "number"
      ? `${lm.open.price}`
      : typeof lm.open?.point === "number"
        ? `${lm.open.point}`
        : undefined;

  const cur =
    typeof lm.current?.price === "number"
      ? `${lm.current.price}`
      : typeof lm.current?.point === "number"
        ? `${lm.current.point}`
        : undefined;

  if (dir === "up") {
    return { state: "up", marketLabel: mkt, openText: open, currentText: cur, updatedAtText: updatedAt };
  }
  if (dir === "down") {
    return { state: "down", marketLabel: mkt, openText: open, currentText: cur, updatedAtText: updatedAt };
  }
  if (dir === "flat") {
    return { state: "flat", marketLabel: mkt, updatedAtText: updatedAt };
  }
  if (dir === "stale") {
    return { state: "stale", marketLabel: mkt, updatedAtText: updatedAt };
  }

  return { state: "tracking", marketLabel: mkt };
}

/** -----------------------------
 * Page
 * ----------------------------- */
export const GamesPage = () => {
  const [dateFilter, setDateFilter] = useState<DateFilter>("today");
  const { data: gamesBySport, isLoading, error } = useSlate(dateFilter);

  const health = useSupabaseHealthCheck();

  const [decisionSlate, setDecisionSlate] = useState<DecisionSlateResponse | null>(null);
  const [picksLoading, setPicksLoading] = useState(false);
  const [picksError, setPicksError] = useState<string | null>(null);

  const [showWhyModal, setShowWhyModal] = useState(false);

  // Performance summary for "Running Results" section
  const [perfSummary, setPerfSummary] = useState<PerformanceSummaryResponse | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPerfLoading(true);
    fetchPerformanceSummary("live", "season")
      .then((data) => { if (!cancelled) setPerfSummary(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setPerfLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // CTA email state
  const [ctaEmail, setCtaEmail] = useState("");
  const [ctaSubmitted, setCtaSubmitted] = useState(false);

  // "How grading works" inline expand
  const [showGradingInfo, setShowGradingInfo] = useState(false);

  const [showWatchlist, setShowWatchlist] = useState(false);
  const [collapsedSports, setCollapsedSports] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const s of sports) init[s] = true;
    return init;
  });

  function toggleSport(sport: Sport) {
    setCollapsedSports((prev) => ({ ...prev, [sport]: !prev[sport] }));
  }

  // ✅ Scroll-to-game with auto-expand league (polish)
  function scrollToGame(gameId: string) {
    // Find which sport contains this game
    const foundSport = sports.find((s) => (gamesBySport?.[s] ?? []).some((g) => g.id === gameId));

    if (foundSport) {
      // If collapsed, expand it first so the element exists in DOM
      const isCollapsed = collapsedSports[foundSport] ?? true;
      if (isCollapsed) {
        setCollapsedSports((prev) => ({ ...prev, [foundSport]: false }));

        // Wait a beat for SportSection to render, then scroll
        setTimeout(() => {
          const el = document.getElementById(`game-${gameId}`);
          if (!el) return;
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 120);

        return;
      }
    }

    const el = document.getElementById(`game-${gameId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setPicksLoading(true);
      setPicksError(null);

      try {
        const decision = await getDecisionSlate(dateFilter);
        if (!cancelled) setDecisionSlate(decision);
      } catch (e: any) {
        console.error("Failed to load decision slate", e);
        if (!cancelled) setPicksError(e?.message ?? "Failed to load picks");
      } finally {
        if (!cancelled) setPicksLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [dateFilter]);

  const totalGames = gamesBySport ? Object.values(gamesBySport).reduce((sum, games) => sum + games.length, 0) : 0;

  const totalDecisionPicks = useMemo(() => {
    if (!decisionSlate) return 0;
    return (decisionSlate.top_pick ? 1 : 0) + decisionSlate.strong_leans.length + decisionSlate.watchlist.length;
  }, [decisionSlate]);

  return (
    <div className="container py-8">
      <div className="mb-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <h1 className="text-3xl font-bold text-foreground">Today's Games</h1>
              <span className="rounded-md border border-border bg-background/60 px-2 py-0.5 text-[11px] font-mono text-muted-foreground">NBA Model (currently)</span>
            </div>
            <p className="text-muted-foreground">What deserves attention and action — in one glance.</p>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-4 px-4 py-3 rounded-xl bg-card border border-border">
              <TrendingUp className="h-5 w-5 text-primary" />
              <div>
                <p className="text-2xl font-bold font-mono text-foreground">{isLoading ? "—" : totalGames}</p>
                <p className="text-xs text-muted-foreground">Games Available</p>
              </div>
            </div>

            <div className="flex items-center gap-4 px-4 py-3 rounded-xl bg-card border border-border">
              <TrendingUp className="h-5 w-5 text-primary" />
              <div>
                <p className="text-2xl font-bold font-mono text-foreground">
                  {picksLoading ? "—" : totalDecisionPicks}
                </p>
                <p className="text-xs text-muted-foreground">Picks Shown</p>
              </div>
            </div>
          </div>
        </div>

        <DateTabs selected={dateFilter} onChange={setDateFilter} />

        {/* What Matters panel */}
        <div className="mt-6 rounded-xl bg-card border border-border p-5">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground">What Matters</h2>
              <p className="text-sm text-muted-foreground">Top pick + strongest leans. Everything else is noise.</p>
              <p className="text-sm text-muted-foreground italic mt-1">If you only make one bet today, this is it.</p>
            </div>

            <button
              type="button"
              onClick={() => setShowWhyModal(true)}
              className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-4"
            >
              Why PickPulse?
            </button>
          </div>

          {"ok" in health && health.ok === false ? (
            <HealthBanner reason={health.reason} detail={health.detail} />
          ) : null}

          {picksLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Loading picks…</span>
            </div>
          ) : picksError ? (
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-4 w-4" />
              <span className="text-sm">{picksError}</span>
            </div>
          ) : !decisionSlate ? (
            <div className="text-sm text-muted-foreground">No data yet.</div>
          ) : (
            <div className="space-y-4">
              {/* Top Pick */}
              <div className="rounded-lg border border-border bg-background/40 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-foreground">Top Pick</div>
                    <div className="text-xs text-muted-foreground">
                      {decisionSlate.top_pick
                        ? `${decisionSlate.top_pick.league} • ${new Date(decisionSlate.top_pick.start_time).toLocaleString()}`
                        : "No play today"}
                    </div>
                  </div>

                  {decisionSlate.top_pick
                    ? (() => {
                        const topConf = capConfidence(decisionSlate.top_pick.confidence, "top");
                        return (
                          <div
                            className={[
                              "shrink-0 text-xs font-mono px-2 py-1 rounded-md border capitalize",
                              confidencePillClasses(confidenceLabel(topConf)),
                            ].join(" ")}
                            title="Confidence"
                          >
                            {confidenceLabel(topConf)}
                          </div>
                        );
                      })()
                    : null}
                </div>

                {decisionSlate.top_pick ? (
                  <>
                    {(() => {
                      const topConf = capConfidence(decisionSlate.top_pick!.confidence, "top");
                      const { homeAbbr, awayAbbr } = getPickAbbrs(decisionSlate.top_pick);

                      return (
                        <div className="mt-3 flex flex-wrap items-center gap-3">
                          {/* ✅ Option B: matchup logos */}
                          <MatchupLogos homeAbbr={homeAbbr} awayAbbr={awayAbbr} />

                          <div className="text-sm text-foreground flex flex-wrap items-center gap-2">
                            <span className="font-medium">{marketLabel(decisionSlate.top_pick!.market)}</span>
                            <span className="text-muted-foreground">—</span>

                            {/* ✅ Clickable: scroll to game */}
                            <button
                              type="button"
                              onClick={() => scrollToGame(decisionSlate.top_pick!.game_id)}
                              className="font-semibold underline underline-offset-4 hover:opacity-90"
                              title="Jump to this game"
                            >
                              {decisionSlate.top_pick!.side}
                            </button>

                            {/* ✅ De-emphasized % as a small secondary chip */}
                            <span className="inline-flex items-center rounded-md border border-border/60 bg-background/20 px-2 py-0.5 text-[11px] font-mono text-muted-foreground">
                              {Math.round(topConf * 100)}%
                            </span>
                          </div>
                        </div>
                      );
                    })()}

                    {(() => {
                      const lm = getTopPickLineMove(decisionSlate.top_pick as any);
                      return (
                        <LineMovementTicker
                          state={lm.state}
                          marketLabel={lm.marketLabel}
                          openText={lm.openText}
                          currentText={lm.currentText}
                          updatedAtText={lm.updatedAtText}
                        />
                      );
                    })()}

                    {decisionSlate.top_pick.why?.length ? (
                      <ul className="mt-3 space-y-1 text-xs text-muted-foreground list-disc pl-5">
                        {decisionSlate.top_pick.why.slice(0, 4).map((w, idx) => (
                          <li key={idx}>{w}</li>
                        ))}
                      </ul>
                    ) : null}
                  </>
                ) : (
                  <div className="mt-3 text-sm text-muted-foreground">
                    Nothing cleared the bar today — check back closer to tip-off as lines update.
                  </div>
                )}
              </div>

              {/* Strong Leans */}
              <div className="rounded-lg border border-border bg-background/40 p-4">
                <div className="text-sm font-semibold text-foreground mb-2">Strong Leans</div>

                {decisionSlate.strong_leans.length === 0 ? (
                  <div className="text-sm text-muted-foreground">No strong leans today.</div>
                ) : (
                  <div className="space-y-2">
                    {decisionSlate.strong_leans.slice(0, 3).map((p) => {
                      const conf = capConfidence(p.confidence, "strong");
                      const label = confidenceLabel(conf);
                      const { homeAbbr, awayAbbr } = getPickAbbrs(p);

                      return (
                        <div
                          key={`${p.game_id}-${p.market}-${p.side}`}
                          className="flex items-start justify-between gap-3"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-3">
                              {/* ✅ Option B: matchup logos */}
                              <MatchupLogos homeAbbr={homeAbbr} awayAbbr={awayAbbr} />

                              <div className="text-sm text-foreground">
                                <span className="font-medium">{p.league}</span>
                                <span className="text-muted-foreground"> • </span>

                                {/* ✅ Clickable: scroll to game */}
                                <button
                                  type="button"
                                  onClick={() => scrollToGame(p.game_id)}
                                  className="font-semibold underline underline-offset-4 hover:opacity-90"
                                  title="Jump to this game"
                                >
                                  {p.side}
                                </button>

                                <span className="text-muted-foreground"> • {marketLabel(p.market)}</span>
                              </div>
                            </div>

                            <div className="text-xs text-muted-foreground mt-1">{p.why?.[0] ?? ""}</div>
                          </div>

                          <div
                            className={[
                              "shrink-0 text-xs font-mono px-2 py-1 rounded-md border capitalize",
                              confidencePillClasses(label),
                            ].join(" ")}
                            title="Confidence"
                          >
                            {label}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Watchlist (collapsible) */}
              <div className="rounded-lg border border-border bg-background/40 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm font-semibold text-foreground">Watchlist</div>
                  <button
                    onClick={() => setShowWatchlist((v) => !v)}
                    className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
                    type="button"
                  >
                    {showWatchlist ? (
                      <>
                        <ChevronDown className="h-4 w-4" />
                        Hide
                      </>
                    ) : (
                      <>
                        <ChevronRight className="h-4 w-4" />
                        Show ({decisionSlate.watchlist.length})
                      </>
                    )}
                  </button>
                </div>

                {decisionSlate.watchlist.length === 0 ? (
                  <div className="text-sm text-muted-foreground">Nothing on the watchlist.</div>
                ) : showWatchlist ? (
                  <div className="space-y-2">
                    {decisionSlate.watchlist.map((p) => {
                      const conf = capConfidence(p.confidence, "watch");
                      return (
                        <div
                          key={`${p.game_id}-${p.market}-${p.side}`}
                          className="flex items-start justify-between gap-3"
                        >
                          <div className="min-w-0">
                            <div className="text-sm text-foreground">
                              <span className="font-medium">{p.league}</span>
                              <span className="text-muted-foreground"> • </span>

                              {/* ✅ Clickable: scroll to game */}
                              <button
                                type="button"
                                onClick={() => scrollToGame(p.game_id)}
                                className="font-semibold underline underline-offset-4 hover:opacity-90"
                                title="Jump to this game"
                              >
                                {p.side}
                              </button>

                              <span className="text-muted-foreground"> • {marketLabel(p.market)}</span>
                            </div>
                            <div className="text-xs text-muted-foreground">{p.why?.[0] ?? ""}</div>
                          </div>

                          {/* ✅ De-emphasized % chip */}
                          <span className="shrink-0 inline-flex items-center rounded-md border border-border/60 bg-background/20 px-2 py-0.5 text-[11px] font-mono text-muted-foreground">
                            {Math.round(conf * 100)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">Hidden to reduce noise.</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Running Performance Results */}
      {(() => {
        const perfReady = perfSummary?.ok;
        const gradedPicks = perfReady ? perfSummary!.overall.picks : 0;

        return (
          <div className="mb-8 rounded-xl bg-card border border-border p-5">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <Trophy className="h-5 w-5 text-primary" />
                <h2 className="text-lg font-semibold text-foreground">Running Results <span className="text-sm font-normal text-muted-foreground">(NBA — currently)</span></h2>
              </div>
              <Link
                to="/performance"
                className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 underline underline-offset-4"
              >
                Full breakdown <ArrowRight className="h-3 w-3" />
              </Link>
            </div>

            <p className="text-[11px] text-muted-foreground mb-4 font-mono">
              Updated: {new Date().toLocaleString()}
            </p>

            {perfLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Loading results…</span>
              </div>
            ) : gradedPicks === 0 ? (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  Today's picks are live. Results update after games finish and picks are graded.
                </p>
                <p className="text-sm text-muted-foreground">
                  Results and grading will resume when NBA games return.
                </p>
                <p className="text-xs text-muted-foreground font-mono">
                  Graded picks: 0
                </p>
                <button
                  type="button"
                  onClick={() => setShowGradingInfo((v) => !v)}
                  className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-4"
                >
                  {showGradingInfo ? "Hide" : "What counts as a graded pick?"}
                </button>
                {showGradingInfo && (
                  <div className="mt-2 rounded-lg border border-border bg-background/40 p-3 text-xs text-muted-foreground space-y-1.5">
                    <p>A pick is graded once the game's final score is recorded and the win/loss outcome is determined.</p>
                    <p>Pushes (exact spread ties) and voided lines are excluded from the win/loss record.</p>
                    <p>Only top picks and strong leans are tracked — watchlist items don't count toward the record.</p>
                  </div>
                )}
              </div>
            ) : (
              <>
                {/* Overall stats row */}
                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="rounded-lg border border-border bg-background/40 p-3 text-center">
                    <p className="text-2xl font-bold font-mono text-foreground">
                      {perfSummary!.overall.percentage}%
                    </p>
                    <p className="text-xs text-muted-foreground">Win Rate</p>
                  </div>
                  <div className="rounded-lg border border-border bg-background/40 p-3 text-center">
                    <p className="text-2xl font-bold font-mono text-foreground">
                      {perfSummary!.overall.wins}-{perfSummary!.overall.losses}
                    </p>
                    <p className="text-xs text-muted-foreground">Record</p>
                  </div>
                  <div className="rounded-lg border border-border bg-background/40 p-3 text-center">
                    <p className="text-2xl font-bold font-mono text-foreground">
                      {perfSummary!.overall.picks}
                    </p>
                    <p className="text-xs text-muted-foreground">Total Picks</p>
                  </div>
                </div>

                {/* Per-sport chips */}
                <div className="flex flex-wrap gap-2">
                  {perfSummary!.sports
                    .filter((s) => s.totalPicks > 0)
                    .map((s) => (
                      <div
                        key={s.sport}
                        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background/30 px-2.5 py-1 text-xs font-mono"
                      >
                        <span className="font-semibold text-foreground">{s.sport.toUpperCase()}</span>
                        <span className="text-muted-foreground">
                          {s.overall.wins}-{s.overall.losses}
                        </span>
                        <span className={s.overall.percentage >= 55 ? "text-emerald-600" : s.overall.percentage >= 50 ? "text-amber-600" : "text-muted-foreground"}>
                          {s.overall.percentage}%
                        </span>
                      </div>
                    ))}
                </div>
              </>
            )}
          </div>
        );
      })()}

      {/* CTA: Get picks early */}
      {!ctaSubmitted ? (
        <div className="mb-8 rounded-xl border border-primary/20 bg-primary/5 p-5">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Get picks before tip-off</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Join the early access list — daily picks delivered to your inbox before games start.
              </p>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (ctaEmail.trim()) setCtaSubmitted(true);
              }}
              className="flex items-center gap-2 w-full md:w-auto"
            >
              <div className="relative flex-1 md:w-64">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  type="email"
                  required
                  value={ctaEmail}
                  onChange={(e) => setCtaEmail(e.target.value)}
                  placeholder="you@email.com"
                  className="w-full rounded-lg border border-border bg-background pl-9 pr-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              <button
                type="submit"
                className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                Join Early Access
              </button>
            </form>
          </div>
          <p className="text-xs text-muted-foreground mt-3">No spam. Unsubscribe anytime.</p>
          <p className="text-xs text-muted-foreground mt-1">Emails currently go directly to nathan@pickpulse.co.</p>
        </div>
      ) : (
        <div className="mb-8 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-5 text-center">
          <p className="text-sm font-medium text-emerald-600">You're on the list. We'll be in touch before tip-off.</p>
        </div>
      )}

      {/* Game slate below (collapsible by league) */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
          <p className="text-muted-foreground">Loading games...</p>
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center py-16">
          <AlertCircle className="h-12 w-12 text-destructive mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-2">Failed to load games</h3>
          <p className="text-muted-foreground text-center max-w-md">
            We couldn't fetch the latest game data. Please try again later.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {sports.map((sport) => {
            const games = gamesBySport?.[sport] ?? [];
            const isCollapsed = collapsedSports[sport] ?? true;

            return (
              <div key={sport} className="rounded-xl border border-border bg-card overflow-hidden">
                <button
                  onClick={() => toggleSport(sport)}
                  className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-foreground"
                  type="button"
                >
                  <div className="flex items-center gap-2">
                    {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    <span>{leagueLabel(sport)}</span>
                    <span className="text-xs text-muted-foreground font-normal">({games.length})</span>
                  </div>
                  <span className="text-xs text-muted-foreground">{isCollapsed ? "Show" : "Hide"}</span>
                </button>

                {!isCollapsed && (
                  <div className="border-t border-border">
                    <SportSection sport={sport} games={games} />
                  </div>
                )}
              </div>
            );
          })}

          {totalGames === 0 && (
            <div className="text-center py-16">
              <Calendar className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-foreground mb-2">No games scheduled</h3>
              <p className="text-muted-foreground">Check back later for updated game listings.</p>
            </div>
          )}
        </div>
      )}

      <WhyPickPulseModal open={showWhyModal} onOpenChange={setShowWhyModal} />
    </div>
  );
};

export default GamesPage;

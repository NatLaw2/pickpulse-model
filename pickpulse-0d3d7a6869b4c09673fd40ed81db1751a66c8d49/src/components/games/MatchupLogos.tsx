// src/components/games/MatchupLogos.tsx
import { useState } from "react";
import { nbaLogoUrl, safeAbbr } from "@/lib/teamLogos";

type Props = {
  homeAbbr: string;
  awayAbbr: string;
  className?: string;
};

export default function MatchupLogos({ homeAbbr, awayAbbr, className }: Props) {
  const [homeOk, setHomeOk] = useState(true);
  const [awayOk, setAwayOk] = useState(true);

  const h = safeAbbr(homeAbbr);
  const a = safeAbbr(awayAbbr);

  // If we don't have abbreviations, don't render anything
  if (!h || !a) return null;

  return (
    <div className={["flex items-center gap-2", className].filter(Boolean).join(" ")}>
      {homeOk ? (
        <img
          src={nbaLogoUrl(h)}
          alt={`${h} logo`}
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
          src={nbaLogoUrl(a)}
          alt={`${a} logo`}
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

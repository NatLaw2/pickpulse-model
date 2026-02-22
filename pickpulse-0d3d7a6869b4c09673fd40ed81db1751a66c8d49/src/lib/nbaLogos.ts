// src/lib/nbaLogos.ts

/**
 * NBA team name → ESPN CDN alias mapping.
 * ESPN uses lowercase abbreviations: lal, bos, gsw, etc.
 */
const TEAM_ALIAS_MAP: Record<string, string> = {
  // Full names
  "Atlanta Hawks": "atl",
  "Boston Celtics": "bos",
  "Brooklyn Nets": "bkn",
  "Charlotte Hornets": "cha",
  "Chicago Bulls": "chi",
  "Cleveland Cavaliers": "cle",
  "Dallas Mavericks": "dal",
  "Denver Nuggets": "den",
  "Detroit Pistons": "det",
  "Golden State Warriors": "gs",
  "Houston Rockets": "hou",
  "Indiana Pacers": "ind",
  "Los Angeles Clippers": "lac",
  "LA Clippers": "lac",
  "Los Angeles Lakers": "lal",
  "LA Lakers": "lal",
  "Memphis Grizzlies": "mem",
  "Miami Heat": "mia",
  "Milwaukee Bucks": "mil",
  "Minnesota Timberwolves": "min",
  "New Orleans Pelicans": "no",
  "New York Knicks": "ny",
  "Oklahoma City Thunder": "okc",
  "Orlando Magic": "orl",
  "Philadelphia 76ers": "phi",
  "Phoenix Suns": "phx",
  "Portland Trail Blazers": "por",
  "Sacramento Kings": "sac",
  "San Antonio Spurs": "sa",
  "Toronto Raptors": "tor",
  "Utah Jazz": "uta",
  "Washington Wizards": "wsh",

  // Abbreviations
  ATL: "atl",
  BOS: "bos",
  BKN: "bkn",
  CHA: "cha",
  CHI: "chi",
  CLE: "cle",
  DAL: "dal",
  DEN: "den",
  DET: "det",
  GSW: "gs",
  GS: "gs",
  HOU: "hou",
  IND: "ind",
  LAC: "lac",
  LAL: "lal",
  MEM: "mem",
  MIA: "mia",
  MIL: "mil",
  MIN: "min",
  NOP: "no",
  NO: "no",
  NYK: "ny",
  NY: "ny",
  OKC: "okc",
  ORL: "orl",
  PHI: "phi",
  PHX: "phx",
  POR: "por",
  SAC: "sac",
  SAS: "sa",
  SA: "sa",
  TOR: "tor",
  UTA: "uta",
  WAS: "wsh",
  WSH: "wsh",
};

/**
 * Returns the ESPN CDN logo URL for a given NBA team name or abbreviation.
 * Falls back to a generic basketball icon if the team is unknown.
 */
export function getNbaLogo(teamName: string): string {
  const key = (teamName || "").trim();
  const alias = TEAM_ALIAS_MAP[key] ?? TEAM_ALIAS_MAP[key.toUpperCase()];
  if (alias) {
    return `https://a.espncdn.com/i/teamlogos/nba/500/${alias}.png`;
  }
  // Fallback: try using the raw input as alias (lowercase)
  return `https://a.espncdn.com/i/teamlogos/nba/500/${key.toLowerCase()}.png`;
}

export { TEAM_ALIAS_MAP };

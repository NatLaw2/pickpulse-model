// src/lib/teamLogos.ts

// ESPN uses NBA abbreviations like "ind", "lal", "lac", etc.
export function nbaLogoUrl(abbr: string) {
  const a = (abbr || "").trim().toLowerCase();
  return `https://a.espncdn.com/i/teamlogos/nba/500/${a}.png`;
}

/**
 * Some feeds give "LA Clippers" vs "Los Angeles Clippers" or similar.
 * This keeps it simple: you pass in abbreviations from your UI model (IND, CHA, etc).
 */
export function safeAbbr(abbr: string) {
  return (abbr || "").trim().toUpperCase();
}

# app/data/bref_fetch.py
from __future__ import annotations

import os
import time
import re
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd


BREF_SCHEDULE_URL = "https://www.basketball-reference.com/leagues/NBA_{season}_games.html"
BREF_MONTH_URL = "https://www.basketball-reference.com/leagues/NBA_{season}_games-{month}.html"

# NBA season months (October through June covers regular season + playoffs)
_SEASON_MONTHS = [
    "october", "november", "december", "january",
    "february", "march", "april", "may", "june",
]


@dataclass
class GameRow:
    date: str
    home_team: str
    away_team: str
    home_pts: int
    away_pts: int
    season: int
    # Optional market fields from BRef schedule tables (when present)
    line: Optional[float] = None   # closing spread from home perspective (negative = home favored)
    ou: Optional[float] = None     # closing total points (over/under)


def _sleep_polite():
    # Be polite to Basketball-Reference
    time.sleep(1.2)


_FLOAT_RE = re.compile(r"[-+]?\d+(\.\d+)?")


def _parse_float_maybe(x) -> Optional[float]:
    """
    BRef can show Line/OU as strings like:
      "-5.5"
      "PK"
      "Pick"
      ""
      None
    We'll try to pull the first float. If no float, return None.
    """
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return None
    if s.upper() in {"PK", "PICK", "PICK'EM", "PICKEM"}:
        return 0.0
    m = _FLOAT_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _find_month_links(season: int) -> List[str]:
    """Discover available month pages from the BRef season landing page."""
    import re as _re
    import requests as _req
    resp = _req.get(BREF_SCHEDULE_URL.format(season=season), timeout=15)
    pattern = rf'/leagues/NBA_{season}_games-(\w+)\.html'
    months = _re.findall(pattern, resp.text)
    return months if months else _SEASON_MONTHS


def _read_schedule_table(url: str) -> List[pd.DataFrame]:
    """Read schedule tables from a single BRef page."""
    try:
        tables = pd.read_html(url)
    except Exception:
        return []
    dfs = []
    for t in tables:
        cols = [c.lower() for c in t.columns.astype(str).tolist()]
        has_core = (
            "date" in cols
            and ("visitor/neutral" in cols or "visitor" in cols)
            and ("home/neutral" in cols or "home" in cols)
        )
        if has_core:
            dfs.append(t.copy())
    return dfs


def fetch_season_games(season: int) -> pd.DataFrame:
    """
    Fetch NBA games for a given season year from Basketball-Reference.

    Iterates through each monthly page to get the full season.
    Example: season=2025 corresponds to the 2024-25 season.
    """
    months = _find_month_links(season)
    print(f"[bref] season {season}: found {len(months)} month pages: {months}")

    dfs = []
    for month in months:
        url = BREF_MONTH_URL.format(season=season, month=month)
        month_dfs = _read_schedule_table(url)
        for d in month_dfs:
            dfs.append(d)
        _sleep_polite()

    if not dfs:
        # Fallback: try the landing page directly
        url = BREF_SCHEDULE_URL.format(season=season)
        dfs = _read_schedule_table(url)

    if not dfs:
        raise RuntimeError(f"No schedule tables found for season {season}")

    df = pd.concat(dfs, ignore_index=True)

    # Normalize column names
    col_map = {}
    for c in df.columns:
        cl = str(c).lower()
        if cl == "visitor/neutral":
            col_map[c] = "away_team"
        elif cl == "home/neutral":
            col_map[c] = "home_team"
        elif cl == "date":
            col_map[c] = "date"
        elif cl == "line":
            col_map[c] = "line_raw"
        elif cl in {"ou", "o/u"}:
            col_map[c] = "ou_raw"

    df = df.rename(columns=col_map)

    # Handle points columns robustly:
    # Typically: 'PTS' is away, 'PTS.1' is home.
    away_pts_col = None
    home_pts_col = None
    for c in df.columns:
        if str(c).lower() == "pts":
            away_pts_col = c
        if str(c).lower() in ("pts.1", "pts_1"):
            home_pts_col = c

    if away_pts_col is None or home_pts_col is None:
        pts_like = [c for c in df.columns if str(c).lower().startswith("pts")]
        if len(pts_like) >= 2:
            away_pts_col, home_pts_col = pts_like[0], pts_like[1]
        else:
            raise RuntimeError("Could not identify points columns from Basketball-Reference tables.")

    df = df.rename(columns={away_pts_col: "away_pts", home_pts_col: "home_pts"})

    # Remove header rows that repeat inside tables (sometimes 'Date' appears as a row)
    df = df[df["date"].astype(str).str.lower() != "date"].copy()

    # Keep only completed games (pts are present)
    df["away_pts"] = pd.to_numeric(df["away_pts"], errors="coerce")
    df["home_pts"] = pd.to_numeric(df["home_pts"], errors="coerce")
    df = df.dropna(subset=["away_pts", "home_pts"]).copy()

    df["away_pts"] = df["away_pts"].astype(int)
    df["home_pts"] = df["home_pts"].astype(int)
    df["season"] = season

    # Parse optional market fields, if present
    if "line_raw" in df.columns:
        df["line"] = df["line_raw"].apply(_parse_float_maybe)
    else:
        df["line"] = None

    if "ou_raw" in df.columns:
        df["ou"] = df["ou_raw"].apply(_parse_float_maybe)
    else:
        df["ou"] = None

    # Ensure date is parseable
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date.astype(str)
    df = df.dropna(subset=["date", "away_team", "home_team"]).copy()

    # Keep only the fields we need
    keep = ["date", "away_team", "home_team", "away_pts", "home_pts", "season", "line", "ou"]
    return df[keep].reset_index(drop=True)


def build_dataset(seasons: List[int], out_csv: str = "nba_games.csv") -> pd.DataFrame:
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)

    all_df = []
    for s in seasons:
        print(f"[bref] fetching season={s} ...")
        df = fetch_season_games(s)
        print(f"[bref] season={s} rows={len(df)} (line%={df['line'].notna().mean():.1%} ou%={df['ou'].notna().mean():.1%})")
        all_df.append(df)
        _sleep_polite()

    data = pd.concat(all_df, ignore_index=True)

    # Sort chronologically (date first, then season)
    data["date_dt"] = pd.to_datetime(data["date"])
    data = data.sort_values(["date_dt", "season"]).drop(columns=["date_dt"]).reset_index(drop=True)

    data.to_csv(out_csv, index=False)
    print(f"[bref] wrote {len(data)} rows -> {out_csv}")
    return data


if __name__ == "__main__":
    # Example: 2020..2025 = 2019-20 through 2024-25
    seasons = [2020, 2021, 2022, 2023, 2024, 2025]
    build_dataset(seasons, out_csv="data/nba_games.csv")

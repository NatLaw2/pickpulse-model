"""NBA schedule-derived structural features.

Computes per-game features from a schedule DataFrame:
  - rest_days: days since team's last game
  - back_to_back, three_in_four, four_in_six: fatigue flags
  - games_last_7: games played in trailing 7 days
  - travel_miles: haversine miles from previous game venue to current
  - tz_shift_hours: timezone delta from previous game venue

Requires a DataFrame with columns: date, home_team, away_team
(and optionally home_pts, away_pts for result-aware features).

Usage:
    from app.features.nba_schedule_features import add_schedule_features
    df = add_schedule_features(df)
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Team geo data
# ---------------------------------------------------------------------------

_GEO_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_TZ_OFFSETS: Dict[str, float] = {
    "America/New_York": -5,
    "America/Toronto": -5,
    "America/Detroit": -5,
    "America/Indiana/Indianapolis": -5,
    "America/Chicago": -6,
    "America/Denver": -7,
    "America/Phoenix": -7,
    "America/Los_Angeles": -8,
}


def _load_geo() -> Dict[str, Dict[str, Any]]:
    global _GEO_CACHE
    if _GEO_CACHE is not None:
        return _GEO_CACHE
    geo_path = os.path.join(os.path.dirname(__file__), "nba_team_geo.json")
    try:
        with open(geo_path) as f:
            _GEO_CACHE = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _GEO_CACHE = {}
    return _GEO_CACHE


def _team_coords(team: str) -> Optional[Tuple[float, float]]:
    geo = _load_geo()
    info = geo.get(team)
    if info and "lat" in info and "lon" in info:
        return (info["lat"], info["lon"])
    return None


def _team_tz_offset(team: str) -> Optional[float]:
    geo = _load_geo()
    info = geo.get(team)
    if info and "tz" in info:
        return _TZ_OFFSETS.get(info["tz"])
    return None


def _game_city_coords(team: str, is_home: bool) -> Optional[Tuple[float, float]]:
    """Get coordinates of the city where team is playing.

    If home, use own city. If away, the opponent's city determines the venue,
    but we don't know it here - we always track where the team WAS (previous game venue).
    """
    return _team_coords(team)


def _game_tz(team: str) -> Optional[float]:
    return _team_tz_offset(team)


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in miles between two points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Build per-team game history
# ---------------------------------------------------------------------------

def _build_team_history(df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    """Build sorted game history per team.

    Each entry: {date, opponent, is_home, venue_team (team whose city hosts)}.
    """
    history: Dict[str, List[Dict[str, Any]]] = {}

    for _, row in df.iterrows():
        d = row["date"]
        home = row["home_team"]
        away = row["away_team"]

        # Home team plays at home city
        history.setdefault(home, []).append({
            "date": d,
            "opponent": away,
            "is_home": True,
            "venue_team": home,
        })
        # Away team travels to home team's city
        history.setdefault(away, []).append({
            "date": d,
            "opponent": home,
            "is_home": False,
            "venue_team": home,
        })

    # Sort each team's history by date
    for team in history:
        history[team].sort(key=lambda g: g["date"])

    return history


def _compute_team_features(
    team: str,
    game_date: str,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute schedule features for one team on a given date.

    Uses games strictly BEFORE game_date.
    """
    try:
        gd = datetime.strptime(game_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return _default_features()

    # Filter to games before this date
    prior = [g for g in history if g["date"] < game_date]

    if not prior:
        return _default_features()

    last = prior[-1]
    try:
        last_date = datetime.strptime(last["date"], "%Y-%m-%d")
    except (ValueError, TypeError):
        return _default_features()

    rest_days = (gd - last_date).days

    # Back-to-back, 3-in-4, 4-in-6
    b2b = 1 if rest_days <= 1 else 0

    cutoff_4 = (gd - timedelta(days=3)).strftime("%Y-%m-%d")
    games_in_4 = sum(1 for g in prior if g["date"] >= cutoff_4)
    three_in_four = 1 if games_in_4 >= 2 else 0  # this game would be 3rd

    cutoff_6 = (gd - timedelta(days=5)).strftime("%Y-%m-%d")
    games_in_6 = sum(1 for g in prior if g["date"] >= cutoff_6)
    four_in_six = 1 if games_in_6 >= 3 else 0

    # Games in last 7 days
    cutoff_7 = (gd - timedelta(days=7)).strftime("%Y-%m-%d")
    games_last_7 = sum(1 for g in prior if g["date"] >= cutoff_7)

    # Travel: distance from previous game venue to current game venue
    # Previous venue = last["venue_team"]'s city
    prev_venue = last.get("venue_team", "")
    prev_coords = _team_coords(prev_venue)

    travel_miles = 0.0
    if prev_coords:
        # Current venue: we'll set this when we know if this team is home/away
        # For now, store prev_coords for later
        pass  # handled in add_schedule_features

    # Timezone shift from previous venue
    prev_tz = _team_tz_offset(prev_venue) if prev_venue else None

    return {
        "rest_days": rest_days,
        "back_to_back": b2b,
        "three_in_four": three_in_four,
        "four_in_six": four_in_six,
        "games_last_7": games_last_7,
        "_prev_venue_team": prev_venue,
        "_prev_tz": prev_tz,
    }


def _default_features() -> Dict[str, Any]:
    return {
        "rest_days": 3,
        "back_to_back": 0,
        "three_in_four": 0,
        "four_in_six": 0,
        "games_last_7": 2,
        "_prev_venue_team": "",
        "_prev_tz": None,
    }


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def add_schedule_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add schedule/rest/travel/timezone features to a games DataFrame.

    Input must have columns: date, home_team, away_team.
    Adds columns with home_ and away_ prefixes.

    Safe: defaults to 0 on any error, never raises.
    """
    if df.empty:
        return df

    work = df.copy()

    # Ensure date column is string for consistent comparison
    if "date" not in work.columns:
        return work
    work["date"] = work["date"].astype(str)

    # Build per-team history
    history = _build_team_history(work)

    # Feature columns to add
    feat_cols = [
        "rest_days", "back_to_back", "three_in_four", "four_in_six",
        "games_last_7", "travel_miles", "tz_shift_hours",
    ]

    # Initialize columns
    for side in ["home", "away"]:
        for col in feat_cols:
            work[f"{side}_{col}"] = 0.0

    # Derived columns
    work["rest_diff"] = 0.0

    for idx, row in work.iterrows():
        try:
            home = row["home_team"]
            away = row["away_team"]
            game_date = row["date"]

            # Home team features
            h_feats = _compute_team_features(home, game_date, history.get(home, []))
            a_feats = _compute_team_features(away, game_date, history.get(away, []))

            for col in ["rest_days", "back_to_back", "three_in_four", "four_in_six", "games_last_7"]:
                work.at[idx, f"home_{col}"] = h_feats.get(col, 0)
                work.at[idx, f"away_{col}"] = a_feats.get(col, 0)

            # Travel: from previous venue to THIS game's venue (home team's city)
            venue_coords = _team_coords(home)

            for side, feats, prefix in [(home, h_feats, "home"), (away, a_feats, "away")]:
                prev_venue = feats.get("_prev_venue_team", "")
                prev_coords = _team_coords(prev_venue) if prev_venue else None
                if prev_coords and venue_coords:
                    miles = haversine_miles(prev_coords[0], prev_coords[1], venue_coords[0], venue_coords[1])
                    work.at[idx, f"{prefix}_travel_miles"] = round(miles, 1)

                prev_tz = feats.get("_prev_tz")
                curr_tz = _team_tz_offset(home)  # venue is home team's city
                if prev_tz is not None and curr_tz is not None:
                    work.at[idx, f"{prefix}_tz_shift_hours"] = abs(curr_tz - prev_tz)

            # Rest differential (home advantage in rest)
            work.at[idx, "rest_diff"] = h_feats.get("rest_days", 0) - a_feats.get("rest_days", 0)

        except Exception:
            # Safety: never crash, defaults are already 0
            continue

    return work


# ---------------------------------------------------------------------------
# Convenience: get feature column names
# ---------------------------------------------------------------------------

SCHEDULE_FEATURE_COLS = [
    "home_rest_days",
    "away_rest_days",
    "rest_diff",
    "home_back_to_back",
    "away_back_to_back",
    "home_games_last_7",
    "away_games_last_7",
    "home_travel_miles",
    "away_travel_miles",
    "home_tz_shift_hours",
    "away_tz_shift_hours",
]

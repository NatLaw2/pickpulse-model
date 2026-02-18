"""Build training DataFrame from Supabase production tables.

Features (NBA moneyline):
  - locked_home_nv:   no-vig implied prob for home at lock time
  - locked_away_nv:   no-vig implied prob for away at lock time
  - closing_home_nv:  no-vig implied prob for home at close
  - closing_away_nv:  no-vig implied prob for away at close
  - spread_home_point: locked spread (if available)
  - is_home:          1 if selection is home team, 0 otherwise
  - edge_vs_market:   model prob - market no-vig prob (selected side)

Label:
  - won: 1 if pick result == 'win', 0 if 'loss'
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..agents._supabase import (
    fetch_locked_picks,
    fetch_pick_results,
    fetch_closing_lines,
    since_date,
)
from ..agents._math import implied_prob, normalize_no_vig, safe_float


def _nv(odds_home: Any, odds_away: Any) -> Tuple[Optional[float], Optional[float]]:
    """Convert American odds pair to no-vig probabilities."""
    h = safe_float(odds_home)
    a = safe_float(odds_away)
    if h is None or a is None:
        return None, None
    ph = implied_prob(h)
    pa = implied_prob(a)
    if not math.isfinite(ph) or not math.isfinite(pa):
        return None, None
    return normalize_no_vig(ph, pa)


def _resolve_side(pick: Dict[str, Any]) -> Optional[str]:
    """Return 'home' or 'away' for this pick."""
    sel = (pick.get("selection_team") or pick.get("side") or "").strip().lower()
    home = (pick.get("home_team") or "").strip().lower()
    away = (pick.get("away_team") or "").strip().lower()
    if not sel:
        return None
    if home and (home in sel or sel in home):
        return "home"
    if away and (away in sel or sel in away):
        return "away"
    return None


def _extract_closing_nv(
    event_id: str,
    home_team: str,
    away_team: str,
    game_start: Optional[str],
    closing: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Optional[float], Optional[float]]:
    """Get closing no-vig probs from closing_lines (latest snapshot <= game_start)."""
    lines = closing.get(event_id, [])
    if not lines:
        return None, None

    # Filter to h2h rows with captured_at <= game_start
    eligible = []
    for cl in lines:
        if cl.get("market") != "h2h":
            continue
        cap = cl.get("captured_at")
        if game_start and cap and cap <= game_start:
            eligible.append(cl)
        elif not game_start:
            eligible.append(cl)

    if not eligible:
        return None, None

    # Latest snapshot
    eligible.sort(key=lambda r: r.get("captured_at", ""), reverse=True)
    latest_ts = eligible[0].get("captured_at", "")
    snap = [r for r in eligible if r.get("captured_at") == latest_ts]

    home_lower = home_team.strip().lower()
    away_lower = away_team.strip().lower()
    ml_home = None
    ml_away = None
    for r in snap:
        name = (r.get("outcome_name") or "").strip().lower()
        if name == home_lower:
            ml_home = r.get("price")
        elif name == away_lower:
            ml_away = r.get("price")

    return _nv(ml_home, ml_away)


def build_dataset(days: int = 365) -> pd.DataFrame:
    """Build training DataFrame from Supabase production tables.

    Returns DataFrame with columns:
      event_id, run_date, home_team, away_team, selection_team,
      locked_home_nv, locked_away_nv, closing_home_nv, closing_away_nv,
      spread_home_point, is_home, confidence, score, won
    """
    since = since_date(days)
    print(f"[dataset] Fetching data since {since}...")

    results = fetch_pick_results(since)
    print(f"[dataset] Pick results: {len(results)}")

    locked = fetch_locked_picks(since)
    print(f"[dataset] Locked picks: {len(locked)}")

    closing = fetch_closing_lines()
    print(f"[dataset] Closing line events: {len(closing)}")

    # Index locked picks by event_id for enrichment
    locked_by_eid: Dict[str, Dict[str, Any]] = {}
    for lp in locked:
        locked_by_eid[str(lp.get("event_id", ""))] = lp

    rows = []
    for r in results:
        # NBA moneyline only
        if r.get("market") != "moneyline":
            continue
        if r.get("result") not in ("win", "loss"):
            continue

        eid = str(r.get("event_id", ""))
        lp = locked_by_eid.get(eid)
        if not lp:
            continue

        side = _resolve_side(lp)
        if side is None:
            continue

        # Locked odds -> no-vig
        lh_nv, la_nv = _nv(lp.get("locked_ml_home"), lp.get("locked_ml_away"))
        if lh_nv is None:
            continue

        # Closing odds -> no-vig (from closing_lines snapshots)
        home_team = lp.get("home_team", "")
        away_team = lp.get("away_team", "")
        game_start = lp.get("game_start_time")
        ch_nv, ca_nv = _extract_closing_nv(eid, home_team, away_team, game_start, closing)

        # Spread
        sp = safe_float(lp.get("locked_spread_home_point"))

        # Confidence and score from locked pick
        conf = safe_float(lp.get("confidence"))
        score = safe_float(lp.get("score"))

        won = 1 if r["result"] == "win" else 0
        is_home = 1 if side == "home" else 0

        rows.append({
            "event_id": eid,
            "run_date": r.get("run_date"),
            "home_team": home_team,
            "away_team": away_team,
            "selection_team": lp.get("selection_team"),
            "locked_home_nv": lh_nv,
            "locked_away_nv": la_nv,
            "closing_home_nv": ch_nv,
            "closing_away_nv": ca_nv,
            "spread_home_point": sp,
            "is_home": is_home,
            "confidence": conf,
            "score": score,
            "won": won,
        })

    df = pd.DataFrame(rows)
    print(f"[dataset] Built {len(df)} rows")
    return df


# Feature columns used by the model
FEATURE_COLS = [
    "locked_home_nv",
    "locked_away_nv",
    "spread_home_point",
    "is_home",
]

# Optional features (may have nulls)
OPTIONAL_FEATURES = [
    "closing_home_nv",
    "closing_away_nv",
]

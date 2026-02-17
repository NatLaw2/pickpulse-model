#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


# -------------------------
# ENV
# -------------------------
def env(name: str, default: Optional[str] = None) -> str:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        if default is not None:
            return default
        raise RuntimeError(f"Missing env var: {name}")
    return v.strip()


SUPABASE_URL = env("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = env("SUPABASE_SERVICE_ROLE_KEY")

MODEL_API_URL = env("MODEL_API_URL", "https://pickpulse-model.onrender.com").rstrip("/")
MODEL_API_KEY = env("MODEL_API_KEY")  # required since you want Render model only
MODEL_VERSION = env("MODEL_VERSION", "render_nba_ml_v1")


# -------------------------
# Supabase REST helpers
# -------------------------
def sb_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "application/json",
    }


def sb_get(path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    url = f"{SUPABASE_URL.rstrip('/')}{path}"
    r = requests.get(url, headers=sb_headers(), params=params, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Supabase GET failed {r.status_code}: {r.text}")
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Supabase GET unexpected response: {r.text}")
    return data


def sb_insert(path: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    url = f"{SUPABASE_URL.rstrip('/')}{path}"
    r = requests.post(
        url,
        headers={**sb_headers(), "Prefer": "return=representation"},
        data=json.dumps(rows),
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"Supabase INSERT failed {r.status_code}: {r.text}")
    data = r.json()
    return data if isinstance(data, list) else []


def sb_patch(path: str, match_params: Dict[str, str], patch: Dict[str, Any]) -> None:
    url = f"{SUPABASE_URL.rstrip('/')}{path}"
    r = requests.patch(
        url,
        headers=sb_headers(),
        params=match_params,
        data=json.dumps(patch),
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"Supabase PATCH failed {r.status_code}: {r.text}")


# -------------------------
# Model call (Render)
# -------------------------
def call_model_recommendations(games: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calls Render model: POST /v1/nba/recommendations
    Expects: {"byGameId": {event_id: {moneyline:{...}, spread:{...}, total:{...}}}}
    """
    url = f"{MODEL_API_URL}/v1/nba/recommendations"
    r = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "x-model-key": MODEL_API_KEY,
            "Authorization": f"Bearer {MODEL_API_KEY}",
        },
        data=json.dumps(games),
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"Model API failed {r.status_code}: {r.text}")
    return r.json()


# -------------------------
# Betting math
# -------------------------
def american_profit_per_1u(odds: int) -> float:
    """
    Profit (not including stake) for a 1 unit stake at given American odds.
    -110 => profit 0.909...
    +150 => profit 1.5
    """
    if odds == 0:
        return 0.0
    if odds < 0:
        return 100.0 / abs(odds)
    return odds / 100.0


def safe_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(float(x))
    except Exception:
        return None


def normalize(s: str) -> str:
    return (s or "").strip().lower()


def pick_side_from_selection(selection: str, home_team: str, away_team: str) -> Optional[str]:
    """
    Your Render model selection strings look like:
      "BOS ML" or "Boston Celtics ML" (depends on abbreviation availability)
    We map to "home"/"away" by checking presence of team tokens.
    """
    sel = normalize(selection)

    home = normalize(home_team)
    away = normalize(away_team)

    # simple containment checks
    if home and home in sel:
        return "home"
    if away and away in sel:
        return "away"

    # if selection includes abbreviations, try last-word initials from team names
    def abbr(name: str) -> str:
        parts = [p for p in name.replace(".", "").split(" ") if p]
        return "".join([p[0] for p in parts])[:4].lower()

    ha = abbr(home_team)
    aa = abbr(away_team)
    if ha and ha in sel:
        return "home"
    if aa and aa in sel:
        return "away"

    return None


# -------------------------
# Fetch game_results
# -------------------------
GAME_RESULTS_SELECT = ",".join([
    "sport",
    "event_id",
    "commence_time",
    "home_team",
    "away_team",
    "closing_ml_home",
    "closing_ml_away",
    "home_score",
    "away_score",
])


def fetch_all_nba_results(limit: int = 50000) -> List[Dict[str, Any]]:
    """
    Pulls nba rows from public.game_results (paginated).
    """
    out: List[Dict[str, Any]] = []
    page_size = 1000
    page = 0

    while len(out) < limit:
        offset = page * page_size
        take = min(page_size, limit - len(out))

        params = {
            "select": GAME_RESULTS_SELECT,
            "sport": "eq.nba",
            "order": "commence_time.asc",
            "limit": str(take),
            "offset": str(offset),
        }
        batch = sb_get("/rest/v1/game_results", params=params)
        out.extend(batch)
        if len(batch) < take:
            break
        page += 1

    return out


# -------------------------
# Main backtest
# -------------------------
def build_game_payload(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    event_id = row.get("event_id")
    home_team = row.get("home_team")
    away_team = row.get("away_team")
    commence = row.get("commence_time")

    ml_home = safe_int(row.get("closing_ml_home"))
    ml_away = safe_int(row.get("closing_ml_away"))

    # must have scores + odds to grade ML
    if not event_id or not home_team or not away_team or not commence:
        return None
    if ml_home is None or ml_away is None:
        return None

    return {
        "id": str(event_id),
        "sport": "nba",
        "homeTeam": {"name": str(home_team), "abbreviation": None},
        "awayTeam": {"name": str(away_team), "abbreviation": None},
        "startTime": str(commence),
        "odds": {"moneyline": {"home": ml_home, "away": ml_away}, "spread": None, "total": None},
    }


def grade_moneyline(
    row: Dict[str, Any],
    reco: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Returns a model_backtest_bets row payload.
    """
    event_id = str(row["event_id"])
    home_team = str(row["home_team"])
    away_team = str(row["away_team"])

    ml_home = safe_int(row.get("closing_ml_home"))
    ml_away = safe_int(row.get("closing_ml_away"))

    home_score = row.get("home_score")
    away_score = row.get("away_score")

    # winner
    try:
        hs = float(home_score)
        as_ = float(away_score)
    except Exception:
        hs = math.nan
        as_ = math.nan

    # defaults
    model_status = reco.get("status", "no_bet")
    model_selection = reco.get("selection")
    model_conf = reco.get("confidence")
    model_score = reco.get("score")

    picked_side = None
    picked_odds = None
    outcome_status = "no_bet"
    units = 0.0

    if model_status == "pick" and isinstance(model_selection, str):
        picked_side = pick_side_from_selection(model_selection, home_team, away_team)
        if picked_side == "home":
            picked_odds = ml_home
        elif picked_side == "away":
            picked_odds = ml_away

        # grade if we can
        if picked_side in ("home", "away") and picked_odds is not None and math.isfinite(hs) and math.isfinite(as_):
            picked_won = (hs > as_) if picked_side == "home" else (as_ > hs)
            if picked_won:
                outcome_status = "win"
                units = float(american_profit_per_1u(int(picked_odds)))
            else:
                outcome_status = "loss"
                units = -1.0

    return {
        "sport": "nba",
        "market": "moneyline",
        "model_version": MODEL_VERSION,

        "event_id": event_id,
        "commence_time": row.get("commence_time"),

        "home_team": home_team,
        "away_team": away_team,

        "closing_odds_home": ml_home,
        "closing_odds_away": ml_away,

        "model_status": model_status,
        "model_selection": model_selection,
        "model_confidence": model_conf,
        "model_score": int(model_score) if isinstance(model_score, (int, float)) else None,

        "picked_side": picked_side,
        "picked_odds": picked_odds,

        "outcome_status": outcome_status,
        "units": units,
    }


def main():
    print("Loading NBA game_results from Supabase...")
    rows = fetch_all_nba_results(limit=50000)
    print(f"Rows fetched: {len(rows)}")

    # Filter to rows we can backtest (scores + closing ML)
    usable: List[Dict[str, Any]] = []
    for r in rows:
        if r.get("home_score") is None or r.get("away_score") is None:
            continue
        if safe_int(r.get("closing_ml_home")) is None or safe_int(r.get("closing_ml_away")) is None:
            continue
        if not r.get("event_id"):
            continue
        usable.append(r)

    print(f"Usable rows (scores + closing ML): {len(usable)}")
    if not usable:
        raise SystemExit("No usable rows found. Ensure game_results has scores + closing ML odds.")

    # Create run row
    run_row = {
        "sport": "nba",
        "market": "moneyline",
        "model_version": MODEL_VERSION,
        "n_games": len(usable),
        "notes": "Method 1: call Render model using closing moneyline odds from game_results.",
    }
    inserted = sb_insert("/rest/v1/model_backtest_runs", [run_row])
    if not inserted:
        raise SystemExit("Failed to create model_backtest_runs row.")
    run_id = inserted[0]["id"]
    print(f"Created backtest run: {run_id}")

    # Batch-call model
    batch_size = 200
    bet_rows: List[Dict[str, Any]] = []

    for i in range(0, len(usable), batch_size):
        batch = usable[i:i + batch_size]
        payload = [build_game_payload(r) for r in batch]
        payload = [p for p in payload if p is not None]
        if not payload:
            continue

        data = call_model_recommendations(payload)
        by_game = data.get("byGameId", {}) if isinstance(data, dict) else {}
        if not isinstance(by_game, dict):
            by_game = {}

        # grade each game
        for r in batch:
            gid = str(r["event_id"])
            recs = by_game.get(gid, {})
            ml = recs.get("moneyline", {"status": "no_bet", "reason": "missing_reco"})
            graded = grade_moneyline(r, ml)
            graded["run_id"] = run_id
            bet_rows.append(graded)

        print(f"Processed {min(i + batch_size, len(usable))}/{len(usable)} games")

        # small delay to be nice to Render (optional)
        time.sleep(0.05)

    # Write bet rows
    print(f"Inserting bets: {len(bet_rows)}")
    # insert in chunks to avoid payload limits
    inserted_bets = 0
    for i in range(0, len(bet_rows), 1000):
        chunk = bet_rows[i:i + 1000]
        sb_insert("/rest/v1/model_backtest_bets", chunk)
        inserted_bets += len(chunk)

    # Aggregate run stats
    wins = sum(1 for b in bet_rows if b["outcome_status"] == "win")
    losses = sum(1 for b in bet_rows if b["outcome_status"] == "loss")
    bets = wins + losses
    units = float(sum(float(b.get("units") or 0.0) for b in bet_rows))
    win_rate = float(wins / bets) if bets > 0 else None
    roi = float(units / bets) if bets > 0 else None

    # Patch run row
    sb_patch(
        "/rest/v1/model_backtest_runs",
        match_params={"id": f"eq.{run_id}"},
        patch={
            "finished_at": "now()",
            "n_bets": bets,
            "n_wins": wins,
            "n_losses": losses,
            "win_rate": win_rate,
            "units": units,
            "roi": roi,
        },
    )

    print("\nDONE")
    print(f"Run: {run_id}")
    print(f"Bets: {bets} | Wins: {wins} | Losses: {losses}")
    print(f"Win rate: {win_rate:.3f}" if win_rate is not None else "Win rate: —")
    print(f"Units: {units:.3f}")
    print(f"ROI (units/bet): {roi:.4f}" if roi is not None else "ROI: —")


if __name__ == "__main__":
    main()

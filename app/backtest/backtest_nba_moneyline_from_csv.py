#!/usr/bin/env python3
"""
CSV-driven NBA moneyline backtest.

Reads historical games from a local CSV (default: data/nba_calibration_ml.csv),
calls the production Render model for predictions, grades outcomes, computes
performance stats, and inserts results into Supabase backtest tables.

Usage:
    python -m app.backtest.backtest_nba_moneyline_from_csv
    python -m app.backtest.backtest_nba_moneyline_from_csv --csv data/nba_games.csv
    python -m app.backtest.backtest_nba_moneyline_from_csv --min-edge 0.05 --start-date 2024-01-01
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from typing import Any, Dict, List, Optional

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


def _lazy_env():
    """Lazy-load env vars so CSV parsing can be tested without all keys set."""
    return {
        "SUPABASE_URL": env("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": env("SUPABASE_SERVICE_ROLE_KEY"),
        "MODEL_API_URL": env("MODEL_API_URL", "https://pickpulse-model.onrender.com").rstrip("/"),
        "MODEL_API_KEY": env("MODEL_API_KEY"),
        "MODEL_VERSION": env("MODEL_VERSION", "render_nba_ml_v1"),
    }


_ENV: Optional[Dict[str, str]] = None


def get_env() -> Dict[str, str]:
    global _ENV
    if _ENV is None:
        _ENV = _lazy_env()
    return _ENV


# -------------------------
# Supabase REST helpers
# -------------------------
def sb_headers() -> Dict[str, str]:
    e = get_env()
    return {
        "Authorization": f"Bearer {e['SUPABASE_SERVICE_ROLE_KEY']}",
        "apikey": e["SUPABASE_SERVICE_ROLE_KEY"],
        "Content-Type": "application/json",
    }


def sb_insert(path: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    url = f"{get_env()['SUPABASE_URL'].rstrip('/')}{path}"
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
    url = f"{get_env()['SUPABASE_URL'].rstrip('/')}{path}"
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
    e = get_env()
    url = f"{e['MODEL_API_URL']}/v1/nba/recommendations"
    r = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "x-model-key": e["MODEL_API_KEY"],
            "Authorization": f"Bearer {e['MODEL_API_KEY']}",
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
    if odds == 0:
        return 0.0
    if odds < 0:
        return 100.0 / abs(odds)
    return odds / 100.0


def implied_prob_from_american(odds: int) -> float:
    if odds == 0:
        return 0.5
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def clamp_int(x: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(x))))


def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None or str(x).strip() == "":
            return None
        return float(x)
    except (ValueError, TypeError):
        return None


def safe_int(x: Any) -> Optional[int]:
    f = safe_float(x)
    if f is None:
        return None
    return int(f)


def normalize(s: str) -> str:
    return (s or "").strip().lower()


def pick_side_from_selection(selection: str, home_team: str, away_team: str) -> Optional[str]:
    sel = normalize(selection)
    home = normalize(home_team)
    away = normalize(away_team)

    if home and home in sel:
        return "home"
    if away and away in sel:
        return "away"

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
# CSV loading
# -------------------------

# Columns in nba_calibration_ml.csv (rich):
#   date, season, home_team, away_team, home_pts, away_pts, home_win,
#   snapshot_time, event_id, commence_time, bookmaker_key,
#   home_odds, away_odds, p_home_mkt, p_away_mkt, p_home_nv, p_away_nv,
#   snapshot_offset_minutes, match_status
#
# Columns in nba_games.csv (minimal):
#   date, away_team, home_team, away_pts, home_pts, season, line, ou

def detect_csv_format(headers: List[str]) -> str:
    """Return 'calibration' if rich format, 'basic' if minimal."""
    if "home_odds" in headers and "away_odds" in headers:
        return "calibration"
    return "basic"


def load_csv(path: str, start_date: Optional[str], end_date: Optional[str],
             book: Optional[str]) -> List[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        fmt = detect_csv_format(headers)
        rows: List[Dict[str, Any]] = []

        for raw in reader:
            date = raw.get("date", "")
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue

            # Filter by bookmaker if requested (calibration CSV only)
            if book and fmt == "calibration":
                if raw.get("bookmaker_key", "") != book:
                    continue

            home_team = raw.get("home_team", "")
            away_team = raw.get("away_team", "")
            home_pts = safe_float(raw.get("home_pts"))
            away_pts = safe_float(raw.get("away_pts"))

            if not home_team or not away_team:
                continue
            if home_pts is None or away_pts is None:
                continue

            if fmt == "calibration":
                home_odds = safe_int(raw.get("home_odds"))
                away_odds = safe_int(raw.get("away_odds"))
                event_id = raw.get("event_id", "")
                commence_time = raw.get("commence_time", "")
            else:
                # basic CSV has no odds — skip rows without odds
                home_odds = None
                away_odds = None
                event_id = ""
                commence_time = raw.get("date", "") + "T00:00:00Z"

            if home_odds is None or away_odds is None:
                continue

            rows.append({
                "date": date,
                "home_team": home_team,
                "away_team": away_team,
                "home_pts": home_pts,
                "away_pts": away_pts,
                "home_odds": home_odds,
                "away_odds": away_odds,
                "event_id": event_id,
                "commence_time": commence_time,
            })

    return rows


# -------------------------
# Game payload for model API
# -------------------------
def build_game_payload(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    event_id = row.get("event_id") or f"{row['date']}_{row['home_team']}_{row['away_team']}"
    home_team = row["home_team"]
    away_team = row["away_team"]
    commence = row.get("commence_time", "")
    ml_home = row["home_odds"]
    ml_away = row["away_odds"]

    return {
        "id": str(event_id),
        "sport": "nba",
        "homeTeam": {"name": str(home_team), "abbreviation": None},
        "awayTeam": {"name": str(away_team), "abbreviation": None},
        "startTime": str(commence),
        "odds": {
            "moneyline": {"home": ml_home, "away": ml_away},
            "spread": None,
            "total": None,
        },
    }


# -------------------------
# Grade a single game
# -------------------------
def grade_moneyline(
    row: Dict[str, Any],
    reco: Dict[str, Any],
    min_edge: float,
) -> Dict[str, Any]:
    event_id = str(row.get("event_id", ""))
    home_team = str(row["home_team"])
    away_team = str(row["away_team"])

    ml_home = row["home_odds"]
    ml_away = row["away_odds"]

    home_pts = row["home_pts"]
    away_pts = row["away_pts"]

    model_status = reco.get("status", "no_bet")
    model_selection = reco.get("selection")
    model_conf = reco.get("confidence")
    model_score = reco.get("score")

    picked_side = None
    picked_odds = None
    outcome_status = "no_bet"
    units = 0.0
    edge = None
    win_prob = None

    if model_status == "pick" and isinstance(model_selection, str):
        picked_side = pick_side_from_selection(model_selection, home_team, away_team)
        if picked_side == "home":
            picked_odds = ml_home
        elif picked_side == "away":
            picked_odds = ml_away

        # Compute edge from model score and picked odds
        if model_score is not None and picked_odds is not None:
            win_prob = model_score / 100.0
            implied = implied_prob_from_american(int(picked_odds))
            edge = win_prob - implied

        # Apply min-edge filter (override model's own threshold)
        if edge is not None and edge < min_edge:
            model_status = "no_bet"
            outcome_status = "no_bet"
            units = 0.0
        elif picked_side in ("home", "away") and picked_odds is not None:
            picked_won = (home_pts > away_pts) if picked_side == "home" else (away_pts > home_pts)
            if home_pts == away_pts:
                outcome_status = "push"
                units = 0.0
            elif picked_won:
                outcome_status = "win"
                units = american_profit_per_1u(int(picked_odds))
            else:
                outcome_status = "loss"
                units = -1.0

    return {
        "sport": "nba",
        "market": "moneyline",
        "model_version": get_env()["MODEL_VERSION"],
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


# -------------------------
# Main
# -------------------------
def main():
    parser = argparse.ArgumentParser(description="CSV-driven NBA moneyline backtest")
    parser.add_argument("--csv", default="data/nba_calibration_ml.csv",
                        help="Path to CSV file (default: data/nba_calibration_ml.csv)")
    parser.add_argument("--min-edge", type=float, default=0.00,
                        help="Minimum edge threshold to place bet (default: 0.00)")
    parser.add_argument("--start-date", default=None,
                        help="Filter games on or after this date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=None,
                        help="Filter games on or before this date (YYYY-MM-DD)")
    parser.add_argument("--book", default=None,
                        help="Bookmaker key to filter (calibration CSV only, e.g. 'fanduel')")
    args = parser.parse_args()

    csv_path = args.csv
    min_edge = args.min_edge

    print(f"Loading CSV: {csv_path}")
    rows = load_csv(csv_path, args.start_date, args.end_date, args.book)
    print(f"Loaded {len(rows)} usable rows (with scores + odds)")
    if not rows:
        raise SystemExit("No usable rows found. Check CSV path and filters.")

    date_range = f"{rows[0]['date']} to {rows[-1]['date']}"
    print(f"Date range: {date_range}")
    if min_edge > 0:
        print(f"Min edge filter: {min_edge:.2%}")

    # Create backtest run in Supabase
    notes = (
        f"CSV backtest from {csv_path}. "
        f"Dates: {date_range}. "
        f"Min edge: {min_edge:.4f}."
    )
    if args.book:
        notes += f" Book: {args.book}."

    run_row = {
        "sport": "nba",
        "market": "moneyline",
        "model_version": get_env()["MODEL_VERSION"],
        "n_games": len(rows),
        "notes": notes,
    }
    inserted = sb_insert("/rest/v1/model_backtest_runs", [run_row])
    if not inserted:
        raise SystemExit("Failed to create model_backtest_runs row.")
    run_id = inserted[0]["id"]
    print(f"Created backtest run: {run_id}")

    # Call model in batches
    batch_size = 200
    bet_rows: List[Dict[str, Any]] = []

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        payload = [build_game_payload(r) for r in batch]
        payload = [p for p in payload if p is not None]
        if not payload:
            continue

        data = call_model_recommendations(payload)
        by_game = data.get("byGameId", {}) if isinstance(data, dict) else {}
        if not isinstance(by_game, dict):
            by_game = {}

        for r in batch:
            gid = str(r.get("event_id", ""))
            recs = by_game.get(gid, {})
            ml = recs.get("moneyline", {"status": "no_bet", "reason": "missing_reco"})
            graded = grade_moneyline(r, ml, min_edge)
            graded["run_id"] = run_id
            bet_rows.append(graded)

        processed = min(i + batch_size, len(rows))
        print(f"Processed {processed}/{len(rows)} games")
        time.sleep(0.05)

    # Insert bet rows in chunks
    print(f"Inserting {len(bet_rows)} bet rows to Supabase...")
    for i in range(0, len(bet_rows), 1000):
        chunk = bet_rows[i:i + 1000]
        sb_insert("/rest/v1/model_backtest_bets", chunk)

    # Compute stats
    bets_placed = [b for b in bet_rows if b["outcome_status"] in ("win", "loss", "push")]
    wins = sum(1 for b in bets_placed if b["outcome_status"] == "win")
    losses = sum(1 for b in bets_placed if b["outcome_status"] == "loss")
    pushes = sum(1 for b in bets_placed if b["outcome_status"] == "push")
    n_bets = wins + losses
    total_units = sum(b["units"] for b in bets_placed)
    win_rate = wins / n_bets if n_bets > 0 else None
    roi = total_units / n_bets if n_bets > 0 else None
    no_bets = sum(1 for b in bet_rows if b["outcome_status"] == "no_bet")

    # Patch run with final stats
    sb_patch(
        "/rest/v1/model_backtest_runs",
        match_params={"id": f"eq.{run_id}"},
        patch={
            "finished_at": "now()",
            "n_bets": n_bets,
            "n_wins": wins,
            "n_losses": losses,
            "win_rate": win_rate,
            "units": total_units,
            "roi": roi,
        },
    )

    # Print summary
    print("\n" + "=" * 50)
    print("BACKTEST COMPLETE")
    print("=" * 50)
    print(f"Run ID:     {run_id}")
    print(f"Games:      {len(rows)}")
    print(f"Bets:       {n_bets} ({no_bets} no-bet, {pushes} push)")
    print(f"Wins:       {wins}")
    print(f"Losses:     {losses}")
    print(f"Win rate:   {win_rate:.1%}" if win_rate is not None else "Win rate:   —")
    print(f"Units:      {total_units:+.2f}")
    print(f"ROI:        {roi:.1%}" if roi is not None else "ROI:        —")
    print("=" * 50)


if __name__ == "__main__":
    main()

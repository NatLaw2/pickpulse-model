# app/data/odds_history_fetch.py
"""Fetch historical NBA odds from The Odds API and join with BRef game data.

Produces data/nba_calibration_ml.csv with one row per game including:
- Game outcome (home_win)
- Pre-game odds snapshot (closest to T-15 before tip)
- No-vig implied probabilities
- Snapshot offset (minutes before game start)

Usage:
    python -m app.data.odds_history_fetch [--in-csv data/nba_games.csv] [--out-csv data/nba_calibration_ml.csv]

Resumable: saves checkpoint after each date to data/_odds_checkpoint.csv
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import requests
import pandas as pd


ODDS_API_BASE = "https://api.the-odds-api.com/v4"
NBA_SPORT_KEY = "basketball_nba"


def implied_prob_from_american(odds: int) -> float:
    if odds == 0:
        return 0.5
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def no_vig_normalize(p_home: float, p_away: float) -> Tuple[float, float]:
    s = p_home + p_away
    if s <= 0:
        return 0.5, 0.5
    return p_home / s, p_away / s


def _sleep_polite(seconds: float = 1.1):
    time.sleep(seconds)


def fetch_historical_odds_snapshot(
    api_key: str,
    sport_key: str,
    snapshot_iso: str,
    regions: str = "us",
    markets: str = "h2h",
    odds_format: str = "american",
    date_format: str = "iso",
    bookmakers: Optional[str] = None,
    timeout_s: int = 30,
) -> Dict[str, Any]:
    """
    GET /v4/historical/sports/{sport}/odds?date=...
    Returns: { timestamp, previous_timestamp, next_timestamp, data: [...] }
    """
    url = f"{ODDS_API_BASE}/historical/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format,
        "dateFormat": date_format,
        "date": snapshot_iso,
    }
    if bookmakers:
        params["bookmakers"] = bookmakers

    resp = requests.get(url, params=params, timeout=timeout_s)

    # Log remaining credits from headers
    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")

    if not resp.ok:
        raise RuntimeError(f"Odds API error {resp.status_code}: {resp.text[:500]}")

    print(f"    [credits] used={used} remaining={remaining}")
    return resp.json()


def pick_bookmaker(event: Dict[str, Any], preferred_keys: List[str]) -> Optional[Dict[str, Any]]:
    books = event.get("bookmakers") or []
    for k in preferred_keys:
        for b in books:
            if (b.get("key") or "").lower() == k.lower():
                return b
    return books[0] if books else None


def extract_h2h_odds(
    event: Dict[str, Any],
    home_team: str,
    away_team: str,
    preferred_books: List[str],
) -> Tuple[Optional[str], Optional[int], Optional[int], str]:
    """Returns: (book_key, home_odds, away_odds, status)"""
    book = pick_bookmaker(event, preferred_books)
    if not book:
        return None, None, None, "no_book"

    markets = book.get("markets") or []
    h2h = next((m for m in markets if m.get("key") == "h2h"), None)
    if not h2h:
        return book.get("key"), None, None, "no_market"

    outcomes = h2h.get("outcomes") or []
    if not outcomes:
        return book.get("key"), None, None, "no_outcomes"

    home_row = next((o for o in outcomes if o.get("name") == home_team), None)
    away_row = next((o for o in outcomes if o.get("name") == away_team), None)

    if not home_row or not away_row:
        return book.get("key"), None, None, "name_mismatch"

    home_odds = home_row.get("price")
    away_odds = away_row.get("price")
    if home_odds is None or away_odds is None:
        return book.get("key"), None, None, "no_prices"

    try:
        return book.get("key"), int(home_odds), int(away_odds), "ok"
    except Exception:
        return book.get("key"), None, None, "no_prices"


# ---------------------------------------------------------------------------
# Team name mapping: BRef name -> Odds API name
# ---------------------------------------------------------------------------
# The Odds API uses slightly different team names than Basketball Reference.
# This mapping covers known differences.
_BREF_TO_ODDS = {
    "Los Angeles Clippers": "Los Angeles Clippers",
    "LA Clippers": "Los Angeles Clippers",
    "Brooklyn Nets": "Brooklyn Nets",
    "Charlotte Bobcats": "Charlotte Hornets",
    # Most names match exactly; add overrides as discovered
}


def _normalize_team(bref_name: str) -> str:
    """Map BRef team name to Odds API convention."""
    return _BREF_TO_ODDS.get(bref_name, bref_name)


# ---------------------------------------------------------------------------
# Snapshot time selection
# ---------------------------------------------------------------------------

def _best_snapshot_time(date_str: str) -> str:
    """Pick the best snapshot time for a given game date.

    Most NBA games start between 7PM-10:30PM ET (00:00-03:30 UTC next day).
    We want odds close to but before tip-off.

    Strategy: use 23:30 UTC (6:30PM ET) which is typically 30-60 min before
    the first games and gives us pre-game odds for all evening games.
    """
    return f"{date_str}T23:30:00Z"


def _compute_offset_minutes(snapshot_iso: str, commence_iso: Optional[str]) -> Optional[float]:
    """Minutes between snapshot and game start (positive = snapshot before game)."""
    if not commence_iso:
        return None
    try:
        snap_dt = datetime.fromisoformat(snapshot_iso.replace("Z", "+00:00"))
        comm_dt = datetime.fromisoformat(commence_iso.replace("Z", "+00:00"))
        delta = (comm_dt - snap_dt).total_seconds() / 60.0
        return round(delta, 1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_nba_calibration_ml(
    in_csv: str = "data/nba_games.csv",
    out_csv: str = "data/nba_calibration_ml.csv",
    checkpoint_csv: str = "data/_odds_checkpoint.csv",
):
    api_key = os.getenv("ODDS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing ODDS_API_KEY env var. Set it in .env or environment.")

    preferred_books = ["fanduel", "draftkings", "betmgm", "bovada"]
    bookmakers_param = os.getenv("ODDS_BOOKMAKERS_PARAM", "").strip() or None

    df = pd.read_csv(in_csv)
    required = {"date", "home_team", "away_team", "home_pts", "away_pts"}
    missing = sorted(list(required - set(df.columns)))
    if missing:
        raise RuntimeError(f"{in_csv} missing columns: {missing}")

    df["home_win"] = (df["home_pts"] > df["away_pts"]).astype(int)

    # Load checkpoint if exists (dates already fetched)
    done_dates: set = set()
    checkpoint_rows: List[Dict[str, Any]] = []
    if os.path.exists(checkpoint_csv):
        ckpt = pd.read_csv(checkpoint_csv)
        done_dates = set(ckpt["date"].astype(str).unique())
        checkpoint_rows = ckpt.to_dict("records")
        print(f"[odds] Resuming: {len(done_dates)} dates already fetched, {len(checkpoint_rows)} rows cached")

    unique_dates = sorted(df["date"].astype(str).unique().tolist())
    remaining_dates = [d for d in unique_dates if d not in done_dates]
    print(f"[odds] Total dates: {len(unique_dates)}, remaining: {len(remaining_dates)}")

    # Cache: date -> list of events from API
    snapshot_cache: Dict[str, Dict[str, Any]] = {}

    for i, d in enumerate(remaining_dates, start=1):
        snap_iso = _best_snapshot_time(d)
        print(f"[odds] {i}/{len(remaining_dates)} date={d} snap={snap_iso}")

        try:
            payload = fetch_historical_odds_snapshot(
                api_key=api_key,
                sport_key=NBA_SPORT_KEY,
                snapshot_iso=snap_iso,
                regions="us",
                markets="h2h",
                odds_format="american",
                date_format="iso",
                bookmakers=bookmakers_param,
            )
            snapshot_cache[d] = payload
        except Exception as e:
            print(f"[odds] FAILED date={d}: {e}")
            snapshot_cache[d] = {"timestamp": snap_iso, "data": []}

        # Process games for this date immediately
        games_on_date = df[df["date"].astype(str) == d]
        events = (snapshot_cache[d].get("data") or [])
        actual_snap_time = snapshot_cache[d].get("timestamp", snap_iso)

        for _, g in games_on_date.iterrows():
            home_team = str(g["home_team"])
            away_team = str(g["away_team"])
            home_odds_api = _normalize_team(home_team)
            away_odds_api = _normalize_team(away_team)

            # Match event by team names
            event = next(
                (ev for ev in events
                 if ev.get("home_team") == home_odds_api
                 and ev.get("away_team") == away_odds_api),
                None,
            )

            row = {
                "date": d,
                "season": int(g.get("season", 0)),
                "home_team": home_team,
                "away_team": away_team,
                "home_pts": int(g["home_pts"]),
                "away_pts": int(g["away_pts"]),
                "home_win": int(g["home_win"]),
                "snapshot_time": actual_snap_time,
                "event_id": None,
                "commence_time": None,
                "bookmaker_key": None,
                "home_odds": None,
                "away_odds": None,
                "p_home_mkt": None,
                "p_away_mkt": None,
                "p_home_nv": None,
                "p_away_nv": None,
                "snapshot_offset_minutes": None,
                "match_status": "no_event",
            }

            if event:
                row["event_id"] = event.get("id")
                row["commence_time"] = event.get("commence_time")
                row["snapshot_offset_minutes"] = _compute_offset_minutes(
                    actual_snap_time, event.get("commence_time")
                )

                book_key, h_odds, a_odds, status = extract_h2h_odds(
                    event, home_odds_api, away_odds_api, preferred_books,
                )
                row["bookmaker_key"] = book_key

                if status == "ok":
                    row["home_odds"] = h_odds
                    row["away_odds"] = a_odds
                    row["p_home_mkt"] = implied_prob_from_american(h_odds)
                    row["p_away_mkt"] = implied_prob_from_american(a_odds)
                    p_h_nv, p_a_nv = no_vig_normalize(row["p_home_mkt"], row["p_away_mkt"])
                    row["p_home_nv"] = round(p_h_nv, 6)
                    row["p_away_nv"] = round(p_a_nv, 6)
                    row["match_status"] = "matched"
                else:
                    row["match_status"] = status

            checkpoint_rows.append(row)

        # Save checkpoint after each date
        ckpt_df = pd.DataFrame(checkpoint_rows)
        ckpt_df.to_csv(checkpoint_csv, index=False)

        _sleep_polite(1.2)

    # Write final output
    out_df = pd.DataFrame(checkpoint_rows)
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    out_df.to_csv(out_csv, index=False)

    n_matched = (out_df["match_status"] == "matched").sum()
    n_total = len(out_df)
    print(f"\n[done] Wrote {n_total} rows -> {out_csv}")
    print(f"  matched={n_matched} ({n_matched/n_total*100:.1f}%)")
    print(f"  no_event={( out_df['match_status'] == 'no_event').sum()}")
    print(f"  name_mismatch={(out_df['match_status'] == 'name_mismatch').sum()}")
    print(f"  other={(out_df['match_status'].isin(['no_book', 'no_market', 'no_prices'])).sum()}")

    # Clean up checkpoint
    if os.path.exists(checkpoint_csv):
        os.remove(checkpoint_csv)
        print(f"  Cleaned up checkpoint: {checkpoint_csv}")

    return out_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch historical NBA odds from The Odds API")
    parser.add_argument("--in-csv", default="data/nba_games.csv", help="Input games CSV")
    parser.add_argument("--out-csv", default="data/nba_calibration_ml.csv", help="Output CSV")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    build_nba_calibration_ml(in_csv=args.in_csv, out_csv=args.out_csv)

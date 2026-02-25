#!/usr/bin/env python3
"""
PickPulse — Complete Model Evaluation Pipeline
===============================================

Computes win%, ROI, drawdown, losing streaks, and calibration across
confidence tiers using auditable, leakage-free methodology.

Data Sources (tried in order):
  1. `pick_results` table — pre-graded picks with locked odds + scores
     Joined with `locked_picks` for the `locked_at` timestamp.
  2. `locked_picks` + `game_results` — grades from scratch if pick_results
     is empty (same logic as grade_picks edge function).

NO-LEAKAGE GUARANTEE:
  - Every qualifying bet must have `locked_at < game_start_time`.
  - Picks without a valid locked_at timestamp are excluded.
  - The locked_at comes from `locked_picks.locked_at` which is set by
    `lock_picks_tminus15` at T-15 before game start.

TIER DEFINITIONS (from repo):
  - 70%+       → confidence >= 0.70  (subset of top_pick)
  - 65-70%     → 0.65 <= confidence < 0.70
  - 60-65%     → 0.60 <= confidence < 0.65
  - Strong Lean→ tier='strong_lean' (score 66-73, repo-canonical)

Usage:
  python3 scripts/evaluate_model.py
  python3 scripts/evaluate_model.py --test-split 0.30
  python3 scripts/evaluate_model.py --min-prob 0.55 --odds -110

Flags:
  --test-split  Fraction of dates reserved as "test set" (default: 0.30)
  --min-prob    Minimum confidence to qualify as a bet (default: 0.55)
  --odds        Default American odds when locked odds are missing (default: -110)
  --source      Data source: "supabase" (default) or "csv"
  --csv-path    Path to CSV file if --source csv

Requirements:
  pip install requests python-dotenv  (python-dotenv optional but recommended)

Outputs (in /outputs):
  evaluation_summary.json   — Full metrics (all + test-only)
  evaluation_tiers.csv      — Tier breakdown table
  evaluation_calibration.csv— Calibration bins
  evaluation_bets.csv       — One row per qualifying bet (auditable)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Env / Supabase helpers
# ---------------------------------------------------------------------------

def _load_dotenv():
    """Try to load .env from repo root."""
    repo = Path(__file__).resolve().parent.parent
    env_path = repo / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            # Manual parse
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k and k not in os.environ:
                    os.environ[k] = v


def _env(name: str, *fallbacks: str) -> str:
    for key in (name, *fallbacks):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    raise RuntimeError(f"Missing env var: {name}")


import requests

_sb_url: Optional[str] = None
_sb_key: Optional[str] = None


def _sb_config() -> Tuple[str, str]:
    global _sb_url, _sb_key
    if _sb_url is None:
        _sb_url = _env("SUPABASE_URL")
        _sb_key = _env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY")
    return _sb_url, _sb_key  # type: ignore


def _headers() -> Dict[str, str]:
    _, key = _sb_config()
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
    }


def _sb_get_all(path: str, params: Dict[str, str], limit: int = 100_000) -> List[Dict[str, Any]]:
    base, _ = _sb_config()
    url = f"{base.rstrip('/')}{path}"
    out: List[Dict[str, Any]] = []
    page = 1000
    offset = 0
    while len(out) < limit:
        take = min(page, limit - len(out))
        r = requests.get(url, headers=_headers(), params={**params, "limit": str(take), "offset": str(offset)}, timeout=120)
        if not r.ok:
            raise RuntimeError(f"Supabase GET {r.status_code}: {r.text[:400]}")
        batch = r.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected response: {str(batch)[:300]}")
        out.extend(batch)
        if len(batch) < take:
            break
        offset += take
    return out


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

PICK_RESULT_COLS = ",".join([
    "id", "locked_pick_id", "event_id", "sport", "market", "side",
    "tier", "score", "confidence", "source", "run_date",
    "start_time", "home_team", "away_team", "selection_team",
    "result", "units",
    "locked_ml_home", "locked_ml_away",
    "locked_spread_home_point", "locked_spread_home_price",
    "locked_spread_away_point", "locked_spread_away_price",
    "home_score", "away_score", "graded_at",
])

LOCKED_PICK_COLS = ",".join([
    "id", "event_id", "locked_at", "game_start_time",
])


def fetch_pick_results() -> List[Dict[str, Any]]:
    """Fetch all graded pick_results for NBA."""
    return _sb_get_all("/rest/v1/pick_results", {
        "select": PICK_RESULT_COLS,
        "sport": "eq.nba",
        "result": "in.(win,loss,push)",
        "order": "start_time.asc",
    })


def fetch_locked_picks_timestamps() -> Dict[str, Dict[str, str]]:
    """Fetch locked_at and game_start_time from locked_picks, keyed by id."""
    rows = _sb_get_all("/rest/v1/locked_picks", {
        "select": LOCKED_PICK_COLS,
        "sport": "eq.nba",
    })
    return {str(r["id"]): r for r in rows}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(s: Any) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        # Handle ISO with or without tz
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _safe_float(x: Any) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int(x: Any) -> Optional[int]:
    f = _safe_float(x)
    return int(f) if f is not None and math.isfinite(f) else None


def _american_payout(odds: int) -> float:
    """Units won per 1-unit stake at given American odds."""
    if odds == 0:
        return 0.0
    return (100.0 / abs(odds)) if odds < 0 else (odds / 100.0)


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

def classify_tier(confidence: float, tier_db: str) -> str:
    """
    Map to evaluation tiers:
      - "70%+"      : confidence >= 0.70
      - "65-70%"    : 0.65 <= confidence < 0.70
      - "60-65%"    : 0.60 <= confidence < 0.65
      - "Strong Lean": tier_db == 'strong_lean' (regardless of confidence)
    For bets below 0.60 that aren't strong_lean, return "below_threshold".
    """
    if tier_db == "strong_lean":
        return "Strong Lean"
    if confidence >= 0.70:
        return "70%+"
    if confidence >= 0.65:
        return "65-70%"
    if confidence >= 0.60:
        return "60-65%"
    return "below_threshold"


# ---------------------------------------------------------------------------
# Build qualifying bets
# ---------------------------------------------------------------------------

def build_bets(
    pick_results: List[Dict[str, Any]],
    locked_map: Dict[str, Dict[str, str]],
    default_odds: int,
    min_prob: float,
) -> List[Dict[str, Any]]:
    """
    Build list of qualifying bets with leakage checks.
    Returns list sorted by start_time ascending.
    """
    bets: List[Dict[str, Any]] = []
    excluded = {"no_locked_at": 0, "leakage": 0, "below_min": 0, "no_result": 0}

    for pr in pick_results:
        # Must have a graded result
        result = pr.get("result")
        if result not in ("win", "loss", "push"):
            excluded["no_result"] += 1
            continue

        confidence = _safe_float(pr.get("confidence"))
        if confidence is None or confidence < min_prob:
            excluded["below_min"] += 1
            continue

        # Get locked_at from locked_picks join
        lp_id = str(pr.get("locked_pick_id", ""))
        lp = locked_map.get(lp_id, {})
        locked_at = _parse_dt(lp.get("locked_at"))
        game_start = _parse_dt(lp.get("game_start_time")) or _parse_dt(pr.get("start_time"))

        if locked_at is None:
            excluded["no_locked_at"] += 1
            continue

        # LEAKAGE CHECK: locked_at must be before game_start
        if game_start and locked_at >= game_start:
            excluded["leakage"] += 1
            continue

        # Determine odds used
        market = pr.get("market", "")
        side = pr.get("selection_team", pr.get("side", ""))
        home = (pr.get("home_team") or "").strip().lower()
        away = (pr.get("away_team") or "").strip().lower()
        sel = (side or "").strip().lower()

        is_home = (home and home in sel) or (sel and sel in home)

        if market == "moneyline":
            odds_home = _safe_int(pr.get("locked_ml_home"))
            odds_away = _safe_int(pr.get("locked_ml_away"))
            odds_used = (odds_home if is_home else odds_away) if (odds_home and odds_away) else None
        elif market == "spread":
            odds_used = _safe_int(pr.get(f"locked_spread_{'home' if is_home else 'away'}_price"))
        else:
            odds_used = None

        if odds_used is None:
            odds_used = default_odds

        # Units from pre-graded result if available, otherwise compute
        units_from_db = _safe_float(pr.get("units"))
        if units_from_db is not None and result != "push":
            units_change = units_from_db
        elif result == "win":
            units_change = _american_payout(odds_used)
        elif result == "loss":
            units_change = -1.0
        else:
            units_change = 0.0  # push

        tier_db = pr.get("tier", "")
        eval_tier = classify_tier(confidence, tier_db)

        bets.append({
            "game_id": pr.get("event_id", ""),
            "date": pr.get("run_date", ""),
            "start_time": pr.get("start_time", ""),
            "locked_at": locked_at.isoformat(),
            "team_picked": side,
            "prob": round(confidence, 4),
            "tier_db": tier_db,
            "tier": eval_tier,
            "market": market,
            "result": result,
            "odds_used": odds_used,
            "units_change": round(units_change, 4),
            "home_team": pr.get("home_team", ""),
            "away_team": pr.get("away_team", ""),
            "home_score": pr.get("home_score"),
            "away_score": pr.get("away_score"),
        })

    # Sort by start_time
    bets.sort(key=lambda b: b.get("start_time", ""))

    # Compute cumulative units and drawdown
    cum = 0.0
    peak = 0.0
    for b in bets:
        cum += b["units_change"]
        b["cum_units"] = round(cum, 4)
        peak = max(peak, cum)
        b["drawdown"] = round(cum - peak, 4)

    print(f"  Qualifying bets: {len(bets)}")
    print(f"  Excluded: {json.dumps(excluded)}")
    return bets


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(bets: List[Dict[str, Any]], label: str = "") -> Dict[str, Any]:
    """Compute full metrics for a list of bets."""
    if not bets:
        return {
            "label": label,
            "bets": 0, "wins": 0, "losses": 0, "pushes": 0,
            "win_rate": None, "units_won": 0.0, "roi": None,
            "max_drawdown": 0.0, "longest_losing_streak": 0,
        }

    wins = sum(1 for b in bets if b["result"] == "win")
    losses = sum(1 for b in bets if b["result"] == "loss")
    pushes = sum(1 for b in bets if b["result"] == "push")
    decided = wins + losses
    units_won = sum(b["units_change"] for b in bets)

    # Max drawdown
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for b in bets:
        cum += b["units_change"]
        peak = max(peak, cum)
        dd = cum - peak
        max_dd = min(max_dd, dd)

    # Longest losing streak
    max_streak = 0
    cur_streak = 0
    for b in bets:
        if b["result"] == "loss":
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        elif b["result"] != "push":
            cur_streak = 0

    return {
        "label": label,
        "bets": len(bets),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": round(wins / decided * 100, 2) if decided else None,
        "units_won": round(units_won, 4),
        "roi": round(units_won / decided * 100, 2) if decided else None,
        "max_drawdown": round(max_dd, 4),
        "longest_losing_streak": max_streak,
    }


def compute_calibration(bets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bin predictions into fixed probability buckets."""
    bins_def = [
        (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70),
        (0.70, 0.75), (0.75, 0.80), (0.80, 0.85), (0.85, 0.90),
        (0.90, 0.95), (0.95, 1.01),
    ]

    decided = [b for b in bets if b["result"] in ("win", "loss")]
    rows = []

    for lo, hi in bins_def:
        in_bin = [b for b in decided if lo <= b["prob"] < hi]
        if not in_bin:
            continue
        wins = sum(1 for b in in_bin if b["result"] == "win")
        avg_prob = sum(b["prob"] for b in in_bin) / len(in_bin)
        actual_wr = wins / len(in_bin)
        rows.append({
            "prob_bucket": f"{lo:.2f}-{hi:.2f}",
            "bets": len(in_bin),
            "avg_pred_prob": round(avg_prob, 4),
            "actual_win_rate": round(actual_wr, 4),
            "delta": round(actual_wr - avg_prob, 4),
        })

    return rows


# ---------------------------------------------------------------------------
# Test/train split
# ---------------------------------------------------------------------------

def split_by_dates(bets: List[Dict[str, Any]], test_frac: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str, str]:
    """
    Time-based split: most recent `test_frac` of unique dates = test set.
    Returns (all_bets, test_bets, test_start, test_end).
    """
    dates = sorted(set(b["date"] for b in bets if b["date"]))
    if not dates:
        return bets, [], "", ""

    n_test = max(1, int(len(dates) * test_frac))
    test_dates = set(dates[-n_test:])
    test_bets = [b for b in bets if b["date"] in test_dates]
    test_start = min(test_dates) if test_dates else ""
    test_end = max(test_dates) if test_dates else ""

    return bets, test_bets, test_start, test_end


# ---------------------------------------------------------------------------
# Tier breakdown
# ---------------------------------------------------------------------------

TIER_ORDER = ["70%+", "65-70%", "60-65%", "Strong Lean"]


def tier_breakdown(bets: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_tier: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for b in bets:
        t = b["tier"]
        if t in TIER_ORDER:
            by_tier[t].append(b)
    return {t: compute_metrics(by_tier.get(t, []), label=t) for t in TIER_ORDER}


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"


def write_summary(
    all_metrics: Dict[str, Any],
    test_metrics: Dict[str, Any],
    all_tiers: Dict[str, Dict[str, Any]],
    test_tiers: Dict[str, Dict[str, Any]],
    calibration: List[Dict[str, Any]],
    test_start: str,
    test_end: str,
    total_qualifying: int,
    args: argparse.Namespace,
):
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "min_prob": args.min_prob,
            "default_odds": args.odds,
            "test_split": args.test_split,
        },
        "total_games_evaluated": total_qualifying,
        "all_data": {
            "overall": all_metrics,
            "tiers": all_tiers,
        },
        "test_period": {
            "start": test_start,
            "end": test_end,
            "overall": test_metrics,
            "tiers": test_tiers,
        },
        "calibration": calibration,
        "tier_definitions": {
            "70%+": "confidence >= 0.70",
            "65-70%": "0.65 <= confidence < 0.70",
            "60-65%": "0.60 <= confidence < 0.65",
            "Strong Lean": "tier='strong_lean' (repo-canonical, score 66-73)",
        },
        "leakage_policy": "Only picks with locked_at < game_start_time are included.",
    }

    path = OUTPUT_DIR / "evaluation_summary.json"
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Wrote {path}")


def write_tiers_csv(tiers: Dict[str, Dict[str, Any]], overall: Dict[str, Any]):
    path = OUTPUT_DIR / "evaluation_tiers.csv"
    fields = ["tier", "bets", "wins", "losses", "win_rate", "units_won", "roi", "max_drawdown", "longest_losing_streak"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        # Overall row first
        row = {k: overall.get(k, "") for k in fields}
        row["tier"] = "OVERALL"
        w.writerow(row)
        for t in TIER_ORDER:
            m = tiers.get(t, {})
            row = {k: m.get(k, "") for k in fields}
            row["tier"] = t
            w.writerow(row)
    print(f"  Wrote {path}")


def write_calibration_csv(cal: List[Dict[str, Any]]):
    path = OUTPUT_DIR / "evaluation_calibration.csv"
    fields = ["prob_bucket", "bets", "avg_pred_prob", "actual_win_rate", "delta"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in cal:
            w.writerow(row)
    print(f"  Wrote {path}")


def write_bets_csv(bets: List[Dict[str, Any]]):
    path = OUTPUT_DIR / "evaluation_bets.csv"
    fields = [
        "game_id", "date", "start_time", "locked_at", "team_picked",
        "prob", "tier", "market", "result", "odds_used",
        "units_change", "cum_units", "drawdown",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for b in bets:
            w.writerow({k: b.get(k, "") for k in fields})
    print(f"  Wrote {path}")


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def print_summary(overall: Dict[str, Any], tiers: Dict[str, Dict[str, Any]], label: str = "ALL DATA"):
    wr = f"{overall['win_rate']:.1f}%" if overall["win_rate"] is not None else "-"
    roi = f"{overall['roi']:.1f}%" if overall["roi"] is not None else "-"

    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(f"  {'OVERALL':<16s}  {overall['wins']}W-{overall['losses']}L ({overall['pushes']}P)"
          f"  |  Win%: {wr}  |  ROI: {roi}"
          f"  |  Units: {overall['units_won']:+.2f}"
          f"  |  DD: {overall['max_drawdown']:.2f}"
          f"  |  Streak: {overall['longest_losing_streak']}")
    print(f"  {'-'*66}")
    for t in TIER_ORDER:
        m = tiers.get(t, {})
        if not m or m.get("bets", 0) == 0:
            print(f"  {t:<16s}  (no bets)")
            continue
        twr = f"{m['win_rate']:.1f}%" if m["win_rate"] is not None else "-"
        troi = f"{m['roi']:.1f}%" if m["roi"] is not None else "-"
        print(f"  {t:<16s}  {m['wins']}W-{m['losses']}L ({m['pushes']}P)"
              f"  |  Win%: {twr}  |  ROI: {troi}"
              f"  |  Units: {m['units_won']:+.2f}"
              f"  |  DD: {m['max_drawdown']:.2f}"
              f"  |  Streak: {m['longest_losing_streak']}")


def print_calibration(cal: List[Dict[str, Any]]):
    if not cal:
        print("\n  Calibration: not enough data.")
        return
    print(f"\n  {'Bucket':<12s} {'Bets':>5s} {'Pred':>7s} {'Actual':>7s} {'Delta':>7s}")
    print(f"  {'-'*42}")
    for row in cal:
        print(f"  {row['prob_bucket']:<12s} {row['bets']:>5d} {row['avg_pred_prob']:>7.3f} {row['actual_win_rate']:>7.3f} {row['delta']:>+7.3f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PickPulse — Complete Model Evaluation Pipeline")
    parser.add_argument("--source", choices=["supabase", "csv"], default="supabase", help="Data source")
    parser.add_argument("--csv-path", type=str, default=None, help="Path to CSV file (if --source csv)")
    parser.add_argument("--test-split", type=float, default=0.30, help="Fraction of dates for test set (default: 0.30)")
    parser.add_argument("--min-prob", type=float, default=0.55, help="Minimum confidence to qualify (default: 0.55)")
    parser.add_argument("--odds", type=int, default=-110, help="Default American odds when locked odds missing (default: -110)")
    args = parser.parse_args()

    _load_dotenv()

    if args.source == "csv":
        print("CSV source not yet implemented. Use --source supabase.")
        sys.exit(1)

    print("Fetching data from Supabase...")
    pick_results = fetch_pick_results()
    print(f"  pick_results rows: {len(pick_results)}")

    locked_map = fetch_locked_picks_timestamps()
    print(f"  locked_picks rows: {len(locked_map)}")

    print(f"\nBuilding qualifying bets (min_prob={args.min_prob}, default_odds={args.odds})...")
    bets = build_bets(pick_results, locked_map, args.odds, args.min_prob)

    if not bets:
        print("\nNo qualifying bets found. Nothing to evaluate.")
        sys.exit(0)

    # Split
    all_bets, test_bets, test_start, test_end = split_by_dates(bets, args.test_split)

    # Metrics
    all_metrics = compute_metrics(all_bets, "all")
    all_tiers = tier_breakdown(all_bets)
    test_metrics = compute_metrics(test_bets, "test")
    test_tiers = tier_breakdown(test_bets)

    # Calibration (on all data)
    calibration = compute_calibration(all_bets)

    # Console output
    print_summary(all_metrics, all_tiers, "ALL DATA")
    if test_bets:
        print_summary(test_metrics, test_tiers, f"TEST SET ({test_start} to {test_end})")
    print_calibration(calibration)

    # Write files
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nWriting outputs to {OUTPUT_DIR}/")
    write_summary(all_metrics, test_metrics, all_tiers, test_tiers, calibration, test_start, test_end, len(bets), args)
    write_tiers_csv(all_tiers, all_metrics)
    write_calibration_csv(calibration)
    write_bets_csv(bets)

    print(f"\nDone. {len(bets)} qualifying bets evaluated.")


if __name__ == "__main__":
    main()

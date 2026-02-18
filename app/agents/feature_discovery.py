"""Agent 1: Feature Discovery — pattern mining and concrete next-step tests.

Mines locked_picks + pick_results + game_results for exploitable patterns.
Outputs ranked features with sample sizes, win rates, CLV, and proposed tests.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ._supabase import (
    fetch_locked_picks,
    fetch_pick_results,
    fetch_game_results,
    since_date,
)
from ._math import safe_float


# ---------------------------------------------------------------------------
# Segment extractors
# ---------------------------------------------------------------------------

def _extract_segments(
    pick: Dict[str, Any],
    result: Optional[Dict[str, Any]],
    game: Optional[Dict[str, Any]],
) -> List[str]:
    """Extract all applicable segments for a pick."""
    segments: List[str] = []

    tier = pick.get("tier") or "unknown"
    segments.append(f"tier:{tier}")

    market = pick.get("market") or "unknown"
    segments.append(f"market:{market}")

    segments.append(f"tier_market:{tier}_{market}")

    # Confidence buckets
    conf = safe_float(pick.get("confidence"))
    if conf is not None:
        if conf >= 0.65:
            segments.append("conf:high")
        elif conf >= 0.50:
            segments.append("conf:mid")
        else:
            segments.append("conf:low")

    # Score buckets
    score = safe_float(pick.get("score"))
    if score is not None:
        if score >= 75:
            segments.append("score:75+")
        elif score >= 65:
            segments.append("score:65-74")
        else:
            segments.append("score:<65")

    # Home/away
    sel = (pick.get("selection_team") or "").strip().lower()
    home = (pick.get("home_team") or "").strip().lower()
    if sel and home and (home in sel or sel in home):
        segments.append("side:home")
    else:
        segments.append("side:away")

    # Game start time (early vs late) if available
    start = pick.get("game_start_time") or (game.get("commence_time") if game else None)
    if start and isinstance(start, str) and "T" in start:
        try:
            hour = int(start.split("T")[1][:2])
            # Convert UTC to rough ET: -5
            et_hour = (hour - 5) % 24
            if et_hour < 19:
                segments.append("slot:early")
            else:
                segments.append("slot:late")
        except (ValueError, IndexError):
            pass

    return segments


# ---------------------------------------------------------------------------
# Feature test proposals
# ---------------------------------------------------------------------------

_FEATURE_TESTS = [
    {
        "name": "rest_differential",
        "description": "Days since last game for each team (back-to-back, 2+ days rest)",
        "data_source": "game_results.commence_time (compute gap between games per team)",
        "hypothesis": "Teams on rest advantage win more; B2B teams underperform Elo expectation",
    },
    {
        "name": "line_movement_velocity",
        "description": "Rate of line movement between lock time and close",
        "data_source": "locked_picks.locked_at vs closing_lines.captured_at + price delta",
        "hypothesis": "Fast line movement toward our pick = sharp money confirmation",
    },
    {
        "name": "travel_timezone",
        "description": "Consecutive away games, cross-timezone travel impact",
        "data_source": "game_results sequence per team + team city mapping",
        "hypothesis": "West-to-East travel on B2B degrades performance",
    },
    {
        "name": "injury_timing",
        "description": "Key player status changes relative to T-15 lock window",
        "data_source": "injury_snapshots_nba timestamps vs locked_picks.locked_at",
        "hypothesis": "Late injury news after lock creates information asymmetry",
    },
    {
        "name": "late_news_timing",
        "description": "Line movement in final 15 min before game suggests late information",
        "data_source": "Compare locked odds (T-15) vs closing odds magnitude",
        "hypothesis": "Large post-lock movement indicates missed information",
    },
]


def _analyze_segment(
    segment: str,
    picks_in_segment: List[Dict[str, Any]],
    clv_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute stats for a segment."""
    wins = sum(1 for p in picks_in_segment if p.get("result") == "win")
    losses = sum(1 for p in picks_in_segment if p.get("result") == "loss")
    total = wins + losses
    win_pct = wins / total * 100 if total else None

    # Units
    units = sum(safe_float(p.get("units")) or 0.0 for p in picks_in_segment)

    # CLV from agent 3 data if available
    clv_vals: List[float] = []
    if clv_data:
        clv_by_event: Dict[str, float] = {}
        for cp in clv_data.get("picks", []):
            eid = str(cp.get("event_id", ""))
            mkt = cp.get("market", "")
            if cp.get("clv") is not None:
                clv_by_event[f"{eid}_{mkt}"] = cp["clv"]
        for p in picks_in_segment:
            key = f"{p.get('event_id', '')}_{p.get('market', '')}"
            if key in clv_by_event:
                clv_vals.append(clv_by_event[key])

    mean_clv = sum(clv_vals) / len(clv_vals) if clv_vals else None

    return {
        "segment": segment,
        "n": len(picks_in_segment),
        "n_graded": total,
        "wins": wins,
        "losses": losses,
        "win_pct": round(win_pct, 1) if win_pct is not None else None,
        "units": round(units, 3),
        "mean_clv": round(mean_clv, 5) if mean_clv is not None else None,
        "n_clv": len(clv_vals),
    }


def run(
    days: int = 180,
    clv_data: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run feature discovery over the last N days."""
    since = since_date(days)
    print(f"[feature_discovery] Fetching data since {since}...")

    results = fetch_pick_results(since)
    print(f"[feature_discovery] Pick results: {len(results)}")

    locked = fetch_locked_picks(since)
    print(f"[feature_discovery] Locked picks: {len(locked)}")

    games = fetch_game_results()
    print(f"[feature_discovery] Game results: {len(games)}")

    # Index locked picks by event_id for enrichment
    locked_by_eid: Dict[str, Dict[str, Any]] = {}
    for lp in locked:
        locked_by_eid[str(lp.get("event_id", ""))] = lp

    # Build segments
    segment_picks: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in results:
        if r.get("result") not in ("win", "loss"):
            continue
        eid = str(r.get("event_id", ""))
        lp = locked_by_eid.get(eid, r)
        game = games.get(eid)
        segs = _extract_segments(lp, r, game)
        for seg in segs:
            segment_picks[seg].append(r)

    # Analyze each segment
    patterns: List[Dict[str, Any]] = []
    for seg, picks in segment_picks.items():
        if len(picks) < 3:
            continue
        analysis = _analyze_segment(seg, picks, clv_data)
        patterns.append(analysis)

    # Rank by deviation from overall win rate
    all_graded = [r for r in results if r.get("result") in ("win", "loss")]
    overall_wins = sum(1 for r in all_graded if r["result"] == "win")
    overall_rate = overall_wins / len(all_graded) * 100 if all_graded else 50.0

    for p in patterns:
        wp = p.get("win_pct")
        p["deviation_from_overall"] = round(wp - overall_rate, 1) if wp is not None else None

    # Sort: highest absolute deviation first (most interesting patterns)
    patterns.sort(
        key=lambda x: abs(x.get("deviation_from_overall") or 0),
        reverse=True,
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "n_results": len(results),
        "n_graded": len(all_graded),
        "overall_win_pct": round(overall_rate, 1),
        "patterns": patterns[:30],  # top 30
        "proposed_feature_tests": _FEATURE_TESTS,
    }

    return report

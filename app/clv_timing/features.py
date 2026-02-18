"""CLV timing features for a locked pick.

For each pick, computes:
  - p_lock, p_close, clv_prob = p_close - p_lock
  - steam_5m, steam_15m: prob movement in windows before lock
  - velocity_30m: average prob change per minute over 30min before game start
  - range_30m, std_30m: spread and volatility of prob in 30min pre-game
  - snap_gap_lock_sec, snap_gap_close_sec: how stale the nearest snapshots are
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .snapshots import (
    _parse_iso,
    _seconds_between,
    extract_nv_prob,
    group_by_timestamp,
    nearest_snapshot,
    nv_series,
    window_slice,
)
from app.agents._math import resolve_side


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def compute_timing_features(
    pick: Dict[str, Any],
    closing_lines: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute timing features for a single locked pick.

    Args:
        pick: locked_picks row with locked_at, game_start_time, home_team, etc.
        closing_lines: all closing_lines rows for this event_id

    Returns:
        Dict with feature values. Missing features have value None with
        a reason string in "_skip_reasons".
    """
    event_id = pick.get("event_id", "")
    locked_at = pick.get("locked_at")
    game_start = pick.get("game_start_time")
    home_team = pick.get("home_team", "")
    away_team = pick.get("away_team", "")

    result: Dict[str, Any] = {
        "event_id": event_id,
        "locked_at": locked_at,
        "game_start_time": game_start,
        "_skip_reasons": [],
    }

    if not locked_at or not game_start:
        result["_skip_reasons"].append("missing_timestamps")
        return result

    # Resolve side
    side = resolve_side(pick, home_team, away_team)
    if side is None:
        result["_skip_reasons"].append("cannot_resolve_side")
        return result
    result["side"] = side

    # Group snapshots by timestamp
    snapshots = group_by_timestamp(closing_lines)
    if not snapshots:
        result["_skip_reasons"].append("no_snapshots")
        return result

    # --- Lock snapshot (latest at or before locked_at) ---
    lock_snap = nearest_snapshot(snapshots, locked_at, "at_or_before")
    if lock_snap:
        lock_ts, lock_rows, lock_gap = lock_snap
        nv = extract_nv_prob(lock_rows, home_team, away_team)
        if nv:
            p_home_lock, p_away_lock = nv
            p_lock = p_home_lock if side == "home" else p_away_lock
            result["p_lock"] = round(p_lock, 6)
            result["snap_gap_lock_sec"] = round(lock_gap, 1)
            result["lock_snap_ts"] = lock_ts
        else:
            result["_skip_reasons"].append("lock_snap_no_h2h")
    else:
        result["_skip_reasons"].append("no_lock_snapshot")

    # --- Close snapshot (latest at or before game_start) ---
    close_snap = nearest_snapshot(snapshots, game_start, "at_or_before")
    if close_snap:
        close_ts, close_rows, close_gap = close_snap
        nv = extract_nv_prob(close_rows, home_team, away_team)
        if nv:
            p_home_close, p_away_close = nv
            p_close = p_home_close if side == "home" else p_away_close
            result["p_close"] = round(p_close, 6)
            result["snap_gap_close_sec"] = round(close_gap, 1)
            result["close_snap_ts"] = close_ts
        else:
            result["_skip_reasons"].append("close_snap_no_h2h")
    else:
        result["_skip_reasons"].append("no_close_snapshot")

    # --- CLV prob ---
    if result.get("p_lock") is not None and result.get("p_close") is not None:
        result["clv_prob"] = round(result["p_close"] - result["p_lock"], 6)

    # --- Steam / velocity metrics (from no-vig time series) ---
    series = nv_series(snapshots, home_team, away_team, side)
    result.update(_compute_steam_metrics(series, locked_at, game_start))

    return result


def _compute_steam_metrics(
    series: List[Tuple[str, float]],
    locked_at: str,
    game_start: str,
) -> Dict[str, Any]:
    """Compute steam, velocity, range, and std from probability time series.

    Args:
        series: list of (iso_timestamp, p_novig) sorted by time
        locked_at: lock timestamp
        game_start: game start timestamp

    Returns:
        Dict with steam_5m, steam_15m, velocity_30m, range_30m, std_30m.
    """
    out: Dict[str, Any] = {}

    lock_dt = _parse_iso(locked_at)
    start_dt = _parse_iso(game_start)
    if lock_dt is None or start_dt is None or not series:
        return out

    # Build (datetime, prob) pairs
    points = []
    for ts, p in series:
        dt = _parse_iso(ts)
        if dt is not None:
            points.append((dt, p))
    points.sort(key=lambda x: x[0])

    if not points:
        return out

    # --- steam_5m: prob change from T-20 to T-15 (5min window before lock) ---
    out["steam_5m"] = _delta_in_window(points, lock_dt - timedelta(minutes=20), lock_dt - timedelta(minutes=15))

    # --- steam_15m: prob change from T-30 to T-15 (15min window before lock) ---
    out["steam_15m"] = _delta_in_window(points, lock_dt - timedelta(minutes=30), lock_dt - timedelta(minutes=15))

    # --- 30min pre-game window metrics ---
    window_start = start_dt - timedelta(minutes=30)
    window_points = [(dt, p) for dt, p in points if window_start <= dt <= start_dt]

    if len(window_points) >= 2:
        probs = [p for _, p in window_points]
        dt_range_min = (window_points[-1][0] - window_points[0][0]).total_seconds() / 60.0

        # velocity: total prob change / time span
        if dt_range_min > 0:
            out["velocity_30m"] = round(
                (window_points[-1][1] - window_points[0][1]) / dt_range_min, 6
            )
        else:
            out["velocity_30m"] = 0.0

        out["range_30m"] = round(max(probs) - min(probs), 6)

        # std of probabilities in window
        mean_p = sum(probs) / len(probs)
        variance = sum((p - mean_p) ** 2 for p in probs) / len(probs)
        out["std_30m"] = round(math.sqrt(variance), 6)
    elif len(window_points) == 1:
        out["velocity_30m"] = 0.0
        out["range_30m"] = 0.0
        out["std_30m"] = 0.0

    return out


def _delta_in_window(
    points: List[Tuple[datetime, float]],
    win_start: datetime,
    win_end: datetime,
) -> Optional[float]:
    """Compute prob change between nearest points to window boundaries.

    Returns (prob at win_end) - (prob at win_start), or None if insufficient data.
    """
    start_p = _nearest_prob(points, win_start)
    end_p = _nearest_prob(points, win_end)

    if start_p is None or end_p is None:
        return None
    return round(end_p - start_p, 6)


def _nearest_prob(
    points: List[Tuple[datetime, float]],
    target: datetime,
    max_gap_sec: float = 600,  # 10 minute max gap
) -> Optional[float]:
    """Find probability at the point nearest to target within max_gap."""
    best = None
    best_gap = float("inf")
    for dt, p in points:
        gap = abs((dt - target).total_seconds())
        if gap < best_gap:
            best_gap = gap
            best = p
    if best is not None and best_gap <= max_gap_sec:
        return best
    return None


# ---------------------------------------------------------------------------
# Batch computation
# ---------------------------------------------------------------------------

def compute_batch(
    picks: List[Dict[str, Any]],
    closing_by_eid: Dict[str, List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Compute timing features for a batch of picks.

    Returns:
        (features_list, coverage_stats)
    """
    results = []
    stats = {
        "total": 0,
        "has_lock_snap": 0,
        "has_close_snap": 0,
        "has_both": 0,
        "has_clv": 0,
        "has_steam": 0,
        "skipped": 0,
    }

    for pick in picks:
        stats["total"] += 1
        eid = str(pick.get("event_id", ""))
        lines = closing_by_eid.get(eid, [])

        feat = compute_timing_features(pick, lines)
        results.append(feat)

        has_lock = feat.get("p_lock") is not None
        has_close = feat.get("p_close") is not None

        if has_lock:
            stats["has_lock_snap"] += 1
        if has_close:
            stats["has_close_snap"] += 1
        if has_lock and has_close:
            stats["has_both"] += 1
        if feat.get("clv_prob") is not None:
            stats["has_clv"] += 1
        if feat.get("steam_15m") is not None:
            stats["has_steam"] += 1
        if feat.get("_skip_reasons"):
            stats["skipped"] += 1

    return results, stats

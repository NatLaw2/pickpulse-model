"""Snapshot extraction from closing_lines time series.

Provides functions to:
  - pull all snapshots for an event_id
  - find the nearest snapshot to a target timestamp
  - extract a time window of snapshots
  - compute no-vig moneyline probability from a snapshot
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.agents._math import implied_prob, normalize_no_vig


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _parse_iso(iso: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 string to timezone-aware datetime."""
    if not iso:
        return None
    try:
        s = iso.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _seconds_between(a: Optional[str], b: Optional[str]) -> Optional[float]:
    """Signed seconds from a to b (positive if b is later)."""
    da, db = _parse_iso(a), _parse_iso(b)
    if da is None or db is None:
        return None
    return (db - da).total_seconds()


# ---------------------------------------------------------------------------
# Snapshot structures
# ---------------------------------------------------------------------------

def extract_nv_prob(
    rows: List[Dict[str, Any]],
    home_team: str,
    away_team: str,
) -> Optional[Tuple[float, float]]:
    """Extract no-vig moneyline implied probability from a snapshot group.

    Args:
        rows: closing_lines rows sharing the same captured_at timestamp
        home_team: canonical home team name
        away_team: canonical away team name

    Returns:
        (p_home_nv, p_away_nv) or None if h2h odds not found
    """
    home_lower = home_team.strip().lower()
    away_lower = away_team.strip().lower()
    ml_home = None
    ml_away = None

    for r in rows:
        if r.get("market") != "h2h":
            continue
        name = (r.get("outcome_name") or "").strip().lower()
        if name == home_lower and ml_home is None:
            ml_home = r.get("price")
        elif name == away_lower and ml_away is None:
            ml_away = r.get("price")

    if ml_home is None or ml_away is None:
        return None

    p_home_raw = implied_prob(ml_home)
    p_away_raw = implied_prob(ml_away)
    if not math.isfinite(p_home_raw) or not math.isfinite(p_away_raw):
        return None

    return normalize_no_vig(p_home_raw, p_away_raw)


def group_by_timestamp(rows: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Group closing_lines rows by captured_at, sorted ascending.

    Returns list of (captured_at_iso, rows_at_that_timestamp).
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        ts = r.get("captured_at")
        if ts:
            groups.setdefault(ts, []).append(r)

    return sorted(groups.items(), key=lambda x: x[0])


def nearest_snapshot(
    snapshots: List[Tuple[str, List[Dict[str, Any]]]],
    target_iso: str,
    direction: str = "at_or_before",
) -> Optional[Tuple[str, List[Dict[str, Any]], float]]:
    """Find snapshot nearest to target timestamp.

    Args:
        snapshots: sorted (ascending) list of (captured_at, rows) tuples
        target_iso: target ISO-8601 timestamp
        direction: "at_or_before" (latest <= target) or "nearest" (closest)

    Returns:
        (captured_at, rows, gap_seconds) or None if nothing found.
        gap_seconds = abs(captured_at - target) in seconds.
    """
    target_dt = _parse_iso(target_iso)
    if target_dt is None or not snapshots:
        return None

    if direction == "at_or_before":
        best = None
        for ts, rows in snapshots:
            dt = _parse_iso(ts)
            if dt is None:
                continue
            if dt <= target_dt:
                gap = abs((target_dt - dt).total_seconds())
                best = (ts, rows, gap)
            else:
                break  # sorted ascending, no need to continue
        return best

    # "nearest": find minimum distance
    best = None
    best_gap = float("inf")
    for ts, rows in snapshots:
        dt = _parse_iso(ts)
        if dt is None:
            continue
        gap = abs((target_dt - dt).total_seconds())
        if gap < best_gap:
            best_gap = gap
            best = (ts, rows, gap)
    return best


def window_slice(
    snapshots: List[Tuple[str, List[Dict[str, Any]]]],
    start_iso: str,
    end_iso: str,
) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Return snapshots within [start, end] window (inclusive)."""
    start_dt = _parse_iso(start_iso)
    end_dt = _parse_iso(end_iso)
    if start_dt is None or end_dt is None:
        return []

    result = []
    for ts, rows in snapshots:
        dt = _parse_iso(ts)
        if dt is None:
            continue
        if start_dt <= dt <= end_dt:
            result.append((ts, rows))
    return result


def nv_series(
    snapshots: List[Tuple[str, List[Dict[str, Any]]]],
    home_team: str,
    away_team: str,
    picked_side: str,
) -> List[Tuple[str, float]]:
    """Extract time-series of no-vig probability for the picked side.

    Returns list of (captured_at_iso, p_novig_for_side) sorted by time.
    """
    series = []
    for ts, rows in snapshots:
        nv = extract_nv_prob(rows, home_team, away_team)
        if nv is None:
            continue
        p_home_nv, p_away_nv = nv
        p = p_home_nv if picked_side == "home" else p_away_nv
        series.append((ts, p))
    return series

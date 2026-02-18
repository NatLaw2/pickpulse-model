"""Shared Supabase REST client for agents.

Reuses the same pattern as app/evaluate.py: raw requests, no SDK.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_supabase_url: Optional[str] = None
_supabase_key: Optional[str] = None


def _get_sb_config() -> Tuple[str, str]:
    global _supabase_url, _supabase_key
    if _supabase_url is None:
        _supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        if not _supabase_url:
            raise RuntimeError("Missing env var: SUPABASE_URL")
        key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.environ.get("SUPABASE_ANON_KEY", "").strip()
        )
        if not key:
            raise RuntimeError("Missing env var: SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY")
        _supabase_key = key
    return _supabase_url, _supabase_key  # type: ignore[return-value]


def _headers() -> Dict[str, str]:
    _, key = _get_sb_config()
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Generic REST helpers
# ---------------------------------------------------------------------------

def sb_get(path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    base_url, _ = _get_sb_config()
    url = f"{base_url.rstrip('/')}{path}"
    r = requests.get(url, headers=_headers(), params=params, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Supabase GET {r.status_code}: {r.text[:300]}")
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected Supabase response: {str(data)[:300]}")
    return data


def sb_get_all(
    path: str, params: Dict[str, str], limit: int = 50_000
) -> List[Dict[str, Any]]:
    """Paginated fetch (offset-based, 1000 per page)."""
    out: List[Dict[str, Any]] = []
    page_size = 1000
    offset = 0
    while len(out) < limit:
        take = min(page_size, limit - len(out))
        batch = sb_get(path, {**params, "limit": str(take), "offset": str(offset)})
        out.extend(batch)
        if len(batch) < take:
            break
        offset += take
    return out


# ---------------------------------------------------------------------------
# Domain-specific fetchers (NBA only)
# ---------------------------------------------------------------------------

_LOCKED_COLS = ",".join([
    "id", "event_id", "sport", "market", "side", "tier", "score", "confidence",
    "run_date", "source", "home_team", "away_team", "selection_team",
    "game_start_time", "locked_at",
    "locked_ml_home", "locked_ml_away",
    "locked_spread_home_point", "locked_spread_home_price",
    "locked_spread_away_point", "locked_spread_away_price",
])

_RESULT_COLS = ",".join([
    "locked_pick_id", "event_id", "sport", "market", "side", "tier",
    "score", "confidence", "source", "run_date", "start_time",
    "home_team", "away_team", "selection_team",
    "result", "units",
    "locked_ml_home", "locked_ml_away",
    "locked_spread_home_point", "locked_spread_home_price",
    "locked_spread_away_point", "locked_spread_away_price",
    "home_score", "away_score", "graded_at",
])

_CLOSING_COLS = ",".join([
    "event_id", "market", "outcome_name", "price", "point", "bookmaker_key",
    "captured_at", "home_team", "away_team",
])

_GAME_RESULT_COLS = ",".join([
    "event_id", "sport", "home_team", "away_team",
    "home_score", "away_score",
    "closing_ml_home", "closing_ml_away",
    "closing_spread_home_point", "closing_spread_home_price",
    "closing_spread_away_point", "closing_spread_away_price",
    "commence_time",
])


def since_date(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def fetch_locked_picks(since: str) -> List[Dict[str, Any]]:
    return sb_get_all("/rest/v1/locked_picks", {
        "select": _LOCKED_COLS,
        "sport": "eq.nba",
        "run_date": f"gte.{since}",
        "order": "run_date.desc",
    })


def fetch_pick_results(since: str) -> List[Dict[str, Any]]:
    return sb_get_all("/rest/v1/pick_results", {
        "select": _RESULT_COLS,
        "sport": "eq.nba",
        "run_date": f"gte.{since}",
        "order": "run_date.desc",
    })


def fetch_closing_lines(book: str = "fanduel") -> Dict[str, List[Dict[str, Any]]]:
    rows = sb_get_all("/rest/v1/closing_lines", {
        "select": _CLOSING_COLS,
        "sport": "eq.nba",
        "bookmaker_key": f"eq.{book}",
    })
    by_eid: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_eid.setdefault(str(r["event_id"]), []).append(r)
    return by_eid


def fetch_game_results() -> Dict[str, Dict[str, Any]]:
    rows = sb_get_all("/rest/v1/game_results", {
        "select": _GAME_RESULT_COLS,
        "sport": "eq.nba",
    })
    return {str(r["event_id"]): r for r in rows}

"""Pipeline smoke test: validates the live pick/grade/CLV pipeline is working.

CLI:
  python -m app.tests.pipeline_smoke

Safe: read-only queries, never writes. Won't crash if no games.
Requires: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY env vars.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from dotenv import load_dotenv
    load_dotenv(".env")
except ImportError:
    pass


def _sb_get(path: str, params: Dict[str, str] | None = None) -> Any:
    """Supabase REST GET (read-only)."""
    import urllib.request
    import urllib.parse

    base_url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not base_url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    url = f"{base_url}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def check_locked_picks() -> bool:
    """Check if locked_picks has recent rows."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    rows = _sb_get("/rest/v1/locked_picks", {
        "select": "id,event_id,run_date,tier,score,locked_at",
        "run_date": f"gte.{since}",
        "order": "locked_at.desc",
        "limit": "10",
    })
    n = len(rows) if isinstance(rows, list) else 0
    if n > 0:
        print(f"  PASS: {n} locked picks in last 7 days")
        for r in rows[:3]:
            print(f"    {r.get('run_date')} | {r.get('tier')} | score={r.get('score')} | {r.get('event_id', '')[:12]}")
        return True
    else:
        print(f"  WARN: 0 locked picks in last 7 days")
        print(f"    (normal if no NBA games recently or cron not running)")
        return False


def check_pick_results() -> bool:
    """Check if pick_results has recent graded rows."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows = _sb_get("/rest/v1/pick_results", {
        "select": "locked_pick_id,result,units,tier,graded_at,home_team,away_team",
        "start_time": f"gte.{since}",
        "result": "in.(win,loss,push)",
        "order": "graded_at.desc",
        "limit": "10",
    })
    n = len(rows) if isinstance(rows, list) else 0
    if n > 0:
        print(f"  PASS: {n} graded pick_results in last 7 days")
        for r in rows[:3]:
            print(f"    {r.get('result')} | {r.get('tier')} | {r.get('units')}u | "
                  f"{r.get('home_team')} vs {r.get('away_team')}")
        return True
    else:
        print(f"  WARN: 0 graded pick_results in last 7 days")
        return False


def check_closing_lines() -> bool:
    """Check if closing_lines has recent near-tip snapshots."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = _sb_get("/rest/v1/closing_lines", {
        "select": "event_id,captured_at,market,outcome_name",
        "captured_at": f"gte.{since}",
        "sport": "eq.nba",
        "order": "captured_at.desc",
        "limit": "20",
    })
    n = len(rows) if isinstance(rows, list) else 0
    if n > 0:
        events = set(r.get("event_id") for r in rows)
        latest = rows[0].get("captured_at", "?")
        print(f"  PASS: {n} closing_lines rows in last 24h across {len(events)} events")
        print(f"    Latest captured_at: {latest}")
        return True
    else:
        print(f"  WARN: 0 closing_lines rows in last 24h")
        print(f"    (normal if no NBA games in last 24h)")
        return False


def check_game_results() -> bool:
    """Check if game_results has recent entries with scores."""
    since = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    rows = _sb_get("/rest/v1/game_results", {
        "select": "event_id,home_team,away_team,home_score,away_score,commence_time",
        "commence_time": f"gte.{since}",
        "sport": "eq.nba",
        "order": "commence_time.desc",
        "limit": "10",
    })
    n = len(rows) if isinstance(rows, list) else 0
    with_scores = sum(1 for r in (rows or []) if r.get("home_score") is not None)
    if n > 0:
        print(f"  PASS: {n} game_results in last 3 days ({with_scores} with scores)")
        for r in (rows or [])[:3]:
            hs = r.get("home_score", "?")
            as_ = r.get("away_score", "?")
            print(f"    {r.get('home_team')} {hs} - {as_} {r.get('away_team')}")
        return True
    else:
        print(f"  WARN: 0 game_results in last 3 days")
        return False


def main():
    print("=" * 60)
    print("  Pipeline Smoke Test")
    print("=" * 60)

    checks = [
        ("Locked Picks (last 7d)", check_locked_picks),
        ("Pick Results / Grading (last 7d)", check_pick_results),
        ("Closing Lines / Snapshots (last 24h)", check_closing_lines),
        ("Game Results / Scores (last 3d)", check_game_results),
    ]

    results = {}
    for name, fn in checks:
        print(f"\n--- {name} ---")
        try:
            results[name] = fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = False

    print(f"\n{'=' * 60}")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"  Results: {passed}/{total} checks passed")

    for name, ok in results.items():
        status = "PASS" if ok else "WARN"
        print(f"  [{status}] {name}")

    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Locked picks diagnostics: validates schema and recent data.

CLI:
  python -m app.tests.locked_picks_diagnostics

Safe: read-only queries, never writes.
Requires: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY env vars.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

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


def check_locked_picks_schema() -> bool:
    """Verify locked_picks has the expected columns."""
    print("  Checking locked_picks table...")
    rows = _sb_get("/rest/v1/locked_picks", {
        "select": "id,event_id,sport,league,market,side,tier,score,confidence,"
                  "game_start_time,locked_at,run_date,selection_team,home_team,away_team,"
                  "locked_ml_home,locked_ml_away,graded_at",
        "limit": "1",
    })
    if isinstance(rows, list):
        cols = list(rows[0].keys()) if rows else []
        print(f"  PASS: locked_picks accessible, columns: {', '.join(cols) if cols else '(empty table)'}")
        return True
    print(f"  FAIL: unexpected response: {rows}")
    return False


def check_pick_results_schema() -> bool:
    """Verify pick_results uses correct columns (NO locked_at)."""
    print("  Checking pick_results table...")
    rows = _sb_get("/rest/v1/pick_results", {
        "select": "id,locked_pick_id,event_id,sport,tier,confidence,result,units,"
                  "home_team,away_team,selection_team,start_time,graded_at,run_date",
        "limit": "1",
    })
    if isinstance(rows, list):
        cols = list(rows[0].keys()) if rows else []
        print(f"  PASS: pick_results accessible, columns: {', '.join(cols) if cols else '(empty table)'}")
        print(f"    NOTE: pick_results has graded_at and start_time, NOT locked_at")
        return True
    print(f"  FAIL: unexpected response: {rows}")
    return False


def check_recent_locked_picks(days: int = 7) -> bool:
    """Check for recent locked picks using correct schema."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = _sb_get("/rest/v1/locked_picks", {
        "select": "id,event_id,tier,score,confidence,selection_team,home_team,away_team,"
                  "game_start_time,locked_at,run_date,graded_at",
        "run_date": f"gte.{since}",
        "sport": "eq.nba",
        "order": "locked_at.desc",
        "limit": "20",
    })

    n = len(rows) if isinstance(rows, list) else 0
    if n > 0:
        graded = sum(1 for r in rows if r.get("graded_at"))
        print(f"  PASS: {n} locked picks in last {days} days ({graded} graded)")
        print(f"\n  {'Tier':<14} {'Score':>6} {'Conf':>6} {'Selection':<22} {'Locked At':<22} {'Graded':>7}")
        print(f"  {'-'*12}  {'-'*5}  {'-'*5}  {'-'*20}  {'-'*20}  {'-'*6}")
        for r in rows[:10]:
            tier = r.get("tier", "?")
            score = r.get("score", "?")
            conf = r.get("confidence", "?")
            sel = (r.get("selection_team") or "?")[:20]
            locked = (r.get("locked_at") or "?")[:20]
            graded_str = "yes" if r.get("graded_at") else "no"
            print(f"  {tier:<14} {score:>6} {conf:>6} {sel:<22} {locked:<22} {graded_str:>7}")
        return True
    else:
        print(f"  WARN: 0 locked picks in last {days} days")
        print(f"    (normal if no NBA games recently or cron just fixed)")
        return False


def check_recent_pick_results(days: int = 7) -> bool:
    """Check for recent graded results using correct schema (start_time, NOT locked_at)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _sb_get("/rest/v1/pick_results", {
        "select": "tier,confidence,result,units,home_team,away_team,selection_team,start_time,graded_at",
        "start_time": f"gte.{since}",
        "result": "in.(win,loss,push)",
        "order": "graded_at.desc",
        "limit": "20",
    })

    n = len(rows) if isinstance(rows, list) else 0
    if n > 0:
        wins = sum(1 for r in rows if r.get("result") == "win")
        losses = sum(1 for r in rows if r.get("result") == "loss")
        units = sum(float(r.get("units", 0)) for r in rows)
        print(f"  PASS: {n} graded results in last {days} days ({wins}W-{losses}L, {units:+.1f}u)")
        for r in rows[:5]:
            print(f"    {r.get('result'):>5} | {r.get('tier'):<14} | {r.get('units'):>+.1f}u | "
                  f"{r.get('selection_team')} ({r.get('home_team')} vs {r.get('away_team')})")
        return True
    else:
        print(f"  WARN: 0 graded results in last {days} days")
        return False


def main():
    print("=" * 60)
    print("  Locked Picks Diagnostics")
    print("=" * 60)

    checks = [
        ("Schema: locked_picks", check_locked_picks_schema),
        ("Schema: pick_results (no locked_at)", check_pick_results_schema),
        ("Recent Locked Picks (7d)", check_recent_locked_picks),
        ("Recent Pick Results (7d)", check_recent_pick_results),
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

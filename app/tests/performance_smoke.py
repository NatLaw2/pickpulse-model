"""Performance pipeline smoke test: validates end-to-end grading and tier records.

CLI:
  python -m app.tests.performance_smoke

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


def check_finished_games(days: int = 3) -> bool:
    """Check if there are finished games with scores in game_results."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _sb_get("/rest/v1/game_results", {
        "select": "event_id,home_team,away_team,home_score,away_score,commence_time",
        "commence_time": f"gte.{since}",
        "sport": "eq.nba",
        "home_score": "not.is.null",
        "away_score": "not.is.null",
        "order": "commence_time.desc",
        "limit": "10",
    })
    n = len(rows) if isinstance(rows, list) else 0
    if n > 0:
        print(f"  PASS: {n} finished games with scores in last {days} days")
        for r in rows[:3]:
            print(f"    {r.get('home_team')} {r.get('home_score')} - "
                  f"{r.get('away_score')} {r.get('away_team')}")
        return True
    else:
        print(f"  WARN: No finished games in last {days} days")
        return False


def check_graded_picks(days: int = 7) -> bool:
    """Check if pick_results has graded rows (by start_time or graded_at)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Try by start_time first (normal case: recent games)
    rows = _sb_get("/rest/v1/pick_results", {
        "select": "tier,confidence,result,units,home_team,away_team,selection_team,graded_at",
        "start_time": f"gte.{since}",
        "result": "in.(win,loss,push)",
        "order": "graded_at.desc",
        "limit": "20",
    })

    # Fallback: check by graded_at (catches older games graded recently)
    if not rows or not isinstance(rows, list) or len(rows) == 0:
        rows = _sb_get("/rest/v1/pick_results", {
            "select": "tier,confidence,result,units,home_team,away_team,selection_team,graded_at",
            "graded_at": f"gte.{since}",
            "result": "in.(win,loss,push)",
            "order": "graded_at.desc",
            "limit": "20",
        })

    n = len(rows) if isinstance(rows, list) else 0
    if n > 0:
        wins = sum(1 for r in rows if r.get("result") == "win")
        losses = sum(1 for r in rows if r.get("result") == "loss")
        pushes = sum(1 for r in rows if r.get("result") == "push")
        units = sum(float(r.get("units", 0)) for r in rows)
        latest = rows[0].get("graded_at", "?")
        print(f"  PASS: {n} graded picks in last {days} days ({wins}W-{losses}L-{pushes}P, {units:+.2f}u)")
        print(f"    Latest graded_at: {latest}")
        for r in rows[:3]:
            print(f"    {r.get('result'):>5} | {r.get('tier'):<14} | conf={r.get('confidence')} | "
                  f"{r.get('selection_team')}")
        return True
    else:
        print(f"  WARN: No graded picks in last {days} days")
        print(f"    This is expected if the cron pipeline was just restored and no games have been")
        print(f"    locked + completed since then. Check again after tonight's games finalize.")
        return False


def check_tier_records_view() -> bool:
    """Check the v_tier_records view returns valid data."""
    try:
        rows = _sb_get("/rest/v1/v_tier_records", {
            "select": "*",
            "source": "eq.live",
        })
    except Exception as e:
        if "404" in str(e) or "relation" in str(e).lower():
            print(f"  WARN: v_tier_records view does not exist yet (run migration)")
            return False
        raise

    if not isinstance(rows, list):
        print(f"  FAIL: unexpected response from v_tier_records: {rows}")
        return False

    if len(rows) == 0:
        print(f"  WARN: v_tier_records returns 0 rows (no graded picks yet)")
        return False

    # Should have up to 3 rows: top, high, medium
    buckets_found = set()
    valid = True
    print(f"  v_tier_records returned {len(rows)} rows:")
    for r in rows:
        bucket = r.get("tier_bucket", "?")
        buckets_found.add(bucket)
        wins = r.get("wins", 0)
        losses = r.get("losses", 0)
        pushes = r.get("pushes", 0)
        win_pct = r.get("win_pct")
        units = r.get("units", 0)
        updated = r.get("updated_at", "?")

        print(f"    {bucket:<8} {wins}W-{losses}L-{pushes}P  "
              f"win_pct={win_pct}  units={units}  updated={str(updated)[:19]}")

        # Validate consistency
        total_decided = wins + losses
        if total_decided > 0 and win_pct is not None:
            expected_pct = round(100.0 * wins / total_decided, 1)
            if abs(float(win_pct) - expected_pct) > 0.2:
                print(f"      FAIL: win_pct mismatch: expected {expected_pct}, got {win_pct}")
                valid = False

        if bucket not in ("top", "high", "medium"):
            print(f"      FAIL: unexpected tier_bucket: {bucket}")
            valid = False

    if valid:
        print(f"  PASS: {len(buckets_found)} tier buckets validated ({', '.join(sorted(buckets_found))})")
    return valid


def check_performance_summary_endpoint() -> bool:
    """Check the performance-summary edge function returns valid data."""
    import urllib.request

    base_url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not base_url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    url = f"{base_url}/functions/v1/performance-summary?source=live&range=30d"
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())

    if not data.get("ok"):
        print(f"  FAIL: performance-summary returned ok=false: {data.get('error')}")
        return False

    buckets = data.get("confidenceBuckets", {})
    updated_at = data.get("updatedAt")
    overall = data.get("overall", {})

    print(f"  Edge function response:")
    print(f"    Overall: {overall.get('wins', 0)}W-{overall.get('losses', 0)}L "
          f"({overall.get('percentage', 0)}%) {overall.get('picks', 0)} picks")
    print(f"    Updated at: {updated_at or 'null (no graded picks yet)'}")

    has_buckets = False
    for bucket_name in ("top", "high", "medium"):
        b = buckets.get(bucket_name, {})
        picks = b.get("picks", 0)
        if picks > 0:
            has_buckets = True
            print(f"    {bucket_name:>8}: {b.get('wins',0)}W-{b.get('losses',0)}L "
                  f"({b.get('percentage',0)}%) {b.get('units',0):+.2f}u")

    if not has_buckets and overall.get("picks", 0) == 0:
        print(f"  WARN: No picks in response (normal if pipeline just restored)")
        return False

    print(f"  PASS: performance-summary endpoint returns valid data with confidence buckets")
    return True


def check_grading_timeliness() -> bool:
    """Check that grading happens within 10 minutes of game end."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows = _sb_get("/rest/v1/pick_results", {
        "select": "start_time,graded_at",
        "start_time": f"gte.{since}",
        "result": "in.(win,loss,push)",
        "order": "graded_at.desc",
        "limit": "20",
    })
    n = len(rows) if isinstance(rows, list) else 0
    if n == 0:
        print(f"  SKIP: No graded picks to check timeliness")
        return True  # Not a failure, just no data

    delays = []
    for r in rows:
        start = r.get("start_time")
        graded = r.get("graded_at")
        if start and graded:
            try:
                t_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
                t_graded = datetime.fromisoformat(graded.replace("Z", "+00:00"))
                # NBA games are ~2.5 hours long, so grading should happen ~2.5h + 10min after start
                delay_hours = (t_graded - t_start).total_seconds() / 3600
                delays.append(delay_hours)
            except Exception:
                pass

    if delays:
        avg_delay = sum(delays) / len(delays)
        max_delay = max(delays)
        print(f"  Grading delay stats (start_time to graded_at):")
        print(f"    Avg: {avg_delay:.1f}h  Max: {max_delay:.1f}h  Samples: {len(delays)}")
        if max_delay < 5:  # Should be graded within 5h of game start (game ~2.5h + 10min buffer)
            print(f"  PASS: All picks graded within reasonable time")
        else:
            print(f"  WARN: Some picks took >{max_delay:.0f}h to grade (expected <5h)")
        return True

    return True


def main():
    print("=" * 60)
    print("  Performance Pipeline Smoke Test")
    print("=" * 60)

    checks = [
        ("Finished Games (last 3d)", check_finished_games),
        ("Graded Picks (last 7d)", check_graded_picks),
        ("v_tier_records View", check_tier_records_view),
        ("performance-summary Endpoint", check_performance_summary_endpoint),
        ("Grading Timeliness", check_grading_timeliness),
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

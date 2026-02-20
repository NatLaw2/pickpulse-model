"""CLV snapshot diagnostics: checks closing_lines density and lock/close gap.

CLI:
  python -m app.tests.clv_diagnostics

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


def check_snapshot_density(days: int = 7) -> None:
    """Check how many snapshots per event exist within T-90 window."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Get recent closing_lines grouped by event
    rows = _sb_get("/rest/v1/closing_lines", {
        "select": "event_id,captured_at,commence_time,market",
        "captured_at": f"gte.{since}",
        "sport": "eq.nba",
        "market": "eq.h2h",
        "order": "commence_time.desc",
        "limit": "2000",
    })

    if not rows:
        print("  No closing_lines rows found in window")
        return

    # Group by event
    by_event: Dict[str, List[Dict]] = {}
    for r in rows:
        eid = r.get("event_id", "")
        by_event.setdefault(eid, []).append(r)

    print(f"  Events with snapshots: {len(by_event)}")
    print(f"  Total h2h snapshot rows: {len(rows)}")

    # Per-event stats
    single_snap_events = 0
    multi_snap_events = 0
    total_snaps = 0

    print(f"\n  {'Event ID':<16} {'Snaps':>6} {'First Snap':<22} {'Last Snap':<22} {'Tip Time':<22} {'Gap (min)':>10}")
    print(f"  {'-'*14}  {'-'*5}  {'-'*20}  {'-'*20}  {'-'*20}  {'-'*9}")

    for eid, snaps in sorted(by_event.items(), key=lambda x: x[1][-1].get("commence_time", ""), reverse=True)[:20]:
        n = len(snaps)
        total_snaps += n
        captured_times = sorted(set(s["captured_at"] for s in snaps if s.get("captured_at")))
        first = captured_times[0] if captured_times else "?"
        last = captured_times[-1] if captured_times else "?"
        tip = snaps[0].get("commence_time", "?")

        # Gap between first and last snap in minutes
        gap_min = "—"
        if len(captured_times) >= 2:
            try:
                t0 = datetime.fromisoformat(captured_times[0].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(captured_times[-1].replace("Z", "+00:00"))
                gap_min = f"{(t1 - t0).total_seconds() / 60:.0f}"
            except Exception:
                pass

        unique_times = len(captured_times)
        if unique_times <= 1:
            single_snap_events += 1
        else:
            multi_snap_events += 1

        print(f"  {eid[:14]:<16} {unique_times:>6} {first[:20]:<22} {last[:20]:<22} {str(tip)[:20]:<22} {gap_min:>10}")

    print(f"\n  Summary:")
    print(f"    Single-snapshot events: {single_snap_events}")
    print(f"    Multi-snapshot events:  {multi_snap_events}")
    print(f"    Avg snaps/event: {total_snaps / max(len(by_event), 1):.1f}")

    if multi_snap_events == 0:
        print(f"\n  WARNING: All events have only 1 snapshot.")
        print(f"    CLV will be 0.0 until snap_odds_nba_near_tip creates multiple near-tip snapshots.")
        print(f"    Check: SELECT * FROM cron.job WHERE jobname = 'snap-odds-nba-2min';")
    else:
        pct = multi_snap_events / max(single_snap_events + multi_snap_events, 1) * 100
        print(f"\n  {pct:.0f}% of events have multiple snapshots — CLV computation should work.")


def check_lock_vs_close(days: int = 7) -> None:
    """Check if locked picks have distinct lock and close snapshots."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    locked = _sb_get("/rest/v1/locked_picks", {
        "select": "event_id,locked_at,game_start_time,locked_ml_home",
        "run_date": f"gte.{since}",
        "sport": "eq.nba",
        "order": "locked_at.desc",
        "limit": "50",
    })

    if not locked:
        print("  No locked picks in window — nothing to check")
        return

    print(f"  Locked picks: {len(locked)}")

    with_odds = sum(1 for lp in locked if lp.get("locked_ml_home") is not None)
    print(f"  With locked odds: {with_odds}/{len(locked)}")

    if with_odds == 0:
        print(f"\n  WARNING: No locked picks have odds captured.")
        print(f"    Check closing_lines has snapshots before T-15 for these events.")


def main():
    print("=" * 60)
    print("  CLV Snapshot Diagnostics")
    print("=" * 60)

    print("\n--- Snapshot Density (last 7 days) ---")
    try:
        check_snapshot_density(days=7)
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n--- Lock vs Close Gap ---")
    try:
        check_lock_vs_close(days=7)
    except Exception as e:
        print(f"  ERROR: {e}")

    print(f"\n{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

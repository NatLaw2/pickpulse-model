"""Backfill clv_features table from existing locked_picks + closing_lines.

CLI:
  python -m app.clv_timing.backfill --days 365
  python -m app.clv_timing.backfill --days 365 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

from dotenv import load_dotenv
load_dotenv()

from app.agents._supabase import (
    fetch_locked_picks,
    fetch_closing_lines,
    since_date,
    sb_get,
    _get_sb_config,
    _headers,
)
from .features import compute_batch

import requests


def _upsert_features(features: List[Dict[str, Any]], dry_run: bool = False) -> int:
    """Upsert computed features to clv_features table."""
    rows = []
    for f in features:
        if f.get("clv_prob") is None and f.get("p_lock") is None:
            continue
        rows.append({
            "event_id": f.get("event_id"),
            "locked_at": f.get("locked_at"),
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "side": f.get("side"),
            "p_lock": f.get("p_lock"),
            "p_close": f.get("p_close"),
            "clv_prob": f.get("clv_prob"),
            "steam_5m": f.get("steam_5m"),
            "steam_15m": f.get("steam_15m"),
            "velocity_30m": f.get("velocity_30m"),
            "range_30m": f.get("range_30m"),
            "std_30m": f.get("std_30m"),
            "snap_gap_lock_sec": f.get("snap_gap_lock_sec"),
            "snap_gap_close_sec": f.get("snap_gap_close_sec"),
            "lock_snap_ts": f.get("lock_snap_ts"),
            "close_snap_ts": f.get("close_snap_ts"),
        })

    if dry_run:
        print(f"[backfill] DRY RUN: would upsert {len(rows)} rows")
        return len(rows)

    if not rows:
        return 0

    base_url, key = _get_sb_config()
    headers = _headers()
    headers["Prefer"] = "resolution=merge-duplicates"

    # Batch in chunks of 500
    total = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i+500]
        url = f"{base_url.rstrip('/')}/rest/v1/clv_features"
        r = requests.post(url, headers=headers, json=batch, timeout=60)
        if r.ok:
            total += len(batch)
        else:
            print(f"[backfill] Upsert error at batch {i}: {r.status_code} {r.text[:200]}")

    return total


def main():
    parser = argparse.ArgumentParser(description="Backfill clv_features table")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    since = since_date(args.days)
    print(f"[backfill] Fetching locked picks since {since}...")
    picks = fetch_locked_picks(since)
    print(f"[backfill] Locked picks: {len(picks)}")

    print("[backfill] Fetching closing lines...")
    closing = fetch_closing_lines()
    print(f"[backfill] Events: {len(closing)}")

    print("[backfill] Computing timing features...")
    features, coverage = compute_batch(picks, closing)
    print(f"[backfill] Coverage: {coverage}")

    n = _upsert_features(features, dry_run=args.dry_run)
    print(f"[backfill] Upserted {n} rows to clv_features")


if __name__ == "__main__":
    main()

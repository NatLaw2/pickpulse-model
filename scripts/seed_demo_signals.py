#!/usr/bin/env python3
"""Seed realistic churn signals for HubSpot demo accounts.

Populates account_signals_daily with deterministic, cohort-based signal values
so that "Rescore All" produces a realistic high/medium/low risk distribution.

This script is intended for DEMO ENVIRONMENTS ONLY. It writes synthetic values
to the database. Real engagement data synced on a later date will naturally
supersede these rows because latest_signals() picks the most recent signal_date.

Usage:
    python scripts/seed_demo_signals.py --tenant-id <uuid>
    python scripts/seed_demo_signals.py --tenant-id <uuid> --dry-run
    python scripts/seed_demo_signals.py --tenant-id <uuid> --source hubspot
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import date
from typing import Any, Dict, List, Tuple

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


# ---------------------------------------------------------------------------
# Cohort signal templates
# High / Medium / Low base values, with per-account jitter applied on top.
# ---------------------------------------------------------------------------

_COHORTS: List[Dict[str, Any]] = [
    # High risk: disengaged, frustrated, renewal imminent, auto-renew off
    {
        "label": "HIGH",
        "days_since_last_login": 80,
        "monthly_logins": 1,
        "nps_score": 3.0,
        "support_tickets": 6,
        "days_until_renewal": 22,
        "auto_renew_flag": 0,
        "seats": 2,
        "arr_range": (18_000, 60_000),
    },
    # Medium risk: infrequent use, passive NPS, renewal in mid-window
    {
        "label": "MEDIUM",
        "days_since_last_login": 38,
        "monthly_logins": 4,
        "nps_score": 6.5,
        "support_tickets": 2,
        "days_until_renewal": 65,
        "auto_renew_flag": 1,
        "seats": 5,
        "arr_range": (36_000, 120_000),
    },
    # Low risk: engaged, satisfied, long runway, auto-renew on
    {
        "label": "LOW",
        "days_since_last_login": 3,
        "monthly_logins": 18,
        "nps_score": 9.0,
        "support_tickets": 0,
        "days_until_renewal": 210,
        "auto_renew_flag": 1,
        "seats": 12,
        "arr_range": (60_000, 240_000),
    },
]

# Target distribution: (high_count, medium_count, low_count)
# Applied proportionally when account count != 20.
_TARGET_RATIOS = (5, 8, 7)  # out of 20


def _cohort_index(rank: int, total: int) -> int:
    """Map an account's sorted rank to a cohort index (0=high, 1=medium, 2=low).

    Distributes accounts proportionally based on _TARGET_RATIOS regardless
    of the actual total account count.
    """
    high_n = max(1, round(_TARGET_RATIOS[0] * total / 20))
    medium_n = max(1, round(_TARGET_RATIOS[1] * total / 20))
    # low_n = remainder

    if rank < high_n:
        return 0
    if rank < high_n + medium_n:
        return 1
    return 2


def _jitter(external_id: str, field: str, scale: float) -> float:
    """Deterministic jitter in [-scale, +scale] derived from account id + field name."""
    h = hashlib.sha256(f"{external_id}:{field}".encode()).digest()
    # Use first two bytes → value in [0, 65535]
    raw = int.from_bytes(h[:2], "big")
    return (raw / 65535.0 - 0.5) * 2 * scale  # maps to [-scale, +scale]


def _arr_for_account(external_id: str, arr_range: Tuple[int, int]) -> float:
    """Pick a deterministic ARR within the cohort range."""
    lo, hi = arr_range
    h = hashlib.sha256(f"{external_id}:arr".encode()).digest()
    raw = int.from_bytes(h[:4], "big")
    return round(lo + (raw / 0xFFFFFFFF) * (hi - lo), -2)  # round to nearest $100


def build_signals(external_id: str, cohort: Dict[str, Any], today: str) -> Dict[str, Any]:
    """Return a flat signal dict for one account."""
    def ji(field: str, scale: float) -> int:
        return max(0, round(cohort[field] + _jitter(external_id, field, scale)))

    def jf(field: str, scale: float, decimals: int = 1) -> float:
        raw = cohort[field] + _jitter(external_id, field, scale)
        return round(max(0.0, raw), decimals)

    return {
        "external_id": external_id,
        "signal_date": today,
        "days_since_last_login": ji("days_since_last_login", 8),
        "monthly_logins": ji("monthly_logins", 2),
        "nps_score": round(min(10.0, jf("nps_score", 0.8)), 1),
        "support_tickets": ji("support_tickets", 1),
        "days_until_renewal": ji("days_until_renewal", 10),
        "auto_renew_flag": cohort["auto_renew_flag"],  # boolean — no jitter
        "seats": ji("seats", 2),
    }


def seed(tenant_id: str, source: str = "hubspot", dry_run: bool = False) -> None:
    from app.storage import repo
    from app.storage.db import get_client

    today = date.today().isoformat()

    # 1. Pull synced accounts for this tenant (filtered by source)
    accounts = repo.list_accounts(source=source, limit=50_000, tenant_id=tenant_id)
    if not accounts:
        print(f"No accounts found for tenant={tenant_id} source={source}")
        return

    # Sort deterministically by external_id so cohort assignment is stable
    accounts_sorted = sorted(accounts, key=lambda a: a["external_id"])
    total = len(accounts_sorted)
    print(f"Found {total} accounts (source={source}, tenant={tenant_id[:8]}…)")

    # 2. Build signal rows and ARR updates
    signal_rows: List[Dict[str, Any]] = []
    arr_updates: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, str]] = []

    for rank, acct in enumerate(accounts_sorted):
        ext_id = acct["external_id"]
        cohort_idx = _cohort_index(rank, total)
        cohort = _COHORTS[cohort_idx]
        sigs = build_signals(ext_id, cohort, today)

        # Resolve the internal UUID (needed for direct DB write below)
        account_uuid = acct.get("id")

        # Build account_signals_daily rows (one per signal key)
        numeric_keys = [
            "days_since_last_login", "monthly_logins", "nps_score",
            "support_tickets", "days_until_renewal", "auto_renew_flag", "seats",
        ]
        for key in numeric_keys:
            val = sigs[key]
            signal_rows.append({
                "tenant_id": tenant_id,
                "account_id": account_uuid,
                "signal_date": today,
                "signal_key": key,
                "signal_value": float(val),
                "signal_text": None,
            })

        # ARR: only seed if currently null/zero
        current_arr = acct.get("arr")
        if not current_arr:
            seeded_arr = _arr_for_account(ext_id, cohort["arr_range"])
            arr_updates.append({"id": account_uuid, "arr": seeded_arr})
        else:
            seeded_arr = current_arr

        summary_rows.append({
            "name": acct.get("name") or ext_id,
            "cohort": cohort["label"],
            "days_inactive": str(sigs["days_since_last_login"]),
            "nps": str(sigs["nps_score"]),
            "tickets": str(sigs["support_tickets"]),
            "renewal_days": str(sigs["days_until_renewal"]),
            "auto_renew": "YES" if sigs["auto_renew_flag"] else "NO",
            "arr": f"${seeded_arr:,.0f}",
        })

    # 3. Print summary table
    print(f"\n{'Account':<30} {'Cohort':<8} {'Inactive':>8} {'NPS':>5} "
          f"{'Tickets':>8} {'Renewal':>8} {'AutoRenew':>10} {'ARR':>12}")
    print("-" * 95)
    for r in summary_rows:
        print(f"{r['name']:<30} {r['cohort']:<8} {r['days_inactive']:>8} "
              f"{r['nps']:>5} {r['tickets']:>8} {r['renewal_days']:>8} "
              f"{r['auto_renew']:>10} {r['arr']:>12}")

    high_n = sum(1 for r in summary_rows if r["cohort"] == "HIGH")
    med_n = sum(1 for r in summary_rows if r["cohort"] == "MEDIUM")
    low_n = sum(1 for r in summary_rows if r["cohort"] == "LOW")
    arr_seed_n = len(arr_updates)
    print(f"\nDistribution: {high_n} HIGH / {med_n} MEDIUM / {low_n} LOW")
    print(f"Signal rows to upsert: {len(signal_rows)}")
    print(f"ARR values to seed: {arr_seed_n} accounts (skipping accounts that already have ARR)")

    if dry_run:
        print("\n[DRY RUN] No changes written to database.")
        return

    # 4. Upsert signal rows
    sb = get_client()
    res = sb.table("account_signals_daily").upsert(
        signal_rows,
        on_conflict="tenant_id,account_id,signal_date,signal_key",
    ).execute()
    inserted = len(res.data) if res.data else 0
    print(f"\nUpserted {inserted} signal rows into account_signals_daily.")

    # 5. Update ARR on accounts table (only for accounts with no existing ARR)
    if arr_updates:
        for upd in arr_updates:
            sb.table("accounts").update({"arr": upd["arr"]}).eq("id", upd["id"]).execute()
        print(f"Seeded ARR for {len(arr_updates)} accounts.")

    print("\nDone. Run 'Rescore All' in the console to generate updated churn scores.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed demo churn signals for HubSpot accounts."
    )
    parser.add_argument(
        "--tenant-id",
        required=True,
        help="Supabase tenant UUID (the 'sub' claim from your JWT)",
    )
    parser.add_argument(
        "--source",
        default="hubspot",
        help="Account source filter (default: hubspot)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be seeded without writing to the database",
    )
    args = parser.parse_args()

    seed(tenant_id=args.tenant_id, source=args.source, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

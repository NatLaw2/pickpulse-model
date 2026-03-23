"""Auto-seed demo signals for CRM accounts when none exist.

Called automatically before scoring in DEMO_MODE so that "Rescore All"
produces a realistic risk distribution without requiring a manual CLI run
of scripts/seed_demo_signals.py.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from .storage import repo
from .storage.db import get_client

logger = logging.getLogger("pickpulse.demo_seed")

# ---------------------------------------------------------------------------
# Cohort templates (mirrors scripts/seed_demo_signals.py)
# ---------------------------------------------------------------------------
_COHORTS: List[Dict[str, Any]] = [
    {  # High risk
        "days_since_last_login": 80, "monthly_logins": 1, "nps_score": 3.0,
        "support_tickets": 6, "days_until_renewal": 22, "auto_renew_flag": 0, "seats": 2,
    },
    {  # Medium risk
        "days_since_last_login": 38, "monthly_logins": 4, "nps_score": 6.5,
        "support_tickets": 2, "days_until_renewal": 65, "auto_renew_flag": 1, "seats": 5,
    },
    {  # Low risk
        "days_since_last_login": 3, "monthly_logins": 18, "nps_score": 9.0,
        "support_tickets": 0, "days_until_renewal": 210, "auto_renew_flag": 1, "seats": 12,
    },
]
_TARGET_RATIOS = (5, 8, 7)  # high / medium / low out of 20


def _cohort_index(rank: int, total: int) -> int:
    high_n = max(1, round(_TARGET_RATIOS[0] * total / 20))
    medium_n = max(1, round(_TARGET_RATIOS[1] * total / 20))
    if rank < high_n:
        return 0
    if rank < high_n + medium_n:
        return 1
    return 2


def _jitter(external_id: str, field: str, scale: float) -> float:
    h = hashlib.sha256(f"{external_id}:{field}".encode()).digest()
    raw = int.from_bytes(h[:2], "big")
    return (raw / 65535.0 - 0.5) * 2 * scale


def _build_signal_rows(
    accounts: List[Dict[str, Any]],
    tenant_id: str,
    today: str,
) -> List[Dict[str, Any]]:
    accounts_sorted = sorted(accounts, key=lambda a: a.get("external_id", ""))
    total = len(accounts_sorted)
    numeric_keys = [
        "days_since_last_login", "monthly_logins", "nps_score",
        "support_tickets", "days_until_renewal", "auto_renew_flag", "seats",
    ]
    rows = []
    skipped_no_id = 0
    for rank, acct in enumerate(accounts_sorted):
        ext_id = acct.get("external_id", "")
        cohort = _COHORTS[_cohort_index(rank, total)]
        account_uuid = acct.get("id")
        if not account_uuid:
            skipped_no_id += 1
            continue
        for key in numeric_keys:
            base = cohort[key]
            if key == "auto_renew_flag":
                val = float(base)
            elif key == "nps_score":
                raw = base + _jitter(ext_id, key, 0.8)
                val = float(round(min(10.0, max(0.0, raw)), 1))
            else:
                raw = base + _jitter(ext_id, key, max(1, base * 0.1))
                val = float(max(0, round(raw)))
            rows.append({
                "tenant_id": tenant_id,
                "account_id": account_uuid,
                "signal_date": today,
                "signal_key": key,
                "signal_value": val,
                "signal_text": None,
            })
    if skipped_no_id:
        print(f"[demo_seed] WARNING: {skipped_no_id}/{total} accounts had no 'id' field — skipped")
    return rows


def auto_seed_if_needed(tenant_id: str, source: Optional[str] = None) -> bool:
    """Seed demo signals if none exist for this tenant. Returns True if seeding occurred."""
    # TEMPORARY DIAGNOSTIC — print() used to guarantee visibility in Render logs
    print(f"[demo_seed] auto_seed_if_needed called — tenant={tenant_id[:8]}… source={source}")

    try:
        existing = repo.bulk_latest_signals(tenant_id)
        print(f"[demo_seed] existing signals count: {len(existing)}")
        if existing:
            print("[demo_seed] signals already present — skipping seed")
            return False

        accounts = repo.list_accounts(source=source, limit=50_000, tenant_id=tenant_id)
        print(f"[demo_seed] accounts found: {len(accounts)}")
        if not accounts:
            print(f"[demo_seed] no accounts for tenant {tenant_id[:8]} (source={source}) — cannot seed")
            return False

        # Log first account to confirm id/external_id fields are present
        sample = accounts[0]
        print(f"[demo_seed] sample account keys: {list(sample.keys())}")
        print(f"[demo_seed] sample account id={sample.get('id')!r} external_id={sample.get('external_id')!r}")

        today = date.today().isoformat()
        signal_rows = _build_signal_rows(accounts, tenant_id, today)
        print(f"[demo_seed] signal rows prepared: {len(signal_rows)}")
        if not signal_rows:
            print("[demo_seed] ERROR: no signal rows built — all accounts may be missing 'id' field")
            return False

        sb = get_client()
        print(f"[demo_seed] attempting upsert of {len(signal_rows)} rows into account_signals_daily")
        res = sb.table("account_signals_daily").upsert(
            signal_rows,
            on_conflict="tenant_id,account_id,signal_date,signal_key",
        ).execute()
        inserted = len(res.data) if res.data else 0
        print(f"[demo_seed] upsert complete — rows returned by DB: {inserted}")
        if inserted == 0:
            print("[demo_seed] WARNING: upsert returned 0 rows — possible RLS block or schema mismatch")
        else:
            print(f"[demo_seed] SUCCESS: seeded {inserted} signal rows for {len(accounts)} accounts")
        return inserted > 0

    except Exception as exc:
        import traceback
        print(f"[demo_seed] EXCEPTION in auto_seed_if_needed: {exc}")
        print(traceback.format_exc())
        logger.warning("demo_seed: exception during seeding: %s", exc)
        return False

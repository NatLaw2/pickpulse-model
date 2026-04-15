"""Auto-seed demo signals for CRM accounts when none exist.

Called automatically before scoring in DEMO_MODE so that "Rescore All"
produces a realistic risk distribution without requiring a manual CLI run
of scripts/seed_demo_signals.py.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
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


# The minimal set of signal keys that must be present for demo scoring to
# produce a realistic risk distribution.  Partial HubSpot-synced rows
# (e.g. support_tickets=0, extra=null) must NOT block re-seeding.
_REQUIRED_DEMO_KEYS = frozenset({
    "days_since_last_login", "monthly_logins", "nps_score",
    "days_until_renewal", "auto_renew_flag",
})


def _demo_signals_complete(
    signals_by_account: Dict[str, Dict[str, Any]],
    required: frozenset,
    min_fraction: float = 0.5,
) -> bool:
    """Return True only when required keys are present for ≥ min_fraction of accounts."""
    if not signals_by_account:
        return False
    fully_seeded = sum(
        1 for sigs in signals_by_account.values()
        if required.issubset(sigs.keys())
    )
    return (fully_seeded / len(signals_by_account)) >= min_fraction


_MIN_DEMO_CHURNED = 10   # minimum churned outcomes required to pass sufficiency gate
_MIN_DEMO_RETAINED = 10  # minimum retained outcomes


def _seed_outcomes_if_needed(
    accounts: List[Dict[str, Any]],
    tenant_id: str,
) -> int:
    """Seed account_outcomes for demo mode so the CRM training sufficiency gate passes.

    Uses the same cohort ordering as signals: high-risk accounts (first 25%)
    become churned=1, the rest become retained=0.  Idempotent — upserts on
    (tenant_id, account_id) so re-running is safe.

    Guarantees at least _MIN_DEMO_CHURNED churned rows regardless of cohort math,
    so the sufficiency gate always has enough labeled examples.
    """
    try:
        sb = get_client()

        # Check for any existing outcomes for these accounts (any source)
        # to avoid overwriting user-created manual labels.
        account_ids = [a["id"] for a in accounts if a.get("id")]
        if not account_ids:
            print("[demo_seed] no accounts with valid ids — cannot seed outcomes")
            return 0

        existing_res = (
            sb.table("account_outcomes")
            .select("account_id")
            .eq("tenant_id", tenant_id)
            .in_("account_id", account_ids)
            .execute()
        )
        already_seeded_ids = {r["account_id"] for r in (existing_res.data or [])}

        accounts_sorted = sorted(accounts, key=lambda a: a.get("external_id", ""))
        total = len(accounts_sorted)

        # Ensure at least _MIN_DEMO_CHURNED accounts are labeled churned
        # regardless of cohort ratio (cohort math fails with <40 accounts).
        high_n = max(_MIN_DEMO_CHURNED, round(_TARGET_RATIOS[0] * total / 20))
        # Cap at half the total to always leave some retained examples.
        # check_data_sufficiency adapts its threshold in demo_mode, so we don't
        # need to guarantee _MIN_DEMO_RETAINED — just avoid all-churned datasets.
        high_n = min(high_n, max(1, total // 2))

        rows = []
        today = date.today().isoformat()
        now_ts = datetime.now(timezone.utc).isoformat()
        for rank, acct in enumerate(accounts_sorted):
            account_uuid = acct.get("id")
            if not account_uuid or account_uuid in already_seeded_ids:
                continue
            outcome_type = "churned" if rank < high_n else "renewed"
            rows.append({
                "tenant_id": tenant_id,
                "account_id": account_uuid,
                "outcome_type": outcome_type,
                "effective_date": today,
                "source": "system",
                "notes": "Auto-seeded for demo",
                "recorded_at": now_ts,
            })

        if not rows:
            print("[demo_seed] outcomes already seeded — skipping")
            return 0

        print(f"[demo_seed] seeding {len(rows)} outcome rows ({high_n} churned target, {total} total accounts)")
        res = sb.table("account_outcomes").upsert(
            rows,
            on_conflict="tenant_id,account_id",
        ).execute()
        inserted = len(res.data) if res.data else 0
        print(f"[demo_seed] outcome upsert complete — rows returned: {inserted}")
        if inserted == 0:
            print("[demo_seed] WARNING: upsert returned 0 rows — possible RLS block, schema mismatch, or all already seeded")
        return inserted

    except Exception as exc:
        import traceback
        print(f"[demo_seed] outcome seed EXCEPTION: {exc}")
        print(traceback.format_exc())
        return -1  # distinguish failure from "already seeded" (0)


def auto_seed_if_needed(tenant_id: str, source: Optional[str] = None) -> bool:
    """Seed demo signals unless required keys are already present for this tenant."""
    print(f"[demo_seed] auto_seed_if_needed called — tenant={tenant_id[:8]}… source={source}")

    try:
        existing = repo.bulk_latest_signals(tenant_id)
        print(f"[demo_seed] existing signals count: {len(existing)}")

        if _demo_signals_complete(existing, _REQUIRED_DEMO_KEYS):
            print("[demo_seed] required demo keys present — skipping signal seed")
            # Signals are complete, but outcomes may still be missing.
            # Always ensure outcome labels exist so the CRM sufficiency gate passes.
            accounts = repo.list_accounts(source=source, limit=50_000, tenant_id=tenant_id)
            if accounts:
                _seed_outcomes_if_needed(accounts, tenant_id)
            return False

        # Signals exist but are partial/legacy — report and re-seed
        if existing:
            missing_count = sum(
                1 for sigs in existing.values()
                if not _REQUIRED_DEMO_KEYS.issubset(sigs.keys())
            )
            print(f"[demo_seed] {missing_count}/{len(existing)} accounts missing required demo keys — seeding now")

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

        # Seed outcome labels so the CRM training sufficiency gate passes
        _seed_outcomes_if_needed(accounts, tenant_id)

        return inserted > 0

    except Exception as exc:
        import traceback
        print(f"[demo_seed] EXCEPTION in auto_seed_if_needed: {exc}")
        print(traceback.format_exc())
        logger.warning("demo_seed: exception during seeding: %s", exc)
        return False

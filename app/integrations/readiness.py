"""CRM data readiness — quality report, training eligibility, label mapping.

Works entirely from already-synced Supabase data. No live CRM API calls.
Supports both HubSpot and Salesforce.

Public API:
  compute_readiness(tenant_id, provider) -> dict
  discover_candidate_fields(tenant_id, provider) -> list[dict]
  load_label_mapping(tenant_id, provider) -> dict | None
  save_label_mapping(tenant_id, provider, field_name, churned_values) -> dict
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("pickpulse.readiness")

# ---------------------------------------------------------------------------
# Eligibility constants
# ---------------------------------------------------------------------------
ELIGIBILITY_READY              = "ready"
ELIGIBILITY_NEEDS_MAPPING      = "needs_outcome_mapping"
ELIGIBILITY_INSUFFICIENT_CHURN = "insufficient_churn"
ELIGIBILITY_LOW_SIGNALS        = "low_signal_coverage"
ELIGIBILITY_INSUFFICIENT_DATA  = "insufficient_data"

# Confidence thresholds
_HIGH_CHURNED, _HIGH_SIGNAL, _HIGH_TOTAL       = 50, 0.70, 200
_MEDIUM_CHURNED, _MEDIUM_SIGNAL, _MEDIUM_TOTAL = 20, 0.40, 50

# Eligibility thresholds
_MIN_TOTAL   = 10
_MIN_CHURNED = 5
_MIN_SIGNAL  = 0.15

# Key suffixes excluded from candidate field discovery
_EXCLUDED_SUFFIXES = ("id", "uri", "url", "link", "_at", "email", "phone", "date")

# Priority fields shown first in candidate list
_PRIORITY_FIELDS: Dict[str, List[str]] = {
    "hubspot":    ["hs_lifecycle_stage", "hs_lead_status", "lifecyclestage"],
    "salesforce": ["Type", "Status", "AccountSource"],
}

_SIGNAL_BATCH = 500


# ---------------------------------------------------------------------------
# Label mapping — file-backed persistence
# ---------------------------------------------------------------------------

def _mapping_path(tenant_id: str, provider: str) -> str:
    data_dir = os.environ.get("DATA_DIR", "data")
    out_dir = os.path.join(data_dir, "outputs", tenant_id)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"label_mapping_{provider}.json")


def load_label_mapping(tenant_id: str, provider: str) -> Optional[Dict[str, Any]]:
    path = _mapping_path(tenant_id, provider)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("[readiness] load_label_mapping failed: %s", exc)
        return None


def save_label_mapping(
    tenant_id: str,
    provider: str,
    field_name: str,
    churned_values: List[str],
) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {
        "provider": provider,
        "field_name": field_name.strip(),
        "churned_values": [v.strip() for v in churned_values if v.strip()],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(_mapping_path(tenant_id, provider), "w") as f:
        json.dump(mapping, f)
    logger.info(
        "[readiness] saved label mapping %s/%s: %s=%s",
        provider, tenant_id, field_name, churned_values,
    )
    return mapping


# ---------------------------------------------------------------------------
# Candidate field discovery — scans raw_data already in Supabase
# ---------------------------------------------------------------------------

def discover_candidate_fields(
    tenant_id: str,
    provider: str,
    max_accounts: int = 200,
) -> List[Dict[str, Any]]:
    """Scan raw_data from synced accounts to find candidate churn label fields.

    Returns up to 20 fields sorted by: provider priority fields first,
    then by number of accounts containing the field (desc).
    """
    from app.storage import repo

    accounts = repo.list_accounts(source=provider, limit=max_accounts, tenant_id=tenant_id)
    if not accounts:
        return []

    priority_set = set(_PRIORITY_FIELDS.get(provider, []))
    field_values: Dict[str, List[str]] = {}

    for acct in accounts:
        raw = acct.get("raw_data") or {}
        for key, val in raw.items():
            if key.startswith("_"):
                continue
            if not isinstance(val, str) or not val.strip():
                continue
            val_clean = val.strip()
            if val_clean.lower() in ("null", "none", "n/a", ""):
                continue
            key_lower = key.lower()
            if any(key_lower.endswith(sfx) for sfx in _EXCLUDED_SUFFIXES):
                continue
            field_values.setdefault(key, []).append(val_clean)

    results = []
    for field_name, values in field_values.items():
        unique_vals = list(dict.fromkeys(values))  # ordered dedupe
        if len(unique_vals) < 2 or len(unique_vals) > 30:
            continue  # not categorical
        results.append({
            "field_name": field_name,
            "sample_values": unique_vals[:10],
            "account_count_with_field": len(values),
            "_p": field_name in priority_set,
        })

    results.sort(key=lambda r: (not r["_p"], -r["account_count_with_field"]))
    for r in results:
        del r["_p"]
    return results[:20]


# ---------------------------------------------------------------------------
# Confidence + eligibility
# ---------------------------------------------------------------------------

def _confidence(total: int, churned: int, signal_pct: float) -> str:
    if churned >= _HIGH_CHURNED and signal_pct >= _HIGH_SIGNAL and total >= _HIGH_TOTAL:
        return "High"
    if churned >= _MEDIUM_CHURNED and signal_pct >= _MEDIUM_SIGNAL and total >= _MEDIUM_TOTAL:
        return "Medium"
    return "Low"


def _eligibility(total: int, churned: int, signal_pct: float) -> Tuple[str, str]:
    if total < _MIN_TOTAL:
        return (
            ELIGIBILITY_INSUFFICIENT_DATA,
            f"Only {total} account{'s' if total != 1 else ''} synced. "
            f"Need at least {_MIN_TOTAL} to enable training.",
        )
    if churned == 0:
        return (
            ELIGIBILITY_NEEDS_MAPPING,
            "No churned accounts detected automatically. "
            "Map a CRM field to identify churned accounts so the model has examples to learn from.",
        )
    if churned < _MIN_CHURNED:
        return (
            ELIGIBILITY_INSUFFICIENT_CHURN,
            f"Only {churned} churned account{'s' if churned != 1 else ''} detected — "
            f"need at least {_MIN_CHURNED} to split the data reliably. "
            "Map additional label values or import historical data.",
        )
    if signal_pct < _MIN_SIGNAL:
        return (
            ELIGIBILITY_LOW_SIGNALS,
            f"Only {signal_pct:.0%} of accounts have engagement signals. "
            "Training is possible but predictions will be less reliable.",
        )
    return (
        ELIGIBILITY_READY,
        f"{churned} churned accounts detected across {total} total. "
        f"Signal coverage: {signal_pct:.0%}.",
    )


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def compute_readiness(tenant_id: str, provider: str) -> Dict[str, Any]:
    """Compute readiness report from already-synced Supabase data."""
    from app.storage.db import get_client

    sb = get_client()

    # 1. Accounts for this provider
    try:
        acct_res = (
            sb.table("accounts")
            .select("id, arr")
            .eq("tenant_id", tenant_id)
            .eq("source", provider)
            .execute()
        )
        account_rows = acct_res.data or []
    except Exception as exc:
        logger.warning("[readiness] account query failed: %s", exc)
        account_rows = []

    total_accounts = len(account_rows)
    account_ids = [r["id"] for r in account_rows if r.get("id")]
    with_arr = sum(
        1 for r in account_rows
        if r.get("arr") is not None and float(r.get("arr") or 0) > 0
    )
    pct_with_arr = with_arr / total_accounts if total_accounts > 0 else 0.0

    # 2. Signal coverage
    accounts_with_signals = 0
    if account_ids:
        try:
            seen: set = set()
            for i in range(0, len(account_ids), _SIGNAL_BATCH):
                batch = account_ids[i : i + _SIGNAL_BATCH]
                sig_res = (
                    sb.table("account_signals_daily")
                    .select("account_id")
                    .in_("account_id", batch)
                    .execute()
                )
                seen.update(r["account_id"] for r in (sig_res.data or []))
            accounts_with_signals = len(seen)
        except Exception as exc:
            logger.warning("[readiness] signal coverage query failed: %s", exc)

    pct_with_signals = accounts_with_signals / total_accounts if total_accounts > 0 else 0.0

    # 3. Churned outcomes scoped to this provider's accounts
    churned_count = 0
    if account_ids:
        try:
            account_id_set = set(account_ids)
            outcome_res = (
                sb.table("account_outcomes")
                .select("account_id")
                .eq("tenant_id", tenant_id)
                .eq("outcome_type", "churned")
                .execute()
            )
            churned_count = sum(
                1 for r in (outcome_res.data or [])
                if r.get("account_id") in account_id_set
            )
        except Exception as exc:
            logger.warning("[readiness] outcome query failed: %s", exc)

    confidence = _confidence(total_accounts, churned_count, pct_with_signals)
    elig, elig_msg = _eligibility(total_accounts, churned_count, pct_with_signals)
    label_mapping = load_label_mapping(tenant_id, provider)

    candidate_fields: List[Dict[str, Any]] = []
    if elig == ELIGIBILITY_NEEDS_MAPPING or label_mapping is None:
        try:
            candidate_fields = discover_candidate_fields(tenant_id, provider)
        except Exception as exc:
            logger.warning("[readiness] candidate discovery failed: %s", exc)

    return {
        "provider": provider,
        "total_accounts": total_accounts,
        "churned_detected": churned_count,
        "pct_with_signals": round(pct_with_signals, 3),
        "pct_with_arr": round(pct_with_arr, 3),
        "expected_confidence": confidence,
        "eligibility": elig,
        "eligibility_message": elig_msg,
        "label_mapping": label_mapping,
        "candidate_fields": candidate_fields,
    }

"""CRM data readiness — quality report, training eligibility, label mapping.

Works entirely from already-synced Supabase data. No live CRM API calls.
Supports both HubSpot and Salesforce.

Label mappings are stored durably in the `crm_label_mappings` Supabase table
(one row per tenant/provider, upserted on save).

Public API
----------
compute_readiness(tenant_id, provider) -> dict
discover_candidate_fields(tenant_id, provider) -> list[dict]
load_label_mapping(tenant_id, provider) -> dict | None
save_label_mapping(tenant_id, provider, field_name, churned_values) -> dict

Eligibility states
------------------
insufficient_data      total < 10                          → training DISABLED
needs_outcome_mapping  churned == 0                        → training DISABLED
insufficient_churn     1 ≤ churned < 20                   → training DISABLED
low_signal_coverage    churned ≥ 20, signal_pct < 0.15    → training ENABLED (Low confidence)
ready                  churned ≥ 20, signal_pct ≥ 0.15    → training ENABLED

Confidence tier (meaningful only when training is enabled)
------------------
High    churned ≥ 50, signal_pct ≥ 0.70, total ≥ 200
Medium  churned ≥ 20, signal_pct ≥ 0.40, total ≥ 50
Low     everything else (includes low_signal_coverage)
"""
from __future__ import annotations

import logging
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

# Minimum churned examples to allow training
_MIN_TOTAL   = 10
_MIN_CHURNED = 20   # below this → training disabled regardless of signal coverage
_MIN_SIGNAL  = 0.15

# Confidence thresholds (only applied when eligibility is ready or low_signal_coverage)
_HIGH_CHURNED, _HIGH_SIGNAL, _HIGH_TOTAL       = 50, 0.70, 200
_MEDIUM_CHURNED, _MEDIUM_SIGNAL, _MEDIUM_TOTAL = 20, 0.40, 50

# Supabase IN-clause batch size
_SIGNAL_BATCH = 500

# ---------------------------------------------------------------------------
# Candidate field ranking — vocabulary and scoring
# ---------------------------------------------------------------------------

# Substring terms that suggest a field is related to churn/lifecycle/status
_CHURN_HINT_TERMS = frozenset([
    "churn", "cancel", "inactive", "lost", "former", "expired",
    "closed", "attrition", "departed", "terminated", "offboard", "lapsed",
    "lifecycle", "status", "stage", "type", "tier", "health",
    "renewal", "renew", "retain",
])

# Excluded key suffixes — URLs, timestamps, IDs, free-text fields
_EXCLUDED_SUFFIXES = (
    "id", "uri", "url", "link", "_at", "email", "phone", "date",
    "name", "address", "description", "note", "comment",
)

# Provider-specific priority fields — guaranteed to appear first if present
_PRIORITY_FIELDS: Dict[str, List[str]] = {
    "hubspot":    ["hs_lifecycle_stage", "hs_lead_status", "lifecyclestage"],
    "salesforce": ["Type", "Status", "AccountSource"],
}

# Minimum score for a candidate to be returned (prevents garbage fields)
_MIN_SCORE = 10.0


def _candidate_score(
    field_name: str,
    n_unique: int,
    field_count: int,
    total_accounts: int,
) -> float:
    """Score a candidate field 0–100. Higher = more likely to be useful for churn labeling."""
    score = 0.0

    # 1. Coverage (0–35): prefer fields present on most accounts
    coverage = field_count / max(total_accounts, 1)
    score += coverage * 35

    # 2. Cardinality (0–35): sweet spot is 2–8 distinct values
    if n_unique <= 8:
        score += 35
    elif n_unique <= 15:
        score += 20
    elif n_unique <= 25:
        score += 8
    # n_unique > 25 → 0 points (likely free-text, not useful for label mapping)

    # 3. Name hint (0–30): any hint term is a substring of the field name
    fn = field_name.lower().replace("_", " ").replace("-", " ").replace(".", " ")
    for term in _CHURN_HINT_TERMS:
        if term in fn:
            score += 30
            break

    return score


# ---------------------------------------------------------------------------
# Label mapping — Supabase-backed persistence
# ---------------------------------------------------------------------------

def load_label_mapping(tenant_id: str, provider: str) -> Optional[Dict[str, Any]]:
    """Return the saved label mapping for this tenant/provider, or None."""
    from app.storage.db import get_client

    try:
        sb = get_client()
        res = (
            sb.table("crm_label_mappings")
            .select("provider, field_name, churned_values, updated_at")
            .eq("tenant_id", tenant_id)
            .eq("provider", provider)
            .execute()
        )
        if res.data:
            row = res.data[0]
            return {
                "provider": row["provider"],
                "field_name": row["field_name"],
                "churned_values": row["churned_values"],
                "updated_at": row["updated_at"],
            }
        return None
    except Exception as exc:
        logger.warning("[readiness] load_label_mapping failed: %s", exc)
        return None


def save_label_mapping(
    tenant_id: str,
    provider: str,
    field_name: str,
    churned_values: List[str],
) -> Dict[str, Any]:
    """Upsert a label mapping for this tenant/provider. Returns the saved mapping."""
    from app.storage.db import get_client
    from datetime import datetime, timezone

    cleaned_values = [v.strip() for v in churned_values if v.strip()]
    sb = get_client()
    sb.table("crm_label_mappings").upsert(
        {
            "tenant_id": tenant_id,
            "provider": provider,
            "field_name": field_name.strip(),
            "churned_values": cleaned_values,
        },
        on_conflict="tenant_id,provider",
    ).execute()
    logger.info(
        "[readiness] saved label mapping %s/%s: %s → %s",
        provider, tenant_id, field_name, cleaned_values,
    )
    # Re-read to get DB-generated timestamps
    saved = load_label_mapping(tenant_id, provider)
    return saved or {
        "provider": provider,
        "field_name": field_name.strip(),
        "churned_values": cleaned_values,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Candidate field discovery — from raw_data already in Supabase
# ---------------------------------------------------------------------------

def discover_candidate_fields(
    tenant_id: str,
    provider: str,
    max_accounts: int = 200,
) -> List[Dict[str, Any]]:
    """Scan raw_data from synced accounts to surface candidate churn label fields.

    Ranking: scored across coverage (35pts) + cardinality (35pts) + name hint (30pts).
    Provider priority fields are pinned to the top regardless of score.
    Fields scoring below _MIN_SCORE are dropped (too sparse or high-cardinality).
    Returns up to 20 candidates.
    """
    from app.storage import repo

    accounts = repo.list_accounts(source=provider, limit=max_accounts, tenant_id=tenant_id)
    if not accounts:
        return []

    total_accounts = len(accounts)
    priority_set = set(_PRIORITY_FIELDS.get(provider, []))
    field_values: Dict[str, List[str]] = {}

    for acct in accounts:
        raw = acct.get("raw_data") or {}
        for key, val in raw.items():
            if key.startswith("_"):
                continue  # skip PickPulse internal fields
            if not isinstance(val, str) or not val.strip():
                continue
            val_clean = val.strip()
            if val_clean.lower() in ("null", "none", "n/a", ""):
                continue
            key_lower = key.lower()
            if any(key_lower.endswith(sfx) for sfx in _EXCLUDED_SUFFIXES):
                continue
            field_values.setdefault(key, []).append(val_clean)

    scored: List[Dict[str, Any]] = []
    for field_name, values in field_values.items():
        unique_vals = list(dict.fromkeys(values))  # ordered dedupe
        n_unique = len(unique_vals)
        if n_unique < 2 or n_unique > 30:
            continue

        score = _candidate_score(field_name, n_unique, len(values), total_accounts)
        if score < _MIN_SCORE:
            continue

        scored.append({
            "field_name": field_name,
            "sample_values": unique_vals[:10],
            "account_count_with_field": len(values),
            "_score": score,
            "_priority": field_name in priority_set,
        })

    # Sort: priority fields first (pinned), then by score descending
    scored.sort(key=lambda r: (not r["_priority"], -r["_score"]))

    # Strip internal sort keys
    for r in scored:
        del r["_score"]
        del r["_priority"]

    return scored[:20]


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
            "Map a CRM field to identify churned accounts — "
            "the model needs labeled examples to learn from.",
        )
    if churned < _MIN_CHURNED:
        return (
            ELIGIBILITY_INSUFFICIENT_CHURN,
            f"{churned} churned account{'s' if churned != 1 else ''} detected, "
            f"but training requires at least {_MIN_CHURNED}. "
            "Map additional label values or import historical churned accounts.",
        )
    if signal_pct < _MIN_SIGNAL:
        return (
            ELIGIBILITY_LOW_SIGNALS,
            f"{churned} churned accounts detected across {total} total. "
            f"Signal coverage is low ({signal_pct:.0%}) — training will proceed "
            "but predictions will be less reliable.",
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
    """Compute a readiness report from already-synced Supabase data.

    Queries accounts, account_signals_daily, account_outcomes, and
    crm_label_mappings. No live CRM API calls.
    """
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

    # 2. Signal coverage (accounts with at least one signal row)
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

    # 3. Churned outcomes — scoped to this provider's accounts
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

    # Surface candidate fields when mapping is needed or none is set
    candidate_fields: List[Dict[str, Any]] = []
    if elig in (ELIGIBILITY_NEEDS_MAPPING, ELIGIBILITY_INSUFFICIENT_CHURN) or label_mapping is None:
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
        "training_enabled": elig in (ELIGIBILITY_READY, ELIGIBILITY_LOW_SIGNALS),
        "label_mapping": label_mapping,
        "candidate_fields": candidate_fields,
    }

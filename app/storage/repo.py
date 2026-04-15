"""Repository layer — CRUD over Supabase Postgres tables.

Tables:
  accounts              (tenant_id, source, external_id unique)
  account_signals_daily (tenant_id, account_id, signal_date, signal_key unique)
  churn_scores_daily    (tenant_id, account_id, score_date unique)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from app.storage.db import get_client
from app.integrations.models import Account, AccountSignal, ChurnScore

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def upsert_accounts(accounts: List[Account], tenant_id: str = DEFAULT_TENANT) -> int:
    """Upsert accounts into Supabase. Returns count upserted."""
    if not accounts:
        return 0

    sb = get_client()
    rows = []
    for acct in accounts:
        rows.append({
            "tenant_id": tenant_id,
            "external_id": acct.external_id,
            "source": acct.source,
            "name": acct.name,
            "domain": acct.email,  # map email/domain
            "arr": float(acct.arr) if acct.arr is not None else None,
            "status": "active",
            "auto_renew": None,
            "metadata": {
                "plan": acct.plan,
                "seats": acct.seats,
                "industry": acct.industry,
                "company_size": acct.company_size,
                "raw_data": acct.raw_data,
            },
        })

    res = sb.table("accounts").upsert(
        rows,
        on_conflict="tenant_id,source,external_id",
    ).execute()

    return len(res.data) if res.data else 0


def list_accounts(
    source: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    tenant_id: str = DEFAULT_TENANT,
) -> List[Dict[str, Any]]:
    try:
        sb = get_client()
        q = sb.table("accounts").select("*").eq("tenant_id", tenant_id)
        if source:
            q = q.eq("source", source)
        q = q.order("arr", desc=True).range(offset, offset + limit - 1)
        res = q.execute()
        return res.data or []
    except Exception as exc:
        logger.warning("list_accounts: table unavailable (%s) — returning empty list", exc)
        return []


def get_account(
    external_id: str,
    source: Optional[str] = None,
    tenant_id: str = DEFAULT_TENANT,
) -> Optional[Dict[str, Any]]:
    sb = get_client()
    q = sb.table("accounts").select("*").eq("tenant_id", tenant_id).eq("external_id", external_id)
    if source:
        q = q.eq("source", source)
    res = q.limit(1).execute()
    return res.data[0] if res.data else None


def get_account_id(
    external_id: str,
    source: Optional[str] = None,
    tenant_id: str = DEFAULT_TENANT,
) -> Optional[str]:
    """Look up the uuid for an external_id, optionally scoped to a source.

    Pass source="hubspot" or source="salesforce" to prevent cross-CRM
    collisions when the same external_id format could theoretically appear
    in multiple providers.
    """
    row = get_account(external_id, source=source, tenant_id=tenant_id)
    return row["id"] if row else None


def account_count(source: Optional[str] = None, tenant_id: str = DEFAULT_TENANT) -> int:
    try:
        sb = get_client()
        q = sb.table("accounts").select("id", count="exact").eq("tenant_id", tenant_id)
        if source:
            q = q.eq("source", source)
        res = q.execute()
        return res.count if res.count is not None else 0
    except Exception as exc:
        logger.warning("account_count: table unavailable (%s) — returning 0", exc)
        return 0


def clear_provider_data(source: str, tenant_id: str) -> Dict[str, int]:
    """Delete all Supabase rows for a CRM provider's accounts.

    Clears in dependency order to avoid foreign-key violations:
      churn_scores_daily → account_signals_daily → account_outcomes → accounts

    Called by reset_demo so that a demo reset produces a truly clean state
    and the idempotency guard in DemoDataLoader works correctly on next sync.

    Returns a dict of ``{table_name: rows_deleted}`` for logging.
    """
    try:
        sb = get_client()
        acct_res = (
            sb.table("accounts")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("source", source)
            .execute()
        )
        account_ids = [r["id"] for r in (acct_res.data or []) if r.get("id")]
        if not account_ids:
            return {"accounts": 0, "scores": 0, "signals": 0, "outcomes": 0}

        BATCH = 200
        counts: Dict[str, int] = {"scores": 0, "signals": 0, "outcomes": 0, "accounts": 0}

        # Delete scores
        for i in range(0, len(account_ids), BATCH):
            batch = account_ids[i : i + BATCH]
            res = sb.table("churn_scores_daily").delete().eq("tenant_id", tenant_id).in_("account_id", batch).execute()
            counts["scores"] += len(res.data) if res.data else 0

        # Delete signals
        for i in range(0, len(account_ids), BATCH):
            batch = account_ids[i : i + BATCH]
            res = sb.table("account_signals_daily").delete().eq("tenant_id", tenant_id).in_("account_id", batch).execute()
            counts["signals"] += len(res.data) if res.data else 0

        # Delete outcomes
        for i in range(0, len(account_ids), BATCH):
            batch = account_ids[i : i + BATCH]
            res = sb.table("account_outcomes").delete().eq("tenant_id", tenant_id).in_("account_id", batch).execute()
            counts["outcomes"] += len(res.data) if res.data else 0

        # Delete accounts
        res = sb.table("accounts").delete().eq("tenant_id", tenant_id).eq("source", source).execute()
        counts["accounts"] += len(res.data) if res.data else 0

        logger.info("clear_provider_data: %s tenant=%s deleted=%s", source, tenant_id[:8], counts)
        return counts
    except Exception as exc:
        logger.warning("clear_provider_data: failed for source=%s: %s", source, exc)
        return {}


def clear_scores_for_source(source: str, tenant_id: str = DEFAULT_TENANT) -> int:
    """Delete all churn_scores_daily rows for accounts belonging to `source`.

    Called on CRM disconnect so that stale scores never pre-populate the UI
    when the user reconnects and has not yet re-trained or re-scored.
    Returns the number of rows deleted.
    """
    try:
        sb = get_client()
        # Resolve account UUIDs for this provider
        acct_res = (
            sb.table("accounts")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("source", source)
            .execute()
        )
        account_ids = [r["id"] for r in (acct_res.data or []) if r.get("id")]
        if not account_ids:
            return 0
        # Delete in batches to stay within Supabase URL limits
        deleted = 0
        BATCH = 200
        for i in range(0, len(account_ids), BATCH):
            batch = account_ids[i: i + BATCH]
            res = (
                sb.table("churn_scores_daily")
                .delete()
                .eq("tenant_id", tenant_id)
                .in_("account_id", batch)
                .execute()
            )
            deleted += len(res.data) if res.data else 0
        logger.info("clear_scores_for_source: deleted %d score rows for source=%s", deleted, source)
        return deleted
    except Exception as exc:
        logger.warning("clear_scores_for_source: failed (%s)", exc)
        return 0


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

_SIGNAL_KEYS = [
    "monthly_logins", "support_tickets", "nps_score",
    "days_since_last_login", "contract_months_remaining",
    "days_until_renewal", "auto_renew_flag", "renewal_status",
    "seats",
]


def upsert_signals(signals: List[AccountSignal], tenant_id: str = DEFAULT_TENANT) -> int:
    """Upsert signals. Each AccountSignal field becomes a separate signal_key row."""
    if not signals:
        return 0

    sb = get_client()
    rows = []
    for sig in signals:
        account_id = get_account_id(sig.external_id, tenant_id=tenant_id)
        if not account_id:
            continue

        sig_dict = sig.model_dump()
        for key in _SIGNAL_KEYS:
            val = sig_dict.get(key)
            if val is None:
                continue
            if isinstance(val, str):
                rows.append({
                    "tenant_id": tenant_id,
                    "account_id": account_id,
                    "signal_date": sig.signal_date,
                    "signal_key": key,
                    "signal_value": None,
                    "signal_text": val,
                })
            else:
                rows.append({
                    "tenant_id": tenant_id,
                    "account_id": account_id,
                    "signal_date": sig.signal_date,
                    "signal_key": key,
                    "signal_value": float(val),
                    "signal_text": None,
                })

        # Store extra as a single JSON signal
        if sig.extra:
            rows.append({
                "tenant_id": tenant_id,
                "account_id": account_id,
                "signal_date": sig.signal_date,
                "signal_key": "extra",
                "signal_value": None,
                "signal_text": json.dumps(sig.extra),
            })

    if not rows:
        return 0

    res = sb.table("account_signals_daily").upsert(
        rows,
        on_conflict="tenant_id,account_id,signal_date,signal_key",
    ).execute()

    return len(res.data) if res.data else 0


def latest_signals(external_id: str, tenant_id: str = DEFAULT_TENANT) -> Optional[Dict[str, Any]]:
    """Get latest signals for an account, pivoted back to a flat dict."""
    account_id = get_account_id(external_id, tenant_id=tenant_id)
    if not account_id:
        return None

    sb = get_client()
    res = (
        sb.table("account_signals_daily")
        .select("signal_key, signal_value, signal_text, signal_date")
        .eq("tenant_id", tenant_id)
        .eq("account_id", account_id)
        .order("signal_date", desc=True)
        .limit(20)  # get enough rows for latest date
        .execute()
    )

    if not res.data:
        return None

    # Group by the most recent signal_date
    latest_date = res.data[0]["signal_date"]
    result: Dict[str, Any] = {"signal_date": latest_date}
    for row in res.data:
        if row["signal_date"] != latest_date:
            break
        key = row["signal_key"]
        if key == "extra":
            continue
        result[key] = row["signal_value"] if row["signal_value"] is not None else row["signal_text"]

    return result


# ---------------------------------------------------------------------------
# Churn scores
# ---------------------------------------------------------------------------

def insert_scores(scores: List[ChurnScore], tenant_id: str = DEFAULT_TENANT) -> int:
    """Upsert churn scores."""
    if not scores:
        return 0

    sb = get_client()
    today = date.today().isoformat()

    # Batch-fetch external_id → account UUID in one pass to avoid N+1 DB queries.
    _BATCH = 400
    external_ids = [s.external_id for s in scores]
    id_map: Dict[str, str] = {}
    for i in range(0, len(external_ids), _BATCH):
        batch_ext = external_ids[i : i + _BATCH]
        res = (
            sb.table("accounts")
            .select("id,external_id")
            .eq("tenant_id", tenant_id)
            .in_("external_id", batch_ext)
            .execute()
        )
        for row in res.data or []:
            id_map[row["external_id"]] = row["id"]

    rows = []
    for score in scores:
        account_id = id_map.get(score.external_id)
        if not account_id:
            continue
        rows.append({
            "tenant_id": tenant_id,
            "account_id": account_id,
            "score_date": today,
            "churn_risk_pct": round(float(score.churn_probability * 100), 1),
            "urgency": float(score.urgency_score) if score.urgency_score is not None else None,
            "renewal_window": score.renewal_window_label,
            "arr_at_risk": float(score.arr_at_risk) if score.arr_at_risk is not None else None,
            "recommended_action": score.recommended_action,
            "account_status": "active",
            "model_version": "churn_v1",
            "top_drivers": score.top_drivers or [],
            "confidence_level": score.confidence_level,
        })

    if not rows:
        return 0

    total = 0
    for i in range(0, len(rows), _BATCH):
        res = sb.table("churn_scores_daily").upsert(
            rows[i : i + _BATCH],
            on_conflict="tenant_id,account_id,score_date",
        ).execute()
        total += len(res.data) if res.data else len(rows[i : i + _BATCH])

    return total


def latest_scores(
    limit: int = 10000,
    tenant_id: str = DEFAULT_TENANT,
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get the most recent score per account, joined with account info.

    source: if provided, restricts results to accounts from that CRM provider
    (e.g. "hubspot", "salesforce"). Filtering is done in Python after the join
    because PostgREST filtering on related table columns is not reliably
    supported via the Python client.
    """
    try:
        sb = get_client()

        # Get latest scores ordered by risk
        res = (
            sb.table("churn_scores_daily")
            .select("*, accounts(name, domain, arr, source, external_id, metadata)")
            .eq("tenant_id", tenant_id)
            .order("score_date", desc=True)
            .order("churn_risk_pct", desc=True)
            .limit(limit)
            .execute()
        )

        if not res.data:
            return []

        # Flatten the join
        results = []
        seen_accounts = set()
        for row in res.data:
            acct = row.pop("accounts", {}) or {}
            aid = row.get("account_id")
            if aid in seen_accounts:
                continue  # only latest per account
            seen_accounts.add(aid)

            acct_source = acct.get("source")
            if source and acct_source != source:
                continue  # skip accounts from other providers

            meta = acct.get("metadata") or {}
            results.append({
                **row,
                "name": acct.get("name"),
                "email": acct.get("domain"),
                "plan": meta.get("plan"),
                "arr": acct.get("arr"),
                "source": acct_source,
                "external_id": acct.get("external_id"),
                # Map fields for frontend compatibility
                "churn_probability": row.get("churn_risk_pct", 0) / 100.0,
                "tier": _risk_to_tier(row.get("churn_risk_pct", 0)),
                "urgency_score": row.get("urgency"),
            })

        return results[:limit]
    except Exception as exc:
        logger.warning("latest_scores: table unavailable (%s) — returning empty list", exc)
        return []


def score_history(external_id: str, limit: int = 30, tenant_id: str = DEFAULT_TENANT) -> List[Dict[str, Any]]:
    try:
        account_id = get_account_id(external_id, tenant_id=tenant_id)
        if not account_id:
            return []

        sb = get_client()
        res = (
            sb.table("churn_scores_daily")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("account_id", account_id)
            .order("score_date", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning("score_history: table unavailable (%s) — returning empty list", exc)
        return []


def _risk_to_tier(pct: float) -> str:
    if pct >= 30:
        return "High Risk"
    if pct >= 20:
        return "Medium Risk"
    return "Low Risk"


# ---------------------------------------------------------------------------
# Bulk signals (one query for all accounts — avoids N+1 in CRM mode)
# ---------------------------------------------------------------------------

def bulk_latest_signals(tenant_id: str = DEFAULT_TENANT) -> Dict[str, Dict[str, Any]]:
    """Fetch the latest signal snapshot for every account in one query.

    Returns {account_uuid: {signal_key: value, ...}}.
    Rows are ordered date DESC so the first occurrence per account is the latest.
    """
    try:
        sb = get_client()
        res = (
            sb.table("account_signals_daily")
            .select("account_id, signal_key, signal_value, signal_text, signal_date")
            .eq("tenant_id", tenant_id)
            .order("signal_date", desc=True)
            .limit(500000)
            .execute()
        )
        if not res.data:
            return {}

        latest_date: Dict[str, str] = {}
        result: Dict[str, Dict[str, Any]] = {}
        for row in res.data:
            aid = row["account_id"]
            key = row["signal_key"]
            sig_date = row["signal_date"]
            if key == "extra":
                continue
            if aid not in latest_date:
                latest_date[aid] = sig_date
                result[aid] = {}
            if sig_date != latest_date[aid]:
                continue  # older date for this account
            if key not in result[aid]:  # first occurrence = latest
                result[aid][key] = (
                    row["signal_value"] if row["signal_value"] is not None else row["signal_text"]
                )
        return result
    except Exception as exc:
        logger.warning("bulk_latest_signals: unavailable (%s) — returning empty dict", exc)
        return {}


def has_recent_scores(tenant_id: str = DEFAULT_TENANT, days: int = 30) -> bool:
    """Return True if churn_scores_daily has rows scored within `days` days."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        sb = get_client()
        res = (
            sb.table("churn_scores_daily")
            .select("id")
            .eq("tenant_id", tenant_id)
            .gte("score_date", cutoff)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception as exc:
        logger.warning("has_recent_scores: unavailable (%s) — returning False", exc)
        return False


def get_account_latest_score(
    external_id: str,
    tenant_id: str = DEFAULT_TENANT,
) -> Optional[Dict[str, Any]]:
    """Get the most recent churn score for one account by external_id."""
    account_id = get_account_id(external_id, tenant_id=tenant_id)
    if not account_id:
        return None
    try:
        sb = get_client()
        res = (
            sb.table("churn_scores_daily")
            .select("*, accounts(name, domain, arr, source, external_id, metadata)")
            .eq("tenant_id", tenant_id)
            .eq("account_id", account_id)
            .order("score_date", desc=True)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        acct = row.pop("accounts", {}) or {}
        meta = acct.get("metadata") or {}
        return {
            **row,
            "name": acct.get("name"),
            "domain": acct.get("domain"),
            "plan": meta.get("plan"),
            "arr": acct.get("arr"),
            "source": acct.get("source"),
            "external_id": acct.get("external_id"),
            "tier": _risk_to_tier(row.get("churn_risk_pct", 0)),
            "urgency_score": row.get("urgency"),
        }
    except Exception as exc:
        logger.warning("get_account_latest_score: unavailable (%s) — returning None", exc)
        return None


# ---------------------------------------------------------------------------
# Outcome recording
# ---------------------------------------------------------------------------

_OUTCOME_TYPES = {"renewed", "churned", "expanded"}
_OUTCOME_SOURCES = {"manual", "hubspot", "salesforce", "stripe", "system"}


def record_outcome(
    external_id: str,
    outcome_type: str,
    source: str = "manual",
    notes: Optional[str] = None,
    effective_date: Optional[str] = None,
    tenant_id: str = DEFAULT_TENANT,
) -> bool:
    """Insert a canonical outcome row for an account.

    Returns True if written, False if the account wasn't found or the write failed.
    Failures are logged as warnings (non-fatal) so callers can proceed without
    blocking on Supabase availability.
    """
    if outcome_type not in _OUTCOME_TYPES:
        logger.warning("record_outcome: unknown outcome_type=%s — skipping", outcome_type)
        return False

    account_id = get_account_id(external_id, tenant_id=tenant_id)
    if not account_id:
        logger.warning(
            "record_outcome: no account for external_id=%s tenant=%s", external_id, tenant_id
        )
        return False

    today = date.today().isoformat()
    try:
        sb = get_client()
        sb.table("account_outcomes").insert({
            "tenant_id": tenant_id,
            "account_id": account_id,
            "outcome_type": outcome_type,
            "effective_date": effective_date or today,
            "source": source if source in _OUTCOME_SOURCES else "manual",
            "notes": notes,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as exc:
        logger.warning("record_outcome: insert failed (%s)", exc)
        return False


def upsert_outcome(
    external_id: str,
    outcome_type: str,
    source: str,
    effective_date: Optional[str] = None,
    notes: Optional[str] = None,
    tenant_id: str = DEFAULT_TENANT,
) -> bool:
    """Write an outcome only if no outcome from this source already exists for the account.

    Idempotent: safe to call on every sync — won't create duplicates.
    Manual outcomes (source='manual') are separate from CRM-sourced outcomes
    and are never overwritten.
    Returns True if a new record was written, False if skipped or failed.
    """
    if outcome_type not in _OUTCOME_TYPES:
        logger.warning("upsert_outcome: unknown outcome_type=%s — skipping", outcome_type)
        return False

    account_id = get_account_id(external_id, tenant_id=tenant_id)
    if not account_id:
        return False

    try:
        sb = get_client()
        # Check whether this source has already recorded an outcome for this account
        existing = (
            sb.table("account_outcomes")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("account_id", account_id)
            .eq("source", source)
            .limit(1)
            .execute()
        )
        if existing.data:
            return False  # Already imported from this source — skip

        sb.table("account_outcomes").insert({
            "tenant_id": tenant_id,
            "account_id": account_id,
            "outcome_type": outcome_type,
            "effective_date": effective_date or date.today().isoformat(),
            "source": source if source in _OUTCOME_SOURCES else "system",
            "notes": notes,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as exc:
        logger.warning("upsert_outcome: failed (%s)", exc)
        return False


def list_outcomes(
    external_id: Optional[str] = None,
    limit: int = 100,
    tenant_id: str = DEFAULT_TENANT,
) -> List[Dict[str, Any]]:
    """Return outcome rows for the tenant, optionally filtered to one account."""
    try:
        sb = get_client()
        q = (
            sb.table("account_outcomes")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("effective_date", desc=True)
            .limit(limit)
        )
        if external_id:
            account_id = get_account_id(external_id, tenant_id=tenant_id)
            if not account_id:
                return []
            q = q.eq("account_id", account_id)
        res = q.execute()
        return res.data or []
    except Exception as exc:
        logger.warning("list_outcomes: unavailable (%s) — returning empty list", exc)
        return []

"""Repository layer — CRUD over Supabase Postgres tables.

Tables:
  accounts              (source, external_id unique)
  account_signals_daily (account_id, signal_date, signal_key unique)
  churn_scores_daily    (account_id, score_date unique)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

from app.storage.db import get_client
from app.integrations.models import Account, AccountSignal, ChurnScore


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def upsert_accounts(accounts: List[Account]) -> int:
    """Upsert accounts into Supabase. Returns count upserted."""
    if not accounts:
        return 0

    sb = get_client()
    rows = []
    for acct in accounts:
        rows.append({
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
        on_conflict="source,external_id",
    ).execute()

    return len(res.data) if res.data else 0


def list_accounts(
    source: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    sb = get_client()
    q = sb.table("accounts").select("*")
    if source:
        q = q.eq("source", source)
    q = q.order("arr", desc=True).range(offset, offset + limit - 1)
    res = q.execute()
    return res.data or []


def get_account(external_id: str, source: Optional[str] = None) -> Optional[Dict[str, Any]]:
    sb = get_client()
    q = sb.table("accounts").select("*").eq("external_id", external_id)
    if source:
        q = q.eq("source", source)
    res = q.limit(1).execute()
    return res.data[0] if res.data else None


def get_account_id(external_id: str) -> Optional[str]:
    """Look up the uuid for an external_id."""
    row = get_account(external_id)
    return row["id"] if row else None


def account_count(source: Optional[str] = None) -> int:
    sb = get_client()
    q = sb.table("accounts").select("id", count="exact")
    if source:
        q = q.eq("source", source)
    res = q.execute()
    return res.count if res.count is not None else 0


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

_SIGNAL_KEYS = [
    "monthly_logins", "support_tickets", "nps_score",
    "days_since_last_login", "contract_months_remaining",
    "days_until_renewal", "auto_renew_flag", "renewal_status",
    "seats",
]


def upsert_signals(signals: List[AccountSignal]) -> int:
    """Upsert signals. Each AccountSignal field becomes a separate signal_key row."""
    if not signals:
        return 0

    sb = get_client()
    rows = []
    for sig in signals:
        account_id = get_account_id(sig.external_id)
        if not account_id:
            continue

        sig_dict = sig.model_dump()
        for key in _SIGNAL_KEYS:
            val = sig_dict.get(key)
            if val is None:
                continue
            if isinstance(val, str):
                rows.append({
                    "account_id": account_id,
                    "signal_date": sig.signal_date,
                    "signal_key": key,
                    "signal_value": None,
                    "signal_text": val,
                })
            else:
                rows.append({
                    "account_id": account_id,
                    "signal_date": sig.signal_date,
                    "signal_key": key,
                    "signal_value": float(val),
                    "signal_text": None,
                })

        # Store extra as a single JSON signal
        if sig.extra:
            rows.append({
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
        on_conflict="account_id,signal_date,signal_key",
    ).execute()

    return len(res.data) if res.data else 0


def latest_signals(external_id: str) -> Optional[Dict[str, Any]]:
    """Get latest signals for an account, pivoted back to a flat dict."""
    account_id = get_account_id(external_id)
    if not account_id:
        return None

    sb = get_client()
    res = (
        sb.table("account_signals_daily")
        .select("signal_key, signal_value, signal_text, signal_date")
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

def insert_scores(scores: List[ChurnScore]) -> int:
    """Upsert churn scores."""
    if not scores:
        return 0

    sb = get_client()
    rows = []
    today = date.today().isoformat()

    for score in scores:
        account_id = get_account_id(score.external_id)
        if not account_id:
            continue
        rows.append({
            "account_id": account_id,
            "score_date": today,
            "churn_risk_pct": float(score.churn_probability * 100),
            "urgency": float(score.urgency_score) if score.urgency_score is not None else None,
            "renewal_window": None,
            "arr_at_risk": float(score.arr_at_risk) if score.arr_at_risk is not None else None,
            "recommended_action": score.recommended_action,
            "account_status": "active",
            "model_version": "churn_v1",
        })

    if not rows:
        return 0

    res = sb.table("churn_scores_daily").upsert(
        rows,
        on_conflict="account_id,score_date",
    ).execute()

    return len(res.data) if res.data else 0


def latest_scores(limit: int = 200) -> List[Dict[str, Any]]:
    """Get the most recent score per account, joined with account info."""
    sb = get_client()

    # Get latest scores ordered by risk
    res = (
        sb.table("churn_scores_daily")
        .select("*, accounts(name, domain, arr, source, external_id, metadata)")
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

        meta = acct.get("metadata") or {}
        results.append({
            **row,
            "name": acct.get("name"),
            "email": acct.get("domain"),
            "plan": meta.get("plan"),
            "arr": acct.get("arr"),
            "source": acct.get("source"),
            "external_id": acct.get("external_id"),
            # Map fields for frontend compatibility
            "churn_probability": row.get("churn_risk_pct", 0) / 100.0,
            "tier": _risk_to_tier(row.get("churn_risk_pct", 0)),
            "urgency_score": row.get("urgency"),
        })

    return results


def score_history(external_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    account_id = get_account_id(external_id)
    if not account_id:
        return []

    sb = get_client()
    res = (
        sb.table("churn_scores_daily")
        .select("*")
        .eq("account_id", account_id)
        .order("score_date", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def _risk_to_tier(pct: float) -> str:
    if pct >= 70:
        return "High Risk"
    if pct >= 40:
        return "Medium Risk"
    return "Low Risk"

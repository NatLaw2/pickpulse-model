"""CRM-native model training — builds a labeled training dataset from Supabase.

This module constructs a time-aware, labeled training DataFrame directly from
the accounts, account_signals_daily, and account_outcomes tables, bypassing
the CSV upload requirement for CRM-connected tenants.

Labeling hierarchy
------------------
Primary (from account_outcomes):
    outcome_type="churned"  → churned=1
    outcome_type="renewed"  → churned=0

Heuristic fallback (active accounts with no recorded outcome):
    assumed churned=0  (currently retained)

Time alignment
--------------
For accounts with a recorded outcome we find the signal snapshot whose date
is closest to (but before) the outcome's effective_date, within a 90-day
lookback window.  This prevents future-leakage: the model learns from signals
that existed *before* the outcome was known.

For accounts with no recorded outcome we use their latest snapshot.

Feature engineering
-------------------
Point-in-time signals:
    monthly_logins, support_tickets, nps_score, days_since_last_login,
    days_until_renewal, auto_renew_flag, contract_months_remaining, seats

Account-level:
    arr, plan, industry, company_size

CRM-extra (contact/deal metadata):
    contact_count, deal_count, days_since_last_activity

Derived ratios:
    login_rate_per_seat, ticket_rate_per_seat

Trend features (when ≥2 snapshots exist within 60-day window):
    delta_monthly_logins, delta_nps_score, delta_support_tickets,
    delta_days_until_renewal   (per-30-day rate of change)

Data sufficiency requirements
------------------------------
MIN_TOTAL_LABELED    = 30   total labeled rows
MIN_POSITIVE_LABELED = 10   churned=1 examples
MIN_NEGATIVE_LABELED = 10   churned=0 examples
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger("pickpulse.crm_training")

# ---------------------------------------------------------------------------
# Sufficiency thresholds
# ---------------------------------------------------------------------------

MIN_TOTAL_LABELED: int = 30
MIN_POSITIVE_LABELED: int = 10
MIN_NEGATIVE_LABELED: int = 10

# Maximum days before outcome_date that a signal snapshot is still usable
MAX_LOOKBACK_DAYS: int = 90


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Signal pivoting
# ---------------------------------------------------------------------------

def _pivot_signals(
    rows: List[Dict[str, Any]],
) -> Dict[str, Dict[date, Dict[str, Any]]]:
    """Pivot flat signal rows into {account_uuid: {signal_date: {key: value}}}.

    The "extra" signal key contains a JSON blob — its sub-fields are unpacked
    with an ``extra_`` prefix so they appear as first-class features.
    """
    pivot: Dict[str, Dict[date, Dict[str, Any]]] = {}
    for row in rows:
        aid = row.get("account_id")
        key = row.get("signal_key")
        sig_date = _parse_date(row.get("signal_date"))
        if not aid or not key or sig_date is None:
            continue

        if aid not in pivot:
            pivot[aid] = {}
        if sig_date not in pivot[aid]:
            pivot[aid][sig_date] = {}

        if key == "extra":
            try:
                extra = json.loads(row.get("signal_text") or "{}")
                for ek, ev in extra.items():
                    pivot[aid][sig_date][f"extra_{ek}"] = ev
            except (json.JSONDecodeError, TypeError):
                pass
        else:
            val = row.get("signal_value")
            if val is None:
                val = row.get("signal_text")
            if val is not None:
                pivot[aid][sig_date][key] = val

    return pivot


# ---------------------------------------------------------------------------
# Snapshot selection
# ---------------------------------------------------------------------------

def _snapshot_before(
    snapshots: Dict[date, Dict[str, Any]],
    outcome_date: date,
    max_lookback: int = MAX_LOOKBACK_DAYS,
) -> Tuple[Optional[date], Optional[Dict[str, Any]]]:
    """Return (date, snapshot) for the snapshot closest to but before outcome_date.

    Only considers snapshots within the ``max_lookback`` day window to avoid
    using stale features that pre-date the churn event by too long.
    Returns (None, None) when no qualifying snapshot exists.
    """
    cutoff = outcome_date - timedelta(days=max_lookback)
    candidates = [
        d for d in snapshots if d < outcome_date and d >= cutoff
    ]
    if not candidates:
        return None, None
    best = max(candidates)
    return best, snapshots[best]


# ---------------------------------------------------------------------------
# Trend / delta features
# ---------------------------------------------------------------------------

_TREND_KEYS = [
    "monthly_logins",
    "nps_score",
    "support_tickets",
    "days_until_renewal",
]


def _trend_features(
    snapshots: Dict[date, Dict[str, Any]],
    reference_date: date,
    window_days: int = 60,
) -> Dict[str, float]:
    """Compute per-30-day rate of change for key signals over ``window_days``.

    Requires at least two snapshots within the window — returns an empty dict
    when insufficient history exists (features simply absent from the row;
    median imputation in ``prepare_features`` handles them at train time).
    """
    if len(snapshots) < 2:
        return {}

    cutoff = reference_date - timedelta(days=window_days)
    window_dates = sorted(d for d in snapshots if cutoff <= d <= reference_date)
    if len(window_dates) < 2:
        return {}

    earliest_date = window_dates[0]
    days_span = (reference_date - earliest_date).days
    if days_span == 0:
        return {}

    earliest = snapshots[earliest_date]
    latest = snapshots[reference_date] if reference_date in snapshots else snapshots[max(window_dates)]

    trends: Dict[str, float] = {}
    for key in _TREND_KEYS:
        e_val = earliest.get(key)
        l_val = latest.get(key)
        if e_val is None or l_val is None:
            continue
        try:
            delta = (float(l_val) - float(e_val)) / days_span * 30  # per 30 days
            trends[f"delta_{key}"] = round(delta, 4)
        except (TypeError, ValueError):
            pass

    return trends


# ---------------------------------------------------------------------------
# Feature row construction
# ---------------------------------------------------------------------------

def _build_row(
    account: Dict[str, Any],
    snapshot: Dict[str, Any],
    trend: Dict[str, float],
    snapshot_date: date,
    churned: int,
    label_source: str,
) -> Dict[str, Any]:
    """Assemble one training row from account metadata + signal snapshot."""
    meta = account.get("metadata") or {}
    seats_raw = meta.get("seats") or snapshot.get("seats")

    row: Dict[str, Any] = {
        # Required by ModuleConfig (id + timestamp + label)
        "account_id": account.get("external_id") or account.get("id"),
        "snapshot_date": snapshot_date.isoformat(),
        "churned": churned,

        # Account-level features
        "arr": account.get("arr"),
        "plan": meta.get("plan"),
        "seats": seats_raw,
        "industry": meta.get("industry"),
        "company_size": meta.get("company_size"),

        # Point-in-time signal features
        "monthly_logins": snapshot.get("monthly_logins"),
        "support_tickets": snapshot.get("support_tickets"),
        "nps_score": snapshot.get("nps_score"),
        "days_since_last_login": snapshot.get("days_since_last_login"),
        "days_until_renewal": snapshot.get("days_until_renewal"),
        "auto_renew_flag": snapshot.get("auto_renew_flag"),
        "contract_months_remaining": snapshot.get("contract_months_remaining"),
        "renewal_status": snapshot.get("renewal_status"),

        # CRM-extra fields (unpacked from the "extra" JSON blob)
        "contact_count": snapshot.get("extra_contact_count"),
        "deal_count": snapshot.get("extra_deal_count"),
        "days_since_last_activity": snapshot.get("extra_days_since_last_activity"),

        # Internal metadata — stripped before passing to train_model()
        "label_source": label_source,
    }

    # Derived ratio features (engagement per seat; normalizes for company size)
    try:
        seats = float(seats_raw)
        if seats > 0:
            logins = snapshot.get("monthly_logins")
            tickets = snapshot.get("support_tickets")
            if logins is not None:
                row["login_rate_per_seat"] = round(float(logins) / seats, 4)
            if tickets is not None:
                row["ticket_rate_per_seat"] = round(float(tickets) / seats, 4)
    except (TypeError, ValueError):
        pass

    # Trend features from historical snapshots
    row.update(trend)

    return row


# ---------------------------------------------------------------------------
# Supabase data fetchers
# ---------------------------------------------------------------------------

def _fetch_all_signals(sb: Any, tenant_id: str, account_ids: Set[str]) -> List[Dict[str, Any]]:
    """Fetch all signal rows for the given account UUIDs (all dates, ascending).

    Paginates in two dimensions to handle large datasets without hitting
    Supabase's single-query row limits:
      - Outer loop: batches of ACCOUNT_BATCH_SIZE account UUIDs (IN clause)
      - Inner loop: pages of PAGE_SIZE rows within each account batch

    At 6k accounts × 10 signals × 30 daily snapshots ≈ 1.8M rows, a single
    200k-row query would silently truncate results. This approach scales to
    millions of rows.
    """
    ACCOUNT_BATCH_SIZE = 200  # keep IN clause well under Supabase URL length limits
    PAGE_SIZE = 10_000        # rows per Supabase paginated request

    all_rows: List[Dict[str, Any]] = []
    account_list = list(account_ids)

    for i in range(0, len(account_list), ACCOUNT_BATCH_SIZE):
        batch_ids = account_list[i: i + ACCOUNT_BATCH_SIZE]
        offset = 0

        while True:
            try:
                res = (
                    sb.table("account_signals_daily")
                    .select("account_id, signal_key, signal_value, signal_text, signal_date")
                    .eq("tenant_id", tenant_id)
                    .in_("account_id", batch_ids)
                    .order("signal_date", desc=False)
                    .range(offset, offset + PAGE_SIZE - 1)
                    .execute()
                )
            except Exception as exc:
                logger.warning(
                    "[crm_train] _fetch_all_signals batch %d-%d error: %s",
                    i, i + ACCOUNT_BATCH_SIZE, exc,
                )
                break

            if not res.data:
                break

            all_rows.extend(res.data)

            if len(res.data) < PAGE_SIZE:
                break  # Last page for this batch
            offset += PAGE_SIZE

    logger.info("[crm_train] fetched %d signal rows for %d accounts", len(all_rows), len(account_ids))
    return all_rows


def _fetch_outcomes(
    sb: Any, tenant_id: str, account_ids: Set[str]
) -> Dict[str, Dict[str, Any]]:
    """Return {account_uuid: outcome_row} keeping only the latest outcome per account."""
    try:
        res = (
            sb.table("account_outcomes")
            .select("account_id, outcome_type, effective_date, source")
            .eq("tenant_id", tenant_id)
            .order("effective_date", desc=True)
            .limit(50000)
            .execute()
        )
        if not res.data:
            return {}
        seen: Dict[str, Dict[str, Any]] = {}
        for row in res.data:
            aid = row.get("account_id")
            if aid and aid in account_ids and aid not in seen:
                seen[aid] = row
        return seen
    except Exception as exc:
        logger.warning("[crm_train] _fetch_outcomes error: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_crm_training_dataset(
    tenant_id: str,
    source: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Build a training-ready DataFrame from CRM data in Supabase.

    Parameters
    ----------
    tenant_id : str
        Supabase tenant UUID.
    source : str
        CRM provider name — "hubspot" or "salesforce".

    Returns
    -------
    df : pd.DataFrame
        Training DataFrame with ``churned`` label column.
        The ``label_source`` column indicates "primary" (from account_outcomes)
        or "heuristic" (assumed retained, no outcome record).
        **Callers must drop ``label_source`` before passing to train_model().**
    stats : dict
        Labeling statistics for sufficiency checks and UI display.
    """
    from app.storage.db import get_client
    from app.storage import repo

    sb = get_client()

    # ── 1. Accounts for this source ──────────────────────────────────────────
    accounts = repo.list_accounts(source=source, limit=50000, tenant_id=tenant_id)
    if not accounts:
        return pd.DataFrame(), {"error": "no_accounts", "account_count": 0}

    account_by_uuid = {a["id"]: a for a in accounts if a.get("id")}
    account_uuid_set: Set[str] = set(account_by_uuid)

    logger.info("[crm_train] source=%s accounts=%d", source, len(accounts))

    # ── 2. Full signal history for these accounts ────────────────────────────
    all_signal_rows = _fetch_all_signals(sb, tenant_id, account_uuid_set)
    pivot = _pivot_signals(all_signal_rows)

    logger.info("[crm_train] accounts with signal history: %d", len(pivot))

    # ── 3. Outcomes (latest per account, filtered to this source's accounts) ─
    outcome_by_uuid = _fetch_outcomes(sb, tenant_id, account_uuid_set)

    logger.info("[crm_train] outcome records for source: %d", len(outcome_by_uuid))

    # ── 4. Build training rows ───────────────────────────────────────────────
    rows: List[Dict[str, Any]] = []
    primary_labeled: Set[str] = set()

    # 4a. Primary labels — verified outcomes from account_outcomes
    for aid, outcome in outcome_by_uuid.items():
        outcome_type = outcome.get("outcome_type")
        if outcome_type not in ("churned", "renewed"):
            continue  # "expanded" not used for churn label

        effective_date = _parse_date(outcome.get("effective_date"))
        account = account_by_uuid.get(aid)
        if account is None or effective_date is None:
            continue

        snapshots = pivot.get(aid, {})

        if snapshots:
            snap_date, snapshot = _snapshot_before(snapshots, effective_date)
        else:
            snap_date, snapshot = None, None

        if snapshot is None:
            # No pre-outcome snapshot found — fall back to latest or empty
            if snapshots:
                snap_date = max(snapshots.keys())
                snapshot = snapshots[snap_date]
            else:
                snap_date = effective_date
                snapshot = {}

        trend = _trend_features(snapshots, snap_date) if snapshots else {}
        churned = 1 if outcome_type == "churned" else 0

        rows.append(_build_row(account, snapshot, trend, snap_date, churned, "primary"))
        primary_labeled.add(aid)

    # 4b. Heuristic labels — active accounts with no outcome (assumed retained)
    heuristic_count = 0
    for acct in accounts:
        aid = acct.get("id")
        if not aid or aid in primary_labeled:
            continue

        snapshots = pivot.get(aid, {})
        if not snapshots:
            continue  # Skip accounts with zero signal history

        latest_date = max(snapshots.keys())
        snapshot = snapshots[latest_date]
        trend = _trend_features(snapshots, latest_date)

        rows.append(_build_row(acct, snapshot, trend, latest_date, 0, "heuristic"))
        heuristic_count += 1

    if not rows:
        return pd.DataFrame(), {
            "error": "no_training_rows",
            "account_count": len(accounts),
            "outcome_count": len(outcome_by_uuid),
            "accounts_with_signals": len(pivot),
        }

    df = pd.DataFrame(rows)

    # Compute stats
    primary_churned = int(((df["label_source"] == "primary") & (df["churned"] == 1)).sum())
    primary_retained = int(((df["label_source"] == "primary") & (df["churned"] == 0)).sum())
    total_churned = int((df["churned"] == 1).sum())
    total_retained = int((df["churned"] == 0).sum())

    stats: Dict[str, Any] = {
        "account_count": len(accounts),
        "total_rows": len(df),
        "total_churned": total_churned,
        "total_retained": total_retained,
        "primary_churned": primary_churned,
        "primary_retained": primary_retained,
        "heuristic_retained": heuristic_count,
        "accounts_with_signals": len(pivot),
        "accounts_with_outcomes": len(primary_labeled),
    }

    logger.info(
        "[crm_train] dataset built: %d rows, %d churned (primary=%d), %d retained",
        len(df), total_churned, primary_churned, total_retained,
    )

    return df, stats


def check_data_sufficiency(
    df: pd.DataFrame,
    stats: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    """Check whether the dataset is large and balanced enough to train.

    Returns
    -------
    ok : bool
    message : str
        Human-readable explanation; empty string when ok=True.
    stats : dict
        The input stats dict (passed through for convenience).
    """
    if df.empty or "error" in stats:
        err = stats.get("error", "unknown")
        if err == "no_accounts":
            return False, (
                "No accounts found. Sync your CRM integration first."
            ), stats
        if err == "no_training_rows":
            return False, (
                f"{stats.get('account_count', 0)} accounts found but no training rows could "
                "be constructed — accounts likely have no signal history."
            ), stats
        return False, "No training data available.", stats

    total = stats.get("total_rows", 0)
    churned = stats.get("total_churned", 0)
    retained = stats.get("total_retained", 0)
    primary_churned = stats.get("primary_churned", 0)

    issues: List[str] = []

    if primary_churned == 0:
        issues.append(
            "No verified churned accounts found. Open the Accounts page and mark "
            "at least one account as 'Churned' to provide ground-truth labels."
        )

    if churned < MIN_POSITIVE_LABELED:
        needed = MIN_POSITIVE_LABELED - churned
        issues.append(
            f"Need {MIN_POSITIVE_LABELED} churned examples — have {churned}. "
            f"Mark {needed} more account(s) as Churned."
        )

    if retained < MIN_NEGATIVE_LABELED:
        issues.append(
            f"Need {MIN_NEGATIVE_LABELED} retained examples — have {retained}."
        )

    if total < MIN_TOTAL_LABELED:
        issues.append(
            f"Need at least {MIN_TOTAL_LABELED} labeled rows — have {total}."
        )

    if issues:
        return False, " | ".join(issues), stats

    return True, "Data sufficient for training.", stats

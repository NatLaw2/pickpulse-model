"""Schema mapping engine — alias-based column detection for flexible CSV ingestion."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
NONE = "NONE"


# ---------------------------------------------------------------------------
# Canonical field definitions
# ---------------------------------------------------------------------------
@dataclass
class CanonicalField:
    name: str
    required_for_training: bool = False   # block training if absent
    required_for_analysis: bool = False   # block all analysis if absent
    label_column: bool = False            # the churn label
    display_only: bool = False            # never encoded for model
    derivable_from: List[str] = field(default_factory=list)
    description: str = ""


CANONICAL_SCHEMA: Dict[str, CanonicalField] = {
    "account_id": CanonicalField(
        name="account_id",
        required_for_training=True,
        required_for_analysis=True,
        description="Unique account/customer identifier",
    ),
    "snapshot_date": CanonicalField(
        name="snapshot_date",
        required_for_training=False,   # preferred; absent → random split with warning
        required_for_analysis=False,
        description="Date this record was captured (enables time-based train/val split)",
    ),
    "churned": CanonicalField(
        name="churned",
        required_for_training=True,
        label_column=True,
        description="Churn outcome: 0=retained, 1=churned. Required for supervised training.",
    ),
    "arr": CanonicalField(
        name="arr",
        derivable_from=["mrr"],
        description="Annual recurring revenue",
    ),
    "mrr": CanonicalField(
        name="mrr",
        derivable_from=["arr"],
        description="Monthly recurring revenue (arr derived from this if arr absent)",
    ),
    "renewal_date": CanonicalField(
        name="renewal_date",
        description="Contract renewal / expiry date",
    ),
    "days_until_renewal": CanonicalField(
        name="days_until_renewal",
        derivable_from=["renewal_date", "snapshot_date"],
        description="Days until contract renewal (derived from renewal_date if absent)",
    ),
    "contract_start_date": CanonicalField(
        name="contract_start_date",
        description="Contract or account inception date",
    ),
    "seats_purchased": CanonicalField(
        name="seats_purchased",
        description="Total seats / licenses purchased",
    ),
    "seats_active_30d": CanonicalField(
        name="seats_active_30d",
        description="Active seats in last 30 days",
    ),
    "login_days_30d": CanonicalField(
        name="login_days_30d",
        description="Days with logins in last 30 days",
    ),
    "support_tickets_30d": CanonicalField(
        name="support_tickets_30d",
        description="Support tickets submitted in last 30 days",
    ),
    "nps_score": CanonicalField(
        name="nps_score",
        description="Net Promoter Score",
    ),
    "plan_type": CanonicalField(
        name="plan_type",
        description="Subscription plan or tier",
    ),
    "auto_renew_flag": CanonicalField(
        name="auto_renew_flag",
        description="Whether account is set to auto-renew (0/1)",
    ),
    # Display-only — mapped and stored but never encoded for model
    "company_name": CanonicalField(
        name="company_name",
        display_only=True,
        description="Account / company name (display only)",
    ),
    "csm_owner": CanonicalField(
        name="csm_owner",
        display_only=True,
        description="Assigned CSM (display only)",
    ),
    "industry": CanonicalField(
        name="industry",
        display_only=True,
        description="Account industry (display only for MVP)",
    ),
    "region": CanonicalField(
        name="region",
        display_only=True,
        description="Geographic region (display only for MVP)",
    ),
}


# ---------------------------------------------------------------------------
# Alias map — Tier 2 detection (curated synonyms per canonical field)
# ---------------------------------------------------------------------------
ALIAS_MAP: Dict[str, List[str]] = {
    "account_id": [
        "account_id", "accountid", "customer_id", "customerid",
        "client_id", "clientid", "org_id", "orgid", "company_id",
        "companyid", "tenant_id", "tenantid", "account_number",
        "cust_id", "custid", "subscriber_id", "subscriberid",
        "entity_id", "entityid", "uuid", "uid",
    ],
    "snapshot_date": [
        "snapshot_date", "snapshotdate", "record_date", "recorddate",
        "as_of_date", "asofdate", "report_date", "reportdate",
        "period_date", "perioddate", "cohort_date", "cohortdate",
        "eval_date", "observation_date", "data_date", "extract_date",
        "month_date", "period", "date", "month",
    ],
    "churned": [
        "churned", "churn", "is_churned", "ischurned",
        "canceled", "cancelled", "is_canceled", "iscanceled",
        "is_cancelled", "iscancelled", "churn_flag", "churned_flag",
        "did_churn", "attrited", "lost", "terminated",
        "contract_ended", "inactive",
    ],
    "arr": [
        "arr", "arr_usd", "annual_recurring_revenue",
        "annual_revenue", "arr_value", "contract_value",
        "acv", "annual_contract_value", "total_arr",
        "yearly_revenue",
    ],
    "mrr": [
        "mrr", "mrr_usd", "monthly_recurring_revenue",
        "monthly_revenue", "monthly_contract_value",
        "monthly_value",
    ],
    "renewal_date": [
        "renewal_date", "renewaldate", "contract_end",
        "contract_end_date", "contractenddate", "expiry_date",
        "expirydate", "expiration_date", "expirationdate",
        "next_renewal", "subscription_end", "subscription_end_date",
        "end_date", "enddate", "contract_expiry",
    ],
    "days_until_renewal": [
        "days_until_renewal", "daysuntilrenewal", "days_to_renewal",
        "daystorenewal", "renewal_days", "renewaldays",
        "days_remaining", "daysremaining", "days_to_contract_end",
        "days_to_expiry", "contract_days_remaining",
    ],
    "contract_start_date": [
        "contract_start_date", "contractstartdate", "start_date",
        "startdate", "contract_start", "account_start_date",
        "created_date", "createddate", "inception_date",
        "onboard_date", "signup_date",
    ],
    "seats_purchased": [
        "seats_purchased", "seatspurchased", "seats",
        "licenses", "license_count", "licensecount",
        "total_seats", "totalseats", "contracted_seats",
        "users_purchased",
    ],
    "seats_active_30d": [
        "seats_active_30d", "active_seats_30d", "active_users_30d",
        "mau", "mau_30", "active_seats", "active_users",
        "users_active_30d", "monthly_active_users",
        "active_licenses_30d",
    ],
    "login_days_30d": [
        "login_days_30d", "logindays30d", "logins_last_30",
        "logins_30d", "active_days_30", "login_count_30d",
        "sessions_30d", "dau_30", "monthly_logins",
        "logins", "login_count", "sessions",
    ],
    "support_tickets_30d": [
        "support_tickets_30d", "tickets_30d", "support_tickets",
        "ticket_count_30d", "ticket_count", "tickets",
        "cases_30d", "support_cases", "cases",
        "incidents_30d", "support_incidents",
    ],
    "nps_score": [
        "nps_score", "npsscore", "nps", "satisfaction",
        "csat", "csat_score", "net_promoter_score",
        "satisfaction_score",
    ],
    "plan_type": [
        "plan_type", "plantype", "plan", "tier", "subscription",
        "plan_name", "planname", "product", "product_tier",
        "subscription_tier", "package", "plan_tier",
    ],
    "auto_renew_flag": [
        "auto_renew_flag", "autorenewflag", "auto_renew",
        "autorenew", "auto_renewal", "autorenewal",
        "auto_renew_enabled", "is_auto_renew",
    ],
    "company_name": [
        "company_name", "companyname", "account_name",
        "accountname", "customer_name", "customername",
        "client_name", "clientname", "organization",
        "org_name", "orgname",
    ],
    "csm_owner": [
        "csm_owner", "csmowner", "csm", "account_owner",
        "accountowner", "customer_success_manager",
        "csm_name", "assigned_csm",
    ],
    "industry": [
        "industry", "vertical", "sector", "market",
        "industry_name", "business_type",
    ],
    "region": [
        "region", "geography", "geo", "country",
        "territory", "market_region",
    ],
}


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------
@dataclass
class MappingSuggestion:
    suggested: Dict[str, Optional[str]]          # canonical → source_col or None
    confidence: Dict[str, str]                   # canonical → HIGH|MEDIUM|LOW|NONE
    method: Dict[str, str]                       # canonical → exact|alias|heuristic|none
    unmapped_source_cols: List[str]              # source cols not claimed by any canonical
    missing_required_for_training: List[str]     # required canonical fields not found
    missing_required_for_analysis: List[str]     # analysis-required fields not found
    source_columns: List[str]                    # all source columns


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def _norm(name: str) -> str:
    """Strip non-alphanumeric and lowercase for Tier 1b matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def suggest_mapping(df: pd.DataFrame) -> MappingSuggestion:
    """
    Suggest canonical → source column mappings.

    Two-pass approach to prevent heuristics from stealing columns that
    a later alias lookup would claim:

    Pass 1 (all canonicals): Tier 1a exact + Tier 1b normalized + Tier 2 alias
    Pass 2 (unmatched only): Tier 3 value-distribution heuristics
    """
    source_columns = list(df.columns)
    lower_to_src: Dict[str, str] = {c.lower().strip(): c for c in source_columns}
    norm_to_src: Dict[str, str] = {_norm(c): c for c in source_columns}

    claimed: set = set()
    suggested: Dict[str, Optional[str]] = {}
    confidence: Dict[str, str] = {}
    method: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Pass 1: alias-based matching for all canonical fields
    # ------------------------------------------------------------------
    for canonical, aliases in ALIAS_MAP.items():
        match: Optional[str] = None
        conf = NONE
        meth = "none"

        for alias in aliases:
            # Tier 1a: exact lowercase match
            candidate = lower_to_src.get(alias.lower())
            if candidate and candidate not in claimed:
                match = candidate
                conf = HIGH if alias == canonical else MEDIUM
                meth = "exact" if alias == canonical else "alias"
                break

            # Tier 1b: normalized match
            candidate = norm_to_src.get(_norm(alias))
            if candidate and candidate not in claimed:
                match = candidate
                conf = HIGH if _norm(alias) == _norm(canonical) else MEDIUM
                meth = "exact" if _norm(alias) == _norm(canonical) else "alias"
                break

        if match:
            claimed.add(match)

        suggested[canonical] = match
        confidence[canonical] = conf
        method[canonical] = meth

    # ------------------------------------------------------------------
    # Pass 2: heuristic detection only for canonicals still unmatched
    # ------------------------------------------------------------------
    for canonical in ALIAS_MAP:
        if suggested.get(canonical) is not None:
            continue  # already matched in Pass 1
        result = _heuristic_match(canonical, df, claimed)
        if result:
            match, conf, meth = result
            claimed.add(match)
            suggested[canonical] = match
            confidence[canonical] = conf
            method[canonical] = meth

    unmapped = [c for c in source_columns if c not in claimed]

    missing_training = [
        f for f, fd in CANONICAL_SCHEMA.items()
        if fd.required_for_training and suggested.get(f) is None
    ]
    missing_analysis = [
        f for f, fd in CANONICAL_SCHEMA.items()
        if fd.required_for_analysis and suggested.get(f) is None
    ]

    return MappingSuggestion(
        suggested=suggested,
        confidence=confidence,
        method=method,
        unmapped_source_cols=unmapped,
        missing_required_for_training=missing_training,
        missing_required_for_analysis=missing_analysis,
        source_columns=source_columns,
    )


def _heuristic_match(
    canonical: str,
    df: pd.DataFrame,
    claimed: set,
) -> Optional[Tuple[str, str, str]]:
    """Tier 3: infer column semantics from value distribution."""
    unclaimed = [c for c in df.columns if c not in claimed]
    if not unclaimed:
        return None

    if canonical == "churned":
        binary_value_sets = [
            {"0", "1"}, {"0.0", "1.0"}, {"true", "false"},
            {"yes", "no"}, {"churned", "retained"}, {"active", "inactive"},
            {"canceled", "active"}, {"cancelled", "active"},
            {"1", "0", "true", "false"},
        ]
        for col in unclaimed:
            series = df[col].dropna()
            if len(series) == 0:
                continue
            unique_vals = set(series.astype(str).str.lower().str.strip().unique())
            for bs in binary_value_sets:
                if unique_vals <= bs and len(unique_vals) >= 2:
                    return (col, LOW, "heuristic")

    elif canonical == "snapshot_date":
        for col in unclaimed:
            series = df[col].dropna()
            if len(series) == 0:
                continue
            # Only attempt date parsing on string/object columns — integers
            # are valid Timestamps but are almost never actual date columns.
            if pd.api.types.is_numeric_dtype(series):
                continue
            try:
                sample = series.head(20)
                pd.to_datetime(sample, errors="raise")
                return (col, LOW, "heuristic")
            except (ValueError, TypeError):
                pass

    elif canonical == "arr":
        for col in unclaimed:
            series = df[col].dropna()
            if pd.api.types.is_numeric_dtype(series):
                if series.min() >= 0 and series.median() > 500:
                    return (col, LOW, "heuristic")

    elif canonical == "account_id":
        for col in unclaimed:
            series = df[col].dropna()
            # Nearly all unique → likely an ID column
            if len(series) > 0 and series.nunique() >= len(series) * 0.9:
                return (col, LOW, "heuristic")

    return None


def mapping_suggestion_to_dict(s: MappingSuggestion) -> dict:
    """Serialize MappingSuggestion for JSON API response."""
    return {
        "suggested": s.suggested,
        "confidence": s.confidence,
        "method": s.method,
        "unmapped_source_cols": s.unmapped_source_cols,
        "missing_required_for_training": s.missing_required_for_training,
        "missing_required_for_analysis": s.missing_required_for_analysis,
        "source_columns": s.source_columns,
    }

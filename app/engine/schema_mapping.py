"""
Schema mapping engine — alias-based column detection for flexible CSV ingestion.

Detection runs in two passes to prevent heuristics from stealing columns
that a later alias lookup would claim:

  Pass 1 (all canonicals): Tier 1a exact → Tier 1b normalised → Tier 2 CRM alias
  Pass 2 (unmatched only): Tier 3 value-distribution heuristics

Confidence policy
-----------------
  HIGH   — source column name exactly equals the canonical name (or its
            normalised form).
  MEDIUM — source column name matches a curated alias from the global or
            CRM-specific packs (non-ambiguous).
  LOW    — heuristic-only match OR alias marked requires_confirmation.
  NONE   — no match found.

requires_confirmation=True means the match is known to be ambiguous in
the CRM context (e.g. Salesforce StageName, HubSpot dealstage).  These
are always downgraded to LOW and the UI will never auto-populate them;
the user must explicitly choose the mapping.

This deliberately prevents the class of bug where a field like
exec_sponsor_present (binary 0/1) is silently pre-selected as churned.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .crm_aliases import (
    MERGED_ALIAS_MAP,
    REQUIRES_CONFIRMATION_NORMS,
    CHURN_POSITIVE_VALUES,
    CHURN_NEGATIVE_VALUES,
)


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
# ALIAS_MAP — derived from the CRM pack system (single source of truth).
# Kept as a module-level constant so existing importers that reference
# ALIAS_MAP directly (e.g. the API canonical-schema endpoint) keep working.
# ---------------------------------------------------------------------------
ALIAS_MAP: Dict[str, List[str]] = MERGED_ALIAS_MAP


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------
@dataclass
class MappingSuggestion:
    suggested: Dict[str, Optional[str]]          # canonical → source_col or None
    confidence: Dict[str, str]                   # canonical → HIGH|MEDIUM|LOW|NONE
    method: Dict[str, str]                       # canonical → exact|alias|alias|confirm|heuristic|none
    requires_confirmation: Dict[str, bool]       # canonical → True if user must confirm
    unmapped_source_cols: List[str]              # source cols not claimed by any canonical
    missing_required_for_training: List[str]     # required canonical fields not found
    missing_required_for_analysis: List[str]     # analysis-required fields not found
    source_columns: List[str]                    # all source columns


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def _norm(name: str) -> str:
    """Strip non-alphanumeric and lowercase for normalised matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def suggest_mapping(df: pd.DataFrame) -> MappingSuggestion:
    """
    Suggest canonical → source column mappings.

    Two-pass approach prevents heuristics from stealing columns that a
    later alias lookup would claim:

    Pass 1 (all canonicals): Tier 1a exact + Tier 1b normalised + Tier 2 alias
    Pass 2 (unmatched only): Tier 3 value-distribution heuristics
    """
    source_columns = list(df.columns)
    lower_to_src: Dict[str, str] = {c.lower().strip(): c for c in source_columns}
    norm_to_src: Dict[str, str] = {_norm(c): c for c in source_columns}

    claimed: set = set()
    suggested: Dict[str, Optional[str]] = {}
    confidence: Dict[str, str] = {}
    method: Dict[str, str] = {}
    requires_confirmation: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Pass 1: alias-based matching for all canonical fields
    # ------------------------------------------------------------------
    for canonical, aliases in ALIAS_MAP.items():
        match: Optional[str] = None
        conf = NONE
        meth = "none"
        needs_confirm = False
        matched_alias: Optional[str] = None

        for alias in aliases:
            # Tier 1a: exact lowercase match
            candidate = lower_to_src.get(alias.lower())
            if candidate and candidate not in claimed:
                match = candidate
                matched_alias = alias
                conf = HIGH if alias.lower() == canonical.lower() else MEDIUM
                meth = "exact" if alias.lower() == canonical.lower() else "alias"
                break

            # Tier 1b: normalised match
            candidate = norm_to_src.get(_norm(alias))
            if candidate and candidate not in claimed:
                match = candidate
                matched_alias = alias
                conf = HIGH if _norm(alias) == _norm(canonical) else MEDIUM
                meth = "exact" if _norm(alias) == _norm(canonical) else "alias"
                break

        # Check if the matched alias requires user confirmation
        if match and matched_alias:
            rc_norms = REQUIRES_CONFIRMATION_NORMS.get(canonical, frozenset())
            if _norm(matched_alias) in rc_norms:
                needs_confirm = True
                conf = LOW          # force LOW → UI won't auto-populate
                meth = "alias|confirm"

        if match:
            claimed.add(match)

        suggested[canonical] = match
        confidence[canonical] = conf
        method[canonical] = meth
        requires_confirmation[canonical] = needs_confirm

    # ------------------------------------------------------------------
    # Pass 2: heuristic detection only for canonicals still unmatched
    # ------------------------------------------------------------------
    for canonical in ALIAS_MAP:
        if suggested.get(canonical) is not None:
            continue  # already matched in Pass 1

        result = _heuristic_match(canonical, df, claimed)
        if result:
            match, conf, meth, needs_confirm = result
            claimed.add(match)
            suggested[canonical] = match
            confidence[canonical] = conf
            method[canonical] = meth
            requires_confirmation[canonical] = needs_confirm

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
        requires_confirmation=requires_confirmation,
        unmapped_source_cols=unmapped,
        missing_required_for_training=missing_training,
        missing_required_for_analysis=missing_analysis,
        source_columns=source_columns,
    )


def _heuristic_match(
    canonical: str,
    df: pd.DataFrame,
    claimed: set,
) -> Optional[Tuple[str, str, str, bool]]:
    """
    Tier 3: infer column semantics from value distribution.

    Returns (source_col, confidence, method, requires_confirmation) or None.

    Policy:
    - All heuristic matches are LOW confidence.
    - Binary flag matches for 'churned' do NOT require confirmation (they are
      already LOW — the existing UI behaviour prevents auto-population).
    - Value-vocabulary matches (e.g. a column with "Closed Lost" / "Closed Won"
      values) DO require confirmation because the column may not be a true label.
    """
    unclaimed = [c for c in df.columns if c not in claimed]
    if not unclaimed:
        return None

    if canonical == "churned":
        # ------------------------------------------------------------------
        # Tier 3a: binary value-set detection (original behaviour, preserved)
        # ------------------------------------------------------------------
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
                    # Binary flag detected — LOW confidence, no confirmation
                    # required (already handled by LOW preventing auto-populate)
                    return (col, LOW, "heuristic", False)

        # ------------------------------------------------------------------
        # Tier 3b: churn vocabulary detection
        # A column whose values overlap with known churn-positive AND
        # churn-negative vocabulary is a plausible churn indicator, but the
        # match is inferred from values — not from field name — so it always
        # requires_confirmation.
        # ------------------------------------------------------------------
        for col in unclaimed:
            series = df[col].dropna()
            if len(series) == 0:
                continue
            # Skip purely numeric columns — churn vocabulary is text-based.
            if pd.api.types.is_numeric_dtype(series):
                continue
            unique_lower = {v.lower().strip() for v in series.astype(str).unique()}
            has_positive = bool(unique_lower & CHURN_POSITIVE_VALUES)
            has_negative = bool(unique_lower & CHURN_NEGATIVE_VALUES)
            if has_positive and has_negative:
                return (col, LOW, "heuristic|values", True)

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
                return (col, LOW, "heuristic", False)
            except (ValueError, TypeError):
                pass

    elif canonical == "arr":
        for col in unclaimed:
            series = df[col].dropna()
            if pd.api.types.is_numeric_dtype(series):
                if series.min() >= 0 and series.median() > 500:
                    return (col, LOW, "heuristic", False)

    elif canonical == "account_id":
        for col in unclaimed:
            series = df[col].dropna()
            # Nearly all unique → likely an ID column
            if len(series) > 0 and series.nunique() >= len(series) * 0.9:
                return (col, LOW, "heuristic", False)

    return None


def mapping_suggestion_to_dict(s: MappingSuggestion) -> dict:
    """Serialize MappingSuggestion for JSON API response."""
    return {
        "suggested": s.suggested,
        "confidence": s.confidence,
        "method": s.method,
        "requires_confirmation": s.requires_confirmation,
        "unmapped_source_cols": s.unmapped_source_cols,
        "missing_required_for_training": s.missing_required_for_training,
        "missing_required_for_analysis": s.missing_required_for_analysis,
        "source_columns": s.source_columns,
    }

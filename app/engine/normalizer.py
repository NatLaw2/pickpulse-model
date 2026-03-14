"""Normalization layer — converts a raw DataFrame + confirmed mapping into canonical form."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .schema_mapping import CANONICAL_SCHEMA


# ---------------------------------------------------------------------------
# Truthy / falsy sets for binary coercion of the churned column.
#
# These are applied AFTER the user has confirmed a mapping, so values
# like "Closed Lost" (from a Salesforce StageName column) can be
# correctly coerced to 1.  The sets are a union of:
#   - Universal boolean representations (1/0, true/false, yes/no)
#   - Global churn vocabulary from the CRM alias packs
#   - CRM-specific churn values (Salesforce, HubSpot, Dynamics, Pipedrive)
# ---------------------------------------------------------------------------
_TRUTHY = {
    # Universal
    "1", "1.0", "true", "yes", "y", "t",
    # Direct churn labels
    "churned", "churn",
    # Cancellation variants
    "canceled", "cancelled",
    # Termination / loss
    "terminated", "lost", "left", "attrited", "deactivated",
    # Inactivity
    "inactive",
    # Non-renewal
    "non-renewed", "non_renewed", "nonrenewed", "non renewed",
    # CRM-specific: Salesforce StageName values
    "closed lost", "closed_lost", "closedlost",
    # CRM-specific: HubSpot dealstage / lifecyclestage
    "closedlost", "inactive_customer",
    # CRM-specific: Dynamics textual status
    "terminated",
    # Pipedrive
    "lost",
}
_FALSY = {
    # Universal
    "0", "0.0", "false", "no", "n", "f",
    # Retention labels
    "retained", "active", "renewing", "renewed", "healthy", "current",
    # CRM-specific: Salesforce StageName values
    "closed won", "closed_won", "closedwon",
    "active renewal",
    # Generic won/open
    "won", "open",
    # HubSpot lifecyclestage
    "customer", "evangelist", "opportunity",
    # Text "current customer"
    "current customer", "current_customer",
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class NormalizationResult:
    canonical_df: pd.DataFrame         # model-ready canonical columns
    display_meta: pd.DataFrame         # account_id + display-only columns
    derived_columns: List[str]         # columns computed during normalization
    coercion_log: List[str]            # type coercion decisions
    warnings: List[str]                # data quality notes
    confirmed_mappings: Dict[str, Optional[str]]  # stored for reuse


@dataclass
class ReadinessReport:
    mode: str                          # TRAINING_READY | TRAINING_DEGRADED | ANALYSIS_READY | PARTIAL | BLOCKED
    mode_reason: str
    required_mapped: Dict[str, bool]
    recommended_mapped: Dict[str, bool]
    derived_fields: List[str]
    usable_feature_count: int
    label_distribution: Optional[Dict[str, int]]
    split_strategy: str                # time_based | random | n/a
    warnings: List[str]
    improvements: List[str]
    normalized_preview: List[Dict[str, Any]]
    dataset_info: Dict[str, Any]


# ---------------------------------------------------------------------------
# Recommended fields for readiness scoring (ordered by predictive value)
# ---------------------------------------------------------------------------
_RECOMMENDED_FIELDS = [
    "arr", "mrr", "days_until_renewal", "renewal_date",
    "login_days_30d", "seats_purchased", "seats_active_30d",
    "support_tickets_30d", "plan_type", "nps_score",
    "contract_start_date", "auto_renew_flag",
]

# Fields that are modeling features (not display-only, not id/date/label)
_FEATURE_FIELDS = [
    "arr", "mrr", "days_until_renewal", "login_days_30d",
    "seats_purchased", "seats_active_30d", "support_tickets_30d",
    "nps_score", "plan_type", "auto_renew_flag",
    "contract_start_date",  # used to derive account_age_days feature
]


# ---------------------------------------------------------------------------
# Main normalization function
# ---------------------------------------------------------------------------
def normalize(
    raw_df: pd.DataFrame,
    confirmed_mappings: Dict[str, Optional[str]],
) -> NormalizationResult:
    """
    Transform a raw DataFrame into canonical form using the confirmed column mapping.

    Args:
        raw_df: The original uploaded DataFrame (raw column names).
        confirmed_mappings: { canonical_field: source_column_or_None }

    Returns:
        NormalizationResult with canonical_df and metadata.
    """
    derived_columns: List[str] = []
    coercion_log: List[str] = []
    warnings: List[str] = []

    # Build rename map: source_column → canonical_name (skip nulls)
    rename_map = {
        src: canonical
        for canonical, src in confirmed_mappings.items()
        if src is not None
    }

    # Select and rename mapped columns only
    available_src = [c for c in rename_map if c in raw_df.columns]
    work = raw_df[available_src].copy()
    work = work.rename(columns=rename_map)

    # ------------------------------------------------------------------
    # Type coercion
    # ------------------------------------------------------------------

    # churned → int 0/1
    if "churned" in work.columns:
        col = work["churned"]
        if pd.api.types.is_float_dtype(col):
            work["churned"] = col.round().fillna(0).astype(int)
            coercion_log.append("churned: float coerced to int")
        elif not pd.api.types.is_integer_dtype(col):
            # Handles object, str, StringDtype, bool, and any non-numeric type
            mapped = (
                col.astype(str).str.lower().str.strip()
                .map(lambda v: 1 if v in _TRUTHY else (0 if v in _FALSY else np.nan))
            )
            n_unknown = int(mapped.isna().sum())
            if n_unknown > 0:
                warnings.append(
                    f"churned: {n_unknown} values could not be coerced to 0/1 — treated as 0."
                )
            work["churned"] = mapped.fillna(0).astype(int)
            coercion_log.append("churned: text values coerced to 0/1")

    # auto_renew_flag → int 0/1
    if "auto_renew_flag" in work.columns:
        col = work["auto_renew_flag"]
        if not pd.api.types.is_integer_dtype(col) and not pd.api.types.is_float_dtype(col):
            work["auto_renew_flag"] = (
                col.astype(str).str.lower().str.strip()
                .map({"1": 1, "true": 1, "yes": 1, "0": 0, "false": 0, "no": 0})
                .fillna(0).astype(int)
            )
            coercion_log.append("auto_renew_flag: text coerced to 0/1")

    # Date columns → parse to datetime (keep as datetime for derivations, then drop)
    _date_cols = ["snapshot_date", "renewal_date", "contract_start_date"]
    parsed_dates: Dict[str, pd.Series] = {}
    for col in _date_cols:
        if col in work.columns:
            try:
                parsed_dates[col] = pd.to_datetime(work[col], errors="coerce")
                work[col] = parsed_dates[col]
                coercion_log.append(f"{col}: parsed as datetime")
            except Exception:
                warnings.append(f"{col}: could not parse as dates — column dropped")
                work = work.drop(columns=[col])

    # Numeric columns — coerce objects that should be numeric
    _numeric_candidates = [
        "arr", "mrr", "days_until_renewal", "seats_purchased",
        "seats_active_30d", "login_days_30d", "support_tickets_30d",
        "nps_score",
    ]
    for col in _numeric_candidates:
        if col in work.columns and work[col].dtype == object:
            work[col] = pd.to_numeric(work[col], errors="coerce")
            coercion_log.append(f"{col}: coerced to numeric")

    # ------------------------------------------------------------------
    # Derivations
    # ------------------------------------------------------------------

    # ARR ↔ MRR
    if "arr" not in work.columns and "mrr" in work.columns:
        work["arr"] = (pd.to_numeric(work["mrr"], errors="coerce") * 12).round(2)
        derived_columns.append("arr")
        coercion_log.append("arr: derived from mrr × 12")
    elif "mrr" not in work.columns and "arr" in work.columns:
        work["mrr"] = (pd.to_numeric(work["arr"], errors="coerce") / 12).round(2)
        derived_columns.append("mrr")

    # days_until_renewal from renewal_date − snapshot_date
    if "days_until_renewal" not in work.columns:
        rd = parsed_dates.get("renewal_date")
        sd = parsed_dates.get("snapshot_date")
        if rd is not None and sd is not None:
            work["days_until_renewal"] = (rd - sd).dt.days
            derived_columns.append("days_until_renewal")
            coercion_log.append("days_until_renewal: derived from renewal_date − snapshot_date")
        elif rd is not None and sd is None:
            # No snapshot date — derive relative to today
            today = pd.Timestamp.now().normalize()
            work["days_until_renewal"] = (rd - today).dt.days
            derived_columns.append("days_until_renewal")
            warnings.append(
                "days_until_renewal: derived relative to today (no snapshot_date). "
                "Values reflect current state, not historical."
            )

    # account_age_days from contract_start_date
    sd = parsed_dates.get("snapshot_date")
    csd = parsed_dates.get("contract_start_date")
    if csd is not None:
        ref = sd if sd is not None else pd.Timestamp.now().normalize()
        work["account_age_days"] = (ref - csd).dt.days.clip(lower=0)
        derived_columns.append("account_age_days")

    # Clamp: days_until_renewal can be negative (past renewal) — valid, keep as-is
    # Clamp: arr / mrr — negative values are data errors
    for col in ["arr", "mrr"]:
        if col in work.columns:
            n_neg = int((work[col] < 0).sum())
            if n_neg > 0:
                work[col] = work[col].clip(lower=0)
                warnings.append(f"{col}: {n_neg} negative values clamped to 0")

    # ------------------------------------------------------------------
    # Separate display-only columns
    # ------------------------------------------------------------------
    display_cols = ["account_id"] + [
        f for f, fd in CANONICAL_SCHEMA.items()
        if fd.display_only and f in work.columns
    ]
    display_meta = work[[c for c in display_cols if c in work.columns]].copy()

    # Drop display-only columns (except account_id) from modeling df
    modeling_drop = [
        f for f, fd in CANONICAL_SCHEMA.items()
        if fd.display_only and f in work.columns and f != "account_id"
    ]
    canonical_df = work.drop(columns=modeling_drop)

    # Drop raw date columns — they've served their purpose (derivations done)
    # Keep snapshot_date in canonical_df since train.py uses it for time-based split
    for col in ["renewal_date", "contract_start_date"]:
        if col in canonical_df.columns:
            canonical_df = canonical_df.drop(columns=[col])

    return NormalizationResult(
        canonical_df=canonical_df,
        display_meta=display_meta,
        derived_columns=derived_columns,
        coercion_log=coercion_log,
        warnings=warnings,
        confirmed_mappings=confirmed_mappings,
    )


# ---------------------------------------------------------------------------
# Readiness scoring
# ---------------------------------------------------------------------------
def compute_readiness(
    canonical_df: pd.DataFrame,
    derived_columns: List[str],
    warnings: List[str],
    n_rows: int,
    filename: str,
    loaded_at: str,
) -> ReadinessReport:
    """Determine what operations are possible with this normalized dataset."""
    cols = set(canonical_df.columns)

    # Required field check
    required_mapped = {
        "account_id": "account_id" in cols,
        "snapshot_date": "snapshot_date" in cols,
        "churned": "churned" in cols,
    }
    recommended_mapped = {f: f in cols for f in _RECOMMENDED_FIELDS}

    # Usable feature count (numeric/categorical model inputs, not id/date/label)
    feature_cols = [
        c for c in cols
        if c not in {"account_id", "snapshot_date", "churned"}
    ]
    usable_feature_count = len(feature_cols)

    # Label distribution
    label_distribution: Optional[Dict[str, int]] = None
    if "churned" in cols:
        dist = canonical_df["churned"].value_counts().to_dict()
        label_distribution = {str(int(k)): int(v) for k, v in dist.items()}

    # Split strategy
    if "snapshot_date" in cols:
        split_strategy = "time_based"
    else:
        split_strategy = "random" if "churned" in cols else "n/a"

    # Mode determination
    report_warnings = list(warnings)
    improvements: List[str] = []

    if not required_mapped["account_id"]:
        mode = "BLOCKED"
        mode_reason = "account_id is required but could not be mapped. Cannot identify accounts."
    elif usable_feature_count < 2:
        mode = "BLOCKED"
        mode_reason = (
            f"Only {usable_feature_count} usable feature(s) found after mapping. "
            "Need at least 2 to produce meaningful analysis."
        )
    elif not required_mapped["churned"]:
        mode = "ANALYSIS_READY"
        mode_reason = (
            "No churn label found. Supervised model training is unavailable. "
            "Behavioral analysis mode is available."
        )
    else:
        # Has churned label — check quality
        if label_distribution:
            n_classes = len(label_distribution)
            if n_classes < 2:
                mode = "BLOCKED"
                mode_reason = (
                    f"Churn label has only one unique value ({list(label_distribution.keys())[0]}). "
                    "Need both churned and retained examples to train a classifier."
                )
            elif not required_mapped["snapshot_date"]:
                mode = "TRAINING_DEGRADED"
                mode_reason = (
                    "Training is available but snapshot_date is absent. "
                    "Using random train/val split — metrics may be slightly optimistic."
                )
                report_warnings.append(
                    "No date column found. Training will use a random split instead of "
                    "time-based. For production-grade metrics, include a snapshot date."
                )
            else:
                mode = "TRAINING_READY"
                mode_reason = "Dataset is ready for supervised churn model training."
        else:
            mode = "BLOCKED"
            mode_reason = "Churn label found but has no usable values."

    # Improvement suggestions
    missing_recommended = [f for f, mapped in recommended_mapped.items() if not mapped]
    improvement_map = {
        "arr": "Adding ARR/MRR would enable revenue-weighted risk scoring and Revenue Impact tracking.",
        "mrr": "Adding MRR would enable ARR derivation and revenue-weighted analysis.",
        "renewal_date": "Adding renewal_date would enable renewal window risk signals.",
        "days_until_renewal": "Adding days_until_renewal would enable renewal urgency features.",
        "login_days_30d": "Adding login activity data would add a strong behavioral churn signal.",
        "seats_purchased": "Adding seat data would enable utilization rate features.",
        "seats_active_30d": "Adding active seat data would enable seat utilization rate.",
        "support_tickets_30d": "Adding support ticket volume is a reliable leading churn indicator.",
        "plan_type": "Adding plan/tier data enables segment-level analysis.",
        "nps_score": "Adding NPS data provides a satisfaction signal.",
        "contract_start_date": "Adding contract start date enables account tenure features.",
        "auto_renew_flag": "Adding auto-renew flag improves renewal risk modeling.",
    }
    for f in missing_recommended:
        if f in improvement_map:
            improvements.append(improvement_map[f])

    # 5-row preview
    preview_df = canonical_df.head(5).copy()
    # Convert dates to strings for JSON serialization
    for col in preview_df.columns:
        if pd.api.types.is_datetime64_any_dtype(preview_df[col]):
            preview_df[col] = preview_df[col].dt.strftime("%Y-%m-%d")
    normalized_preview = preview_df.where(pd.notna(preview_df), None).to_dict(orient="records")

    dataset_info = {
        "name": filename,
        "rows": n_rows,
        "columns": len(canonical_df.columns),
        "is_demo": False,
        "loaded_at": loaded_at,
    }

    return ReadinessReport(
        mode=mode,
        mode_reason=mode_reason,
        required_mapped=required_mapped,
        recommended_mapped=recommended_mapped,
        derived_fields=derived_columns,
        usable_feature_count=usable_feature_count,
        label_distribution=label_distribution,
        split_strategy=split_strategy,
        warnings=report_warnings,
        improvements=improvements[:5],  # cap at 5 suggestions
        normalized_preview=normalized_preview,
        dataset_info=dataset_info,
    )


def readiness_to_dict(r: ReadinessReport) -> dict:
    """Serialize ReadinessReport for JSON API response."""
    return {
        "mode": r.mode,
        "mode_reason": r.mode_reason,
        "required_mapped": r.required_mapped,
        "recommended_mapped": r.recommended_mapped,
        "derived_fields": r.derived_fields,
        "usable_feature_count": r.usable_feature_count,
        "label_distribution": r.label_distribution,
        "split_strategy": r.split_strategy,
        "warnings": r.warnings,
        "improvements": r.improvements,
        "normalized_preview": r.normalized_preview,
        "dataset_info": r.dataset_info,
    }

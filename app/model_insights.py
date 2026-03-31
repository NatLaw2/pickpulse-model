"""Model Insights — portfolio-level explainability for CRO / PE readership.

Answers: "What did the model learn about churn in this dataset?"
         "What did churned accounts actually do differently?"

Reads feature_importance from the trained model's metadata.json artifact
and translates raw feature names into plain business language. Also computes
quantified behavioral differences between churned and retained accounts from
the scored CSV artifact. No ML jargon, no raw column names in the output.

Output sections:
  churn_drivers      — top features that elevate churn risk, ranked
  health_signals     — top features that correlate with retention/renewal
  top_insight        — one-sentence summary of the model's strongest signal
  lift_statement     — lift in the top risk group (from lift table)
  behavioral_diff    — churned vs retained avg comparison, 3-5 key signals

Design constraints:
  - No multipliers or percentages unless derived from real data
  - No raw feature names exposed in API response
  - Direction (churn vs. protective) uses domain knowledge, not model sign,
    because GradientBoosting importances are unsigned
  - Unknown features are omitted cleanly rather than shown as raw names
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_CHURN_DRIVERS = 5
MAX_HEALTH_SIGNALS = 3


# ---------------------------------------------------------------------------
# Feature translation table
# Each entry: (churn_label, churn_desc, health_label, health_desc, group, churn_direction)
#   churn_direction:
#     "high"  — high feature value = more churn risk (e.g. support_tickets)
#     "low"   — low feature value = more churn risk  (e.g. monthly_logins)
#     "flag"  — binary flag; presence = churn signal
#   churn_label/health_label: None = skip for that list
# ---------------------------------------------------------------------------

_T = Dict[str, Any]

FEATURE_TRANSLATIONS: Dict[str, _T] = {
    # Engagement
    "monthly_logins": {
        "churn_label": "Low product usage",
        "churn_desc": "Accounts with infrequent logins show signs of disengagement",
        "health_label": "Consistent product usage",
        "health_desc": "High login frequency is a strong predictor of renewal",
        "group": "Engagement",
        "churn_direction": "low",
    },
    "days_since_last_login": {
        "churn_label": "Infrequent login activity",
        "churn_desc": "Accounts not recently active are at higher disengagement risk",
        "health_label": "Recent login activity",
        "health_desc": "Accounts that logged in recently show lower churn rates",
        "group": "Engagement",
        "churn_direction": "high",
    },
    "seats": {
        "churn_label": "Low seat utilization",
        "churn_desc": "Underutilized seats relative to contract size signal disengagement",
        "health_label": "Full seat utilization",
        "health_desc": "Accounts using their full allocation are more embedded in the product",
        "group": "Engagement",
        "churn_direction": "low",
    },
    # Support
    "support_tickets": {
        "churn_label": "High support volume",
        "churn_desc": "Elevated ticket counts signal unresolved friction or product issues",
        "health_label": "Low support friction",
        "health_desc": "Accounts with minimal support issues tend to renew without intervention",
        "group": "Support",
        "churn_direction": "high",
    },
    # Customer sentiment
    "nps_score": {
        "churn_label": "Low NPS score",
        "churn_desc": "Low satisfaction scores are a leading indicator of churn risk",
        "health_label": "High customer satisfaction",
        "health_desc": "Promoters (NPS ≥ 8) have significantly lower churn rates",
        "group": "Sentiment",
        "churn_direction": "low",
    },
    # Contract & renewal
    "arr": {
        "churn_label": "Revenue at risk",
        "churn_desc": "Account revenue size is weighted in risk scoring",
        "health_label": "Strong revenue base",
        "health_desc": "Higher-value accounts typically receive dedicated success resources",
        "group": "Financial",
        "churn_direction": "low",
    },
    "days_until_renewal": {
        "churn_label": "Renewal proximity",
        "churn_desc": "Accounts approaching renewal require active engagement",
        "health_label": "Renewal runway",
        "health_desc": "Accounts with ample runway have more time to resolve issues",
        "group": "Contract",
        "churn_direction": "low",
    },
    "contract_months_remaining": {
        "churn_label": "Short contract runway",
        "churn_desc": "Accounts with few months remaining are entering the active churn window",
        "health_label": "Multi-year contract",
        "health_desc": "Longer contracts are associated with deeper product integration",
        "group": "Contract",
        "churn_direction": "low",
    },
    "auto_renew_flag": {
        "churn_label": "Auto-renew not enabled",
        "churn_desc": "Accounts without auto-renewal require active confirmation to retain",
        "health_label": "Auto-renew enabled",
        "health_desc": "Auto-renewing accounts are lower-friction at renewal time",
        "group": "Contract",
        "churn_direction": "low",
    },
    # Renewal status (one-hot encoded)
    "renewal_status_cancelled": {
        "churn_label": "Cancelled renewal status",
        "churn_desc": "Accounts with a cancelled flag are the strongest single churn predictor",
        "health_label": None,
        "health_desc": None,
        "group": "Contract",
        "churn_direction": "flag",
    },
    "renewal_status_in_notice": {
        "churn_label": "In cancellation notice",
        "churn_desc": "Accounts actively in notice period are at immediate churn risk",
        "health_label": None,
        "health_desc": None,
        "group": "Contract",
        "churn_direction": "flag",
    },
    "renewal_status_unknown": {
        "churn_label": "Unknown renewal status",
        "churn_desc": "Accounts with no renewal status on record have higher unpredictability",
        "health_label": None,
        "health_desc": None,
        "group": "Contract",
        "churn_direction": "flag",
    },
    "renewal_status_active": {
        "churn_label": None,
        "churn_desc": None,
        "health_label": "Active renewal status",
        "health_desc": "Accounts with confirmed active status are on a retention track",
        "group": "Contract",
        "churn_direction": "low",
    },
    # Plan tier
    "plan_Free Trial": {
        "churn_label": "Free trial accounts",
        "churn_desc": "Trial accounts have higher conversion uncertainty than paid tiers",
        "health_label": None,
        "health_desc": None,
        "group": "Account Type",
        "churn_direction": "flag",
    },
    "plan_Starter": {
        "churn_label": "Entry-level plan",
        "churn_desc": "Starter-tier accounts show higher churn rates than mid and high tiers",
        "health_label": None,
        "health_desc": None,
        "group": "Account Type",
        "churn_direction": "flag",
    },
    "plan_Professional": {
        "churn_label": None,
        "churn_desc": None,
        "health_label": "Professional plan",
        "health_desc": "Professional-tier accounts show stronger retention and expansion rates",
        "group": "Account Type",
        "churn_direction": "low",
    },
    "plan_Enterprise": {
        "churn_label": None,
        "churn_desc": None,
        "health_label": "Enterprise plan",
        "health_desc": "Enterprise accounts typically have dedicated success coverage and longer contracts",
        "group": "Account Type",
        "churn_direction": "low",
    },
    # Company size
    "company_size_51-200": {
        "churn_label": "Mid-market accounts",
        "churn_desc": "Mid-market companies show distinctive churn patterns in this dataset",
        "health_label": None,
        "health_desc": None,
        "group": "Firmographic",
        "churn_direction": "flag",
    },
    "company_size_1-50": {
        "churn_label": "Small company accounts",
        "churn_desc": "Smaller companies may have more budget volatility at renewal",
        "health_label": None,
        "health_desc": None,
        "group": "Firmographic",
        "churn_direction": "flag",
    },
    "company_size_201-1000": {
        "churn_label": None,
        "churn_desc": None,
        "health_label": "Enterprise-scale accounts",
        "health_desc": "Larger organizations tend to have higher renewal rates and longer contracts",
        "group": "Firmographic",
        "churn_direction": "low",
    },
}


def _translate(feature_name: str) -> Optional[_T]:
    """Return the translation entry for a feature name, or None if unknown."""
    # Exact match first
    if feature_name in FEATURE_TRANSLATIONS:
        return FEATURE_TRANSLATIONS[feature_name]
    # Prefix match for dynamically generated OHE columns not in the table
    for key, entry in FEATURE_TRANSLATIONS.items():
        if feature_name.startswith(key + "_") or feature_name == key:
            return entry
    return None


def compute_model_insights(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Derive plain-language model insights from a training metadata artifact.

    Args:
        metadata: Content of metadata.json produced by train.train_model().

    Returns structured insights dict with churn_drivers, health_signals,
    top_insight, lift_statement, and provenance fields.
    """
    importance_list: List[Dict[str, Any]] = metadata.get("feature_importance", [])
    model_type: str = metadata.get("model_type", "unknown")
    val_metrics: Dict[str, Any] = metadata.get("val_metrics") or {}
    lift_table: List[Dict[str, Any]] = val_metrics.get("lift_table", [])

    if not importance_list:
        return _empty_insights(metadata)

    # Normalize importance scores to [0, 1] relative to the top feature.
    max_imp = max(abs(f["importance"]) for f in importance_list) or 1.0
    normed = [
        {**f, "importance_normalized": round(abs(f["importance"]) / max_imp, 3)}
        for f in importance_list
    ]

    # Build churn_drivers and health_signals
    churn_drivers: List[Dict[str, Any]] = []
    health_signals: List[Dict[str, Any]] = []
    seen_labels: set = set()

    for entry in normed:
        fname = entry["feature"]
        translation = _translate(fname)
        if translation is None:
            continue  # unknown feature — omit rather than show raw name

        imp_norm = entry["importance_normalized"]

        # Churn drivers
        if translation.get("churn_label") and len(churn_drivers) < MAX_CHURN_DRIVERS:
            label = translation["churn_label"]
            if label not in seen_labels:
                seen_labels.add(label)
                churn_drivers.append({
                    "rank": len(churn_drivers) + 1,
                    "label": label,
                    "description": translation["churn_desc"],
                    "group": translation["group"],
                    "importance_normalized": imp_norm,
                })

        # Health signals (separate pass — may use same feature from other angle)
        if translation.get("health_label") and len(health_signals) < MAX_HEALTH_SIGNALS:
            health_label = translation["health_label"]
            if health_label not in seen_labels:
                seen_labels.add(health_label)
                health_signals.append({
                    "rank": len(health_signals) + 1,
                    "label": health_label,
                    "description": translation["health_desc"],
                    "group": translation["group"],
                    "importance_normalized": imp_norm,
                })

    # Top insight — derived from actual top-ranked drivers
    top_insight = _generate_top_insight(churn_drivers, health_signals)

    # Lift statement — derived from lift table (real data, no fake numbers)
    lift_statement = _generate_lift_statement(lift_table)

    return {
        "module": metadata.get("module", "churn"),
        "model_type": model_type,
        "trained_at": metadata.get("trained_at"),
        "n_features_total": metadata.get("n_features", len(importance_list)),
        "churn_drivers": churn_drivers,
        "health_signals": health_signals,
        "top_insight": top_insight,
        "lift_statement": lift_statement,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _generate_top_insight(
    churn_drivers: List[Dict[str, Any]],
    health_signals: List[Dict[str, Any]],
) -> str:
    if not churn_drivers:
        return "No feature importance data available for this model."

    top = churn_drivers[0]["label"].lower()
    if len(churn_drivers) >= 2:
        second = churn_drivers[1]["label"].lower()
        return (
            f"{churn_drivers[0]['label']} and {churn_drivers[1]['label'].lower()} "
            f"are the strongest predictors of churn in this dataset."
        )
    return f"{churn_drivers[0]['label']} is the strongest predictor of churn in this dataset."


def _generate_lift_statement(lift_table: List[Dict[str, Any]]) -> Optional[str]:
    """Derive a lift statement from the real lift table. Returns None if no data."""
    if not lift_table:
        return None
    top_decile = lift_table[0]
    lift = top_decile.get("lift")
    if not lift or lift <= 1.0:
        return None
    return (
        f"Accounts in the model's highest-risk group are "
        f"{lift:.1f}× more likely to churn than the portfolio average."
    )


def _empty_insights(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "module": metadata.get("module", "churn"),
        "model_type": metadata.get("model_type", "unknown"),
        "trained_at": metadata.get("trained_at"),
        "n_features_total": 0,
        "churn_drivers": [],
        "health_signals": [],
        "top_insight": None,
        "lift_statement": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def load_insights_for_tenant(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Load metadata.json for the tenant's churn model and compute insights,
    then merge in behavioral diff from the scored CSV artifact.

    Returns None if no model has been trained yet.
    Uses the same artifact path convention as console_api.py.
    """
    from app.engine.config import get_module

    try:
        mod = get_module("churn")
        artifact_dir = mod.get_artifact_dir(tenant_id)
        meta_path = os.path.join(artifact_dir, "metadata.json")
        if not os.path.exists(meta_path):
            return None
        with open(meta_path) as f:
            metadata = json.load(f)
        insights = compute_model_insights(metadata)
        insights["behavioral_diff"] = _load_behavioral_diff(tenant_id)
        return insights
    except Exception as exc:
        logger.warning("model_insights: load failed for tenant %s (%s)", tenant_id, exc)
        return None


# ---------------------------------------------------------------------------
# Behavioral diff — churned vs retained quantified comparison
# ---------------------------------------------------------------------------

# Features to compare, in priority order.
# (feature_name, display_label, format_type)
#   format_type:
#     "pct"    — % change: "↓ 42% lower login activity"
#     "ratio"  — multiplier: "↑ 2.3× more support ticket volume"
#     "points" — absolute diff: "↓ 3.1 points lower NPS score"
_BEHAVIORAL_FEATURES: List[tuple] = [
    ("monthly_logins",        "login activity",           "pct"),
    ("engagement_score",      "overall engagement",       "pct"),
    ("nps_score",             "NPS score",                "points"),
    ("support_tickets",       "support ticket volume",    "ratio"),
    ("days_since_last_login", "days since last login",    "pct"),
    ("arr",                   "account value (ARR)",      "pct"),
    ("seats",                 "seat utilization",         "pct"),
]

_MAX_DIFF_ITEMS = 5
_MIN_RETAINED_N = 5  # skip if too few samples


def compute_behavioral_diff(
    scored_df: "Any",  # pd.DataFrame — avoid hard import at module level
    label_col: str = "churned",
) -> Dict[str, Any]:
    """Compute churned vs retained behavioral differences from the scored DataFrame.

    Args:
        scored_df: DataFrame produced by evaluate_model's scored CSV output.
                   Must contain label_col plus at least some of the numeric
                   feature columns listed in _BEHAVIORAL_FEATURES.
        label_col: Binary label column name (1 = churned, 0 = retained).

    Returns:
        Dict with keys: items, interpretation, n_churned, n_retained.
    """
    import pandas as pd  # local import — pandas not used elsewhere in this module

    churned = scored_df[scored_df[label_col] == 1]
    retained = scored_df[scored_df[label_col] == 0]

    n_c, n_r = len(churned), len(retained)
    if n_c < _MIN_RETAINED_N or n_r < _MIN_RETAINED_N:
        return {"items": [], "interpretation": None, "n_churned": n_c, "n_retained": n_r}

    raw_items: List[Dict[str, Any]] = []

    for feat, label, fmt in _BEHAVIORAL_FEATURES:
        if feat not in scored_df.columns:
            continue

        c_vals = churned[feat].dropna()
        r_vals = retained[feat].dropna()
        if len(c_vals) < 2 or len(r_vals) < 2:
            continue

        c_mean = float(c_vals.mean())
        r_mean = float(r_vals.mean())

        if r_mean == 0:
            continue

        magnitude: float
        summary: str
        direction: str

        if fmt == "pct":
            pct = (c_mean - r_mean) / abs(r_mean) * 100
            if abs(pct) < 8:
                continue  # noise threshold
            direction = "up" if pct > 0 else "down"
            arrow = "↑" if direction == "up" else "↓"
            word = "higher" if direction == "up" else "lower"
            summary = f"{arrow} {abs(round(pct))}% {word} {label}"
            magnitude = abs(pct)

        elif fmt == "ratio":
            if r_mean == 0:
                continue
            ratio = c_mean / r_mean
            if ratio < 1.15:
                continue  # not meaningfully different
            direction = "up"
            summary = f"↑ {ratio:.1f}× more {label}"
            magnitude = (ratio - 1) * 100  # normalise for sorting

        elif fmt == "points":
            diff = c_mean - r_mean
            if abs(diff) < 0.5:
                continue
            direction = "up" if diff > 0 else "down"
            arrow = "↑" if direction == "up" else "↓"
            word = "higher" if direction == "up" else "lower"
            summary = f"{arrow} {abs(round(diff, 1))} points {word} {label}"
            magnitude = abs(diff)

        else:
            continue

        raw_items.append({
            "label": label,
            "feature": feat,
            "direction": direction,
            "summary": summary,
            "churned_avg": round(c_mean, 2),
            "retained_avg": round(r_mean, 2),
            "format_type": fmt,
            "_magnitude": magnitude,
        })

    # Sort by magnitude descending, cap at _MAX_DIFF_ITEMS
    raw_items.sort(key=lambda x: x["_magnitude"], reverse=True)
    raw_items = raw_items[:_MAX_DIFF_ITEMS]

    # Strip internal sorting field
    items = [{k: v for k, v in item.items() if k != "_magnitude"} for item in raw_items]

    interpretation = _generate_behavioral_interpretation(raw_items, n_c, n_r)

    return {
        "items": items,
        "interpretation": interpretation,
        "n_churned": n_c,
        "n_retained": n_r,
    }


def _generate_behavioral_interpretation(
    items: List[Dict[str, Any]],
    n_churned: int,
    n_retained: int,
) -> Optional[str]:
    """Generate one plain-language sentence summarising the behavioral diff."""
    if not items:
        return None

    top = items[0]
    engagement_labels = {"login activity", "overall engagement", "seat utilization", "days since last login"}
    friction_labels = {"support ticket volume"}

    if len(items) >= 2:
        second = items[1]
        # Detect the dominant theme
        both_engagement = top["label"] in engagement_labels and second["label"] in engagement_labels
        top_friction = top["label"] in friction_labels
        if both_engagement:
            theme = "disengagement"
        elif top_friction:
            theme = "product friction"
        else:
            theme = "behavioral disengagement"
        return (
            f"Across {n_churned} churned accounts, the clearest pattern was "
            f"{top['label']} and {second['label']} — consistent with {theme} "
            f"in the months before renewal."
        )

    return (
        f"Across {n_churned} churned accounts, the strongest behavioral signal was "
        f"{top['label']}."
    )


def _load_behavioral_diff(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Load the scored CSV for the tenant and compute behavioral diff.

    Returns None if the scored CSV does not exist yet.
    """
    import pandas as pd

    try:
        data_dir = os.environ.get("DATA_DIR", "data")
        scored_path = os.path.join(data_dir, "outputs", tenant_id, "churn_scored.csv")
        if not os.path.exists(scored_path):
            return None
        df = pd.read_csv(scored_path)
        label_col = "churned"
        if label_col not in df.columns:
            return None
        df[label_col] = df[label_col].astype(int)
        return compute_behavioral_diff(df, label_col)
    except Exception as exc:
        logger.warning("behavioral_diff: load failed for tenant %s (%s)", tenant_id, exc)
        return None

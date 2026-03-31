"""Model Insights — portfolio-level explainability for CRO / PE readership.

Answers: "What did the model learn about churn in this dataset?"
         "What did churned accounts actually do differently?"

Phase 3 design — fully dynamic, model-driven:

  Source of truth is the trained model, not a predefined feature list.

  churn_drivers / health_signals
    Ranked by feature_importance from metadata.json.
    Direction ("increases_risk" vs "decreases_risk") from shap_directions —
    mean SHAP sign across the background set, computed at training time.
    Labels from driver_labels.clean_feature_name(feature, direction).
    Supplementary descriptions from _FEATURE_DESCRIPTIONS where available;
    generic fallback otherwise.  No feature is silently dropped.

  behavioral_diff
    Compares churned vs retained averages for the model's actual top features
    (from feature_importance), not a hardcoded SaaS feature list.
    Format type (pct / ratio / points / days) inferred from feature name.
    Labels from driver_labels.clean_feature_name().

API response shape is stable — same fields as pre-Phase 3.
Raw feature names never appear in user-facing output.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_CHURN_DRIVERS = 5
MAX_HEALTH_SIGNALS = 3
_MIN_COHORT_N = 5       # skip behavioral diff if either cohort is too small
_MAX_DIFF_ITEMS = 5
_MAX_BEHAV_FEATURES = 12  # scan top-N model features for behavioral diff


# ---------------------------------------------------------------------------
# Supplementary description text
# Provides the explanatory "why" sentence for known feature families.
# Labels and direction come from driver_labels (Phase 2); descriptions are
# additive context, not the source of truth.
# Unknown features get a generic description — they are never silently dropped.
# ---------------------------------------------------------------------------

_FEATURE_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    # Engagement / activity
    "days_since_last_login": {
        "increases_risk": "Accounts not recently active are at higher disengagement risk",
        "decreases_risk": "Accounts that engaged recently show significantly lower churn rates",
    },
    "days_since_last_activity": {
        "increases_risk": "Accounts with no recent activity are showing signs of disengagement",
        "decreases_risk": "Accounts with recent activity are more likely to renew",
    },
    "monthly_logins": {
        "increases_risk": "Accounts with low activity frequency show signs of disengagement",
        "decreases_risk": "Consistent engagement frequency is a strong predictor of renewal",
    },
    # Support
    "support_tickets": {
        "increases_risk": "Elevated ticket counts signal unresolved friction or delivery issues",
        "decreases_risk": "Accounts with minimal support issues tend to renew without intervention",
    },
    # CRM relationship
    "contact_count": {
        "increases_risk": "Accounts with fewer contacts have shallower relationships and lower retention resilience",
        "decreases_risk": "Accounts with multiple contacts are more embedded and harder to displace",
    },
    "deal_count": {
        "increases_risk": "Low deal activity may indicate a stalled or disengaged commercial relationship",
        "decreases_risk": "Ongoing deal activity reflects a healthy and expanding relationship",
    },
    # Sentiment
    "nps_score": {
        "increases_risk": "Low satisfaction scores are a leading indicator of churn risk",
        "decreases_risk": "High satisfaction correlates strongly with renewal and expansion",
    },
    # Financial
    "arr": {
        "increases_risk": "High-value accounts at risk represent significant revenue exposure",
        "decreases_risk": "Higher-value accounts typically receive dedicated success resources",
    },
    # Contract timing
    "days_until_renewal": {
        "increases_risk": "Accounts approaching renewal require active engagement",
        "decreases_risk": "Accounts with ample runway have more time to resolve issues",
    },
    "contract_months_remaining": {
        "increases_risk": "Accounts with few months remaining are entering the active churn window",
        "decreases_risk": "Longer contracts are associated with deeper relationship integration",
    },
    "auto_renew_flag": {
        "increases_risk": "Accounts without auto-renewal require active confirmation to retain",
        "decreases_risk": "Auto-renewing accounts are lower-friction at renewal time",
    },
    # Utilization
    "seats": {
        "increases_risk": "Underutilized capacity relative to contract size signals disengagement",
        "decreases_risk": "Accounts at full allocation are more embedded and harder to displace",
    },
}

# Prefix-match fallbacks: a feature starting with these prefixes uses this entry.
# Handles OHE columns like "renewal_status_cancelled", "plan_Enterprise", etc.
_FEATURE_DESC_PREFIXES: Dict[str, Dict[str, str]] = {
    "renewal_status": {
        "increases_risk": "Contract status is one of the strongest single indicators of churn risk",
        "decreases_risk": "Active renewal status indicates the account is on a retention track",
    },
    "plan_": {
        "increases_risk": "Plan tier is a meaningful predictor of churn patterns in this dataset",
        "decreases_risk": "This plan tier is associated with stronger retention rates",
    },
    "company_size": {
        "increases_risk": "This company size segment shows elevated churn patterns in this dataset",
        "decreases_risk": "This company size segment is associated with stronger retention",
    },
    "arr_tier": {
        "increases_risk": "Account value tier is a risk factor in this dataset",
        "decreases_risk": "This account value segment is associated with lower churn rates",
    },
    "industry_": {
        "increases_risk": "This industry segment shows elevated churn in this dataset",
        "decreases_risk": "This industry segment is associated with stronger retention",
    },
}


def _get_description(feature: str, direction: str) -> str:
    """Return a description sentence for a feature+direction pair.

    Tries exact match, then prefix match, then generic fallback.
    Never returns None — every feature gets a description.
    """
    entry = _FEATURE_DESCRIPTIONS.get(feature)
    if entry:
        return entry.get(direction, entry.get("increases_risk", ""))

    # Prefix match
    for prefix, desc_map in _FEATURE_DESC_PREFIXES.items():
        if feature.startswith(prefix):
            return desc_map.get(direction, desc_map.get("increases_risk", ""))

    # Generic fallback — direction-aware but generic
    if direction == "increases_risk":
        return "This factor is associated with elevated churn risk in the trained dataset"
    return "This factor is associated with improved retention in the trained dataset"


def _get_label(feature: str, direction: str) -> str:
    """Return a clean business-readable label using the Phase 2 driver_labels system."""
    from app.engine.driver_labels import clean_feature_name
    return clean_feature_name(feature, direction)


def _get_direction(feature: str, shap_directions: Dict[str, str]) -> str:
    """Return 'increases_risk' | 'decreases_risk' for a feature.

    Source: shap_directions from metadata.json (computed at training time as mean
    SHAP sign across the background set).  Falls back to 'increases_risk' for
    features not in the dict (safe default — shows as a churn driver).
    """
    return shap_directions.get(feature, "increases_risk")


# ---------------------------------------------------------------------------
# Global insights computation
# ---------------------------------------------------------------------------

def compute_model_insights(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Derive plain-language model insights from a training metadata artifact.

    Source of truth: feature_importance and shap_directions from metadata.json.
    Labels from driver_labels; descriptions from _FEATURE_DESCRIPTIONS.
    Direction from shap_directions (mean SHAP sign at training time).

    No feature is silently dropped — features not in any lookup table get
    a generic label and description.

    Args:
        metadata: Content of metadata.json produced by train.train_model().

    Returns:
        Structured insights dict with churn_drivers, health_signals,
        top_insight, lift_statement, and provenance fields.
    """
    importance_list: List[Dict[str, Any]] = metadata.get("feature_importance", [])
    shap_directions: Dict[str, str] = metadata.get("shap_directions", {})
    model_type: str = metadata.get("model_type", "unknown")
    val_metrics: Dict[str, Any] = metadata.get("val_metrics") or {}
    lift_table: List[Dict[str, Any]] = val_metrics.get("lift_table", [])

    if not importance_list:
        return _empty_insights(metadata)

    # Normalise importance to [0, 1] relative to the top feature
    max_imp = max(abs(f["importance"]) for f in importance_list) or 1.0
    normed = [
        {**f, "importance_normalized": round(abs(f["importance"]) / max_imp, 3)}
        for f in importance_list
    ]

    churn_drivers: List[Dict[str, Any]] = []
    health_signals: List[Dict[str, Any]] = []
    seen_labels: set = set()

    for entry in normed:
        fname = entry["feature"]
        imp_norm = entry["importance_normalized"]
        direction = _get_direction(fname, shap_directions)

        label = _get_label(fname, direction)
        description = _get_description(fname, direction)

        if direction == "increases_risk" and len(churn_drivers) < MAX_CHURN_DRIVERS:
            if label not in seen_labels:
                seen_labels.add(label)
                churn_drivers.append({
                    "rank": len(churn_drivers) + 1,
                    "label": label,
                    "description": description,
                    "feature": fname,   # kept for traceability; not shown in UI
                    "group": _infer_group(fname),
                    "importance_normalized": imp_norm,
                })

        elif direction == "decreases_risk" and len(health_signals) < MAX_HEALTH_SIGNALS:
            if label not in seen_labels:
                seen_labels.add(label)
                health_signals.append({
                    "rank": len(health_signals) + 1,
                    "label": label,
                    "description": description,
                    "feature": fname,
                    "group": _infer_group(fname),
                    "importance_normalized": imp_norm,
                })

        if len(churn_drivers) >= MAX_CHURN_DRIVERS and len(health_signals) >= MAX_HEALTH_SIGNALS:
            break

    top_insight = _generate_top_insight(churn_drivers, health_signals)
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


def _infer_group(feature: str) -> str:
    """Infer a display group from a feature name without hardcoded assumptions."""
    f = feature.lower()
    if any(k in f for k in ("login", "activity", "logins", "engagement")):
        return "Engagement"
    if any(k in f for k in ("ticket", "support", "case")):
        return "Support"
    if any(k in f for k in ("nps", "satisfaction", "csat")):
        return "Sentiment"
    if any(k in f for k in ("arr", "mrr", "revenue", "acv")):
        return "Financial"
    if any(k in f for k in ("renewal", "contract", "auto_renew", "days_until")):
        return "Contract"
    if any(k in f for k in ("contact", "deal", "stakeholder")):
        return "Relationship"
    if any(k in f for k in ("seat", "utiliz", "license")):
        return "Utilization"
    if any(k in f for k in ("plan_", "tier", "company_size", "industry_")):
        return "Firmographic"
    return "Account Signal"


def _generate_top_insight(
    churn_drivers: List[Dict[str, Any]],
    health_signals: List[Dict[str, Any]],
) -> Optional[str]:
    if not churn_drivers:
        return "No feature importance data available for this model."
    if len(churn_drivers) >= 2:
        return (
            f"{churn_drivers[0]['label']} and {churn_drivers[1]['label'].lower()} "
            f"are the strongest predictors of churn in this dataset."
        )
    return f"{churn_drivers[0]['label']} is the strongest predictor of churn in this dataset."


def _generate_lift_statement(lift_table: List[Dict[str, Any]]) -> Optional[str]:
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


# ---------------------------------------------------------------------------
# Behavioral diff — churned vs retained quantified comparison
#
# Phase 3: no longer driven by _BEHAVIORAL_FEATURES (hardcoded SaaS list).
# Instead reads the model's actual top features from feature_importance,
# checks which exist in the scored CSV, and computes from those.
# ---------------------------------------------------------------------------

def _infer_format_type(feature: str) -> str:
    """Infer a diff format from the feature name.

    "days"   → "days"   (show absolute difference in days)
    counts   → "ratio"  (churned / retained multiplier)
    scores   → "points" (absolute difference on the score scale)
    monetary → "pct"    (percentage difference)
    default  → "pct"
    """
    f = feature.lower()
    if "days" in f:
        return "days"
    if any(k in f for k in ("ticket", "count", "deal", "contact", "logins", "seats", "seat")):
        return "ratio"
    if any(k in f for k in ("nps", "score", "csat")):
        return "points"
    return "pct"


def _is_binary_column(series: "Any") -> bool:
    """Return True if series contains only 0s and 1s (OHE or flag column)."""
    unique = set(series.dropna().unique())
    return unique.issubset({0, 1, 0.0, 1.0})


def compute_behavioral_diff(
    scored_df: "Any",
    label_col: str = "churned",
    feature_importance: Optional[List[Dict[str, Any]]] = None,
    shap_directions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Compute churned vs retained behavioral differences.

    Uses the model's actual top features (from feature_importance) rather than
    a hardcoded SaaS feature list.  Labels come from driver_labels.

    Args:
        scored_df:          DataFrame from evaluate_model scored CSV output.
        label_col:          Binary label column (1 = churned, 0 = retained).
        feature_importance: Ranked feature list from metadata.json.
                            If None, uses any numeric column found in scored_df.
        shap_directions:    Per-feature direction from metadata.json.
                            Used to frame diff direction labels correctly.
    """
    import pandas as pd
    from app.engine.driver_labels import clean_feature_name

    churned = scored_df[scored_df[label_col] == 1]
    retained = scored_df[scored_df[label_col] == 0]

    n_c, n_r = len(churned), len(retained)
    if n_c < _MIN_COHORT_N or n_r < _MIN_COHORT_N:
        return {"items": [], "interpretation": None, "n_churned": n_c, "n_retained": n_r}

    # Build candidate feature list: model's top features in importance order,
    # filtered to columns present in the scored CSV.
    if feature_importance:
        candidates = [
            f["feature"] for f in feature_importance[:_MAX_BEHAV_FEATURES]
            if f["feature"] in scored_df.columns
        ]
    else:
        # No importance data — use any numeric column
        candidates = [
            c for c in scored_df.columns
            if c not in (label_col, "account_id", "probability", "tier",
                         "rank", "churn_risk_pct", "urgency_score",
                         "renewal_window_label", "arr_at_risk",
                         "recommended_action", "account_status",
                         "top_drivers", "confidence_level")
            and pd.api.types.is_numeric_dtype(scored_df[c])
        ]

    raw_items: List[Dict[str, Any]] = []

    for feat in candidates:
        if feat not in scored_df.columns:
            continue
        if not pd.api.types.is_numeric_dtype(scored_df[feat]):
            continue
        if _is_binary_column(scored_df[feat]):
            continue  # OHE / flag columns — averages aren't meaningful to display

        c_vals = churned[feat].dropna()
        r_vals = retained[feat].dropna()

        if len(c_vals) < 2 or len(r_vals) < 2:
            continue

        c_mean = float(c_vals.mean())
        r_mean = float(r_vals.mean())

        if r_mean == 0 and c_mean == 0:
            continue

        fmt = _infer_format_type(feat)
        direction = (shap_directions or {}).get(feat, "increases_risk")
        display_label = clean_feature_name(feat, direction)

        magnitude: float
        summary: str
        diff_direction: str

        if fmt == "ratio":
            base = max(abs(r_mean), 0.001)
            ratio = c_mean / base
            if abs(ratio - 1.0) < 0.15:
                continue
            diff_direction = "up" if ratio > 1 else "down"
            arrow = "↑" if diff_direction == "up" else "↓"
            if diff_direction == "up":
                summary = f"↑ {ratio:.1f}× higher in churned accounts"
            else:
                summary = f"↓ {1/ratio:.1f}× lower in churned accounts"
            magnitude = abs(ratio - 1.0) * 100

        elif fmt == "points":
            diff = c_mean - r_mean
            if abs(diff) < 0.5:
                continue
            diff_direction = "up" if diff > 0 else "down"
            arrow = "↑" if diff_direction == "up" else "↓"
            word = "higher" if diff_direction == "up" else "lower"
            summary = f"{arrow} {abs(round(diff, 1))} points {word} in churned accounts"
            magnitude = abs(diff)

        elif fmt == "days":
            diff = c_mean - r_mean
            if abs(diff) < 1.0:
                continue
            diff_direction = "up" if diff > 0 else "down"
            arrow = "↑" if diff_direction == "up" else "↓"
            word = "more" if diff_direction == "up" else "fewer"
            summary = f"{arrow} {abs(round(diff))} days {word} in churned accounts"
            magnitude = abs(diff)

        else:  # "pct"
            base = max(abs(r_mean), 0.001)
            pct = (c_mean - r_mean) / base * 100
            if abs(pct) < 8:
                continue
            diff_direction = "up" if pct > 0 else "down"
            arrow = "↑" if diff_direction == "up" else "↓"
            word = "higher" if diff_direction == "up" else "lower"
            summary = f"{arrow} {abs(round(pct))}% {word} in churned accounts"
            magnitude = abs(pct)

        raw_items.append({
            "label": display_label,
            "feature": feat,
            "direction": diff_direction,
            "summary": summary,
            "churned_avg": round(c_mean, 2),
            "retained_avg": round(r_mean, 2),
            "format_type": fmt,
            "_magnitude": magnitude,
        })

    # Sort by magnitude descending, cap at _MAX_DIFF_ITEMS
    raw_items.sort(key=lambda x: x["_magnitude"], reverse=True)
    items = [
        {k: v for k, v in item.items() if k != "_magnitude"}
        for item in raw_items[:_MAX_DIFF_ITEMS]
    ]

    interpretation = _generate_behavioral_interpretation(items, n_c, n_r)

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
    """Generate one plain-language sentence summarising the behavioral diff.

    Phase 3: no hardcoded feature name sets — uses the labels from items directly.
    """
    if not items:
        return None

    top = items[0]

    if len(items) >= 2:
        second = items[1]
        return (
            f"Across {n_churned} churned accounts, the two clearest behavioral "
            f"differences were {top['label'].lower()} and {second['label'].lower()}."
        )

    return (
        f"Across {n_churned} churned accounts, the strongest behavioral signal "
        f"was {top['label'].lower()}."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def load_insights_for_tenant(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Load metadata.json for the tenant's churn model and compute insights.

    Also merges in behavioral diff from the scored CSV artifact.
    Returns None if no model has been trained yet.
    """
    from app.engine.config import get_module

    try:
        mod = get_module("churn")
        # Prefer versioned artifact path (current model run) if available
        from app.storage import store
        current_run = store.get_current_model_run(tenant_id, "churn")
        if current_run and current_run.get("artifact_path"):
            artifact_dir = current_run["artifact_path"]
        else:
            artifact_dir = mod.get_artifact_dir(tenant_id)

        meta_path = os.path.join(artifact_dir, "metadata.json")
        if not os.path.exists(meta_path):
            return None

        with open(meta_path) as f:
            metadata = json.load(f)

        insights = compute_model_insights(metadata)
        insights["behavioral_diff"] = _load_behavioral_diff(
            tenant_id,
            feature_importance=metadata.get("feature_importance"),
            shap_directions=metadata.get("shap_directions"),
        )
        # Signal whether this model artifact includes SHAP direction metadata.
        # Frontend uses this to show a retrain recommendation for stale models.
        insights["has_shap_directions"] = bool(metadata.get("shap_directions"))
        return insights

    except Exception as exc:
        logger.warning("model_insights: load failed for tenant %s (%s)", tenant_id, exc)
        return None


def _load_behavioral_diff(
    tenant_id: str,
    feature_importance: Optional[List[Dict[str, Any]]] = None,
    shap_directions: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Load the scored CSV and compute behavioral diff using model's top features."""
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
        return compute_behavioral_diff(
            df,
            label_col=label_col,
            feature_importance=feature_importance,
            shap_directions=shap_directions,
        )
    except Exception as exc:
        logger.warning("behavioral_diff: load failed for tenant %s (%s)", tenant_id, exc)
        return None

"""Generic prediction — load artifacts, score new data, classify tiers."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from .config import ModuleConfig
from .features import prepare_features

logger = logging.getLogger(__name__)


def load_model(
    module: ModuleConfig,
    tenant_id: str | None = None,
    artifact_dir: str | None = None,
) -> Dict[str, Any]:
    """Load trained model and feature metadata for a module.

    Args:
        artifact_dir: Explicit path to the artifact directory. When provided,
            overrides the path derived from tenant_id (used for versioned models
            trained in PR 3A+). Callers should prefer passing this directly
            rather than relying on the module+tenant_id derivation.
    """
    if artifact_dir is None:
        artifact_dir = module.get_artifact_dir(tenant_id)
    model_path = os.path.join(artifact_dir, "model.joblib")
    meta_path = os.path.join(artifact_dir, "feature_meta.json")
    metadata_path = os.path.join(artifact_dir, "metadata.json")

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No trained model found for '{module.name}'. "
            f"Expected: {model_path}. Train first."
        )

    model = joblib.load(model_path)

    feature_meta = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            feature_meta = json.load(f)

    metadata = {}
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            metadata = json.load(f)

    # Load base model (needed for SHAP — TreeExplainer can't wrap CalibratedClassifierCV)
    base_model = None
    base_model_path = os.path.join(artifact_dir, "base_model.joblib")
    if os.path.exists(base_model_path):
        base_model = joblib.load(base_model_path)

    # Load SHAP background array
    shap_background = None
    shap_bg_path = os.path.join(artifact_dir, "shap_background.npy")
    if os.path.exists(shap_bg_path):
        shap_background = np.load(shap_bg_path)

    return {
        "model": model,
        "feature_meta": feature_meta,
        "metadata": metadata,
        "base_model": base_model,
        "shap_background": shap_background,
    }


def predict(
    df: pd.DataFrame,
    module: ModuleConfig,
    artifacts: Optional[Dict[str, Any]] = None,
    tenant_id: str | None = None,
) -> pd.DataFrame:
    """Score a DataFrame and return predictions with tiers.

    Returns DataFrame with original columns plus:
      probability, tier, rank, value_at_risk,
      churn_risk_pct, urgency_score, renewal_window_label,
      arr_at_risk, recommended_action, account_status
    """
    if artifacts is None:
        artifacts = load_model(module, tenant_id=tenant_id)

    model = artifacts["model"]
    feature_meta = artifacts["feature_meta"]

    # Prepare features (fit=False uses saved params)
    X, _, feature_names, _ = prepare_features(
        df, module, fit=False, feature_meta=feature_meta,
    )

    # Predict probabilities
    raw_probs = model.predict_proba(X)[:, 1]

    # Clamp
    floor = module.calibration.prob_floor
    ceil = module.calibration.prob_ceil
    probs = np.clip(raw_probs, floor, ceil)

    # Build result
    result = df.copy()
    result["probability"] = probs
    result["tier"] = [module.tiers.classify(p) for p in probs]
    result["rank"] = result["probability"].rank(ascending=False, method="min").astype(int)

    # Add value-at-risk if value column exists
    if module.value_column and module.value_column in result.columns:
        result["value_at_risk"] = result[module.value_column] * result["probability"]

    # SHAP per-account driver extraction
    base_model = artifacts.get("base_model")
    shap_background = artifacts.get("shap_background")
    if base_model is not None and shap_background is not None:
        try:
            from app.engine.shap_utils import (
                build_explainer, compute_shap_values, extract_top_drivers,
                compute_confidence_level,
            )
            explainer = build_explainer(base_model, shap_background)
            shap_vals = compute_shap_values(explainer, X)
            raw_drivers = [
                extract_top_drivers(shap_vals[i], feature_names, n=5)
                for i in range(len(shap_vals))
            ]
            # LLM labeling — one batch call for all unique features in this run
            from app.engine.driver_labels import label_drivers_batch
            result["top_drivers"] = label_drivers_batch(raw_drivers)
            # Confidence: fraction of original row fields that had real (non-null)
            # data before prepare_features imputed them.  Uses the same measure as
            # score_accounts() in scoring.py for consistency across code paths.
            _id_col = module.id_column
            _ts_col = module.timestamp_column
            _skip = {_id_col, _ts_col, module.label_column}
            result["confidence_level"] = [
                compute_confidence_level(
                    int(df.iloc[i].drop(labels=[c for c in _skip if c in df.columns], errors="ignore").notna().sum()),
                    len(feature_names),
                )
                for i in range(len(result))
            ]
        except Exception as exc:
            logger.warning("SHAP driver extraction failed: %s", exc)
            result["top_drivers"] = [[] for _ in range(len(result))]
            result["confidence_level"] = ["low"] * len(result)
    else:
        # No SHAP artifacts — still run rule-based labels on empty driver lists
        result["top_drivers"] = [[] for _ in range(len(result))]
        result["confidence_level"] = ["low"] * len(result)

    # Churn-specific enrichment
    if module.name == "churn":
        _enrich_churn_predictions(result)

    # Sort by arr_at_risk if available, else value_at_risk, else probability
    if "arr_at_risk" in result.columns:
        result = result.sort_values("arr_at_risk", ascending=False)
    elif "value_at_risk" in result.columns:
        result = result.sort_values("value_at_risk", ascending=False)
    else:
        result = result.sort_values("probability", ascending=False)

    return result


def _enrich_churn_predictions(result: pd.DataFrame) -> None:
    """Add churn-specific columns in-place."""
    from app.modules.churn.adapter import (
        compute_urgency_score, compute_renewal_window_label,
        compute_recommended_action, compute_account_status,
    )

    # churn_risk_pct (0-100, 1 decimal)
    result["churn_risk_pct"] = (result["probability"] * 100).round(1)

    # renewal_window_label
    if "days_until_renewal" in result.columns:
        result["renewal_window_label"] = result["days_until_renewal"].apply(
            compute_renewal_window_label
        )
    else:
        result["renewal_window_label"] = "unknown"

    # urgency_score
    dur_col = result["days_until_renewal"] if "days_until_renewal" in result.columns else pd.Series(999, index=result.index)
    result["urgency_score"] = [
        compute_urgency_score(p, d)
        for p, d in zip(result["probability"], dur_col)
    ]

    # arr_at_risk
    if "arr" in result.columns:
        result["arr_at_risk"] = (result["arr"] * result["probability"]).round(2)

    # recommended_action — days_since_last_activity is the HubSpot-normalized alias
    if "days_since_last_login" in result.columns:
        dsll = result["days_since_last_login"]
    elif "days_since_last_activity" in result.columns:
        dsll = result["days_since_last_activity"]
    else:
        dsll = pd.Series(0, index=result.index)
    result["recommended_action"] = [
        compute_recommended_action(pct, rwl, dsl)
        for pct, rwl, dsl in zip(
            result["churn_risk_pct"],
            result["renewal_window_label"],
            dsll,
        )
    ]

    # account_status
    churned_col = result["churned"] if "churned" in result.columns else pd.Series(0, index=result.index)
    rs_col = result["renewal_status"] if "renewal_status" in result.columns else pd.Series("active", index=result.index)
    dur_col2 = result["days_until_renewal"] if "days_until_renewal" in result.columns else pd.Series(999, index=result.index)
    result["account_status"] = [
        compute_account_status(c, rs, d)
        for c, rs, d in zip(churned_col, rs_col, dur_col2)
    ]


def predict_single(
    row: Dict[str, Any],
    module: ModuleConfig,
    artifacts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Score a single row and return prediction dict."""
    df = pd.DataFrame([row])
    result = predict(df, module, artifacts)
    row_result = result.iloc[0]

    output = {
        "probability": round(float(row_result["probability"]), 4),
        "tier": row_result["tier"],
        "rank": int(row_result["rank"]),
    }

    for col in ["value_at_risk", "churn_risk_pct", "urgency_score",
                "renewal_window_label", "arr_at_risk", "recommended_action",
                "account_status"]:
        if col in result.columns:
            val = row_result[col]
            if isinstance(val, (float, np.floating)):
                output[col] = round(float(val), 2)
            else:
                output[col] = val

    return output

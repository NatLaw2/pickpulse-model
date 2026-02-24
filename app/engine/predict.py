"""Generic prediction — load artifacts, score new data, classify tiers."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from .config import ModuleConfig
from .features import prepare_features


def load_model(module: ModuleConfig) -> Dict[str, Any]:
    """Load trained model and feature metadata for a module."""
    model_path = os.path.join(module.artifact_dir, "model.joblib")
    meta_path = os.path.join(module.artifact_dir, "feature_meta.json")
    metadata_path = os.path.join(module.artifact_dir, "metadata.json")

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

    return {
        "model": model,
        "feature_meta": feature_meta,
        "metadata": metadata,
    }


def predict(
    df: pd.DataFrame,
    module: ModuleConfig,
    artifacts: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Score a DataFrame and return predictions with tiers.

    Returns DataFrame with original columns plus:
      probability, tier, rank, value_at_risk,
      churn_risk_pct, urgency_score, renewal_window_label,
      arr_at_risk, recommended_action, account_status
    """
    if artifacts is None:
        artifacts = load_model(module)

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

    # recommended_action
    dsll = result["days_since_last_login"] if "days_since_last_login" in result.columns else pd.Series(0, index=result.index)
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

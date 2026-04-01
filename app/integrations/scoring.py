"""Live scoring — builds a DataFrame from stored accounts + signals, runs the model."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd

from app.engine.config import get_module
from app.modules.churn.adapter import (
    add_derived_features,
    compute_action_tier,
    compute_recommended_action,
    compute_renewal_window_label,
    compute_urgency_score,
    normalize_columns,
)
from app.integrations.models import ChurnScore
from app.storage import repo

logger = logging.getLogger(__name__)


def _build_scoring_dataframe(tenant_id: str = repo.DEFAULT_TENANT) -> pd.DataFrame:
    """Merge accounts + latest signals into a flat DataFrame ready for scoring."""
    accounts = repo.list_accounts(limit=50000, tenant_id=tenant_id)
    if not accounts:
        return pd.DataFrame()

    # Fetch all signals in one query (keyed by internal account UUID)
    signals_by_account = repo.bulk_latest_signals(tenant_id=tenant_id)

    rows = []
    for acct in accounts:
        sig = signals_by_account.get(acct.get("id")) or None
        row: Dict[str, Any] = {
            "account_id": acct["external_id"],
            "snapshot_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "arr": acct.get("arr"),
            "plan": acct.get("plan"),
            "seats": acct.get("seats") or (sig.get("seats") if sig else None),
            "industry": acct.get("industry"),
            "company_size": acct.get("company_size"),
        }
        if sig:
            extra = sig.get("extra") or {}
            row.update({
                "monthly_logins": sig.get("monthly_logins"),
                "support_tickets": sig.get("support_tickets"),
                "nps_score": sig.get("nps_score"),
                "days_since_last_login": sig.get("days_since_last_login"),
                "contract_months_remaining": sig.get("contract_months_remaining"),
                "days_until_renewal": sig.get("days_until_renewal"),
                "auto_renew_flag": sig.get("auto_renew_flag"),
                "renewal_status": sig.get("renewal_status"),
                "contact_count": extra.get("contact_count"),
                "deal_count": extra.get("deal_count"),
                "days_since_last_activity": extra.get("days_since_last_activity"),
            })
        rows.append(row)

    return pd.DataFrame(rows)


def _enrich_drivers_with_baselines(
    drivers: List[Dict[str, Any]],
    row: "pd.Series",
    feature_stats_by_outcome: Dict[str, Any],
    feature_names: List[str],
    X_row: "Any",
) -> List[Dict[str, Any]]:
    """Add raw feature value + retained/churned baselines to each driver dict."""
    feat_idx = {name: i for i, name in enumerate(feature_names)}
    enriched = []
    for d in drivers:
        feat = d["feature"]
        d = d.copy()
        # Raw feature value from the numeric matrix (post-imputation)
        if feat in feat_idx:
            raw_val = float(X_row[feat_idx[feat]])
            import math
            d["value"] = None if not math.isfinite(raw_val) else raw_val
        else:
            d["value"] = None
        # Baselines from training data split by outcome
        stats = feature_stats_by_outcome.get(feat, {})
        d["retained_mean"] = stats.get("retained_mean")
        d["churned_mean"] = stats.get("churned_mean")
        enriched.append(d)
    return enriched


def score_accounts(
    tenant_id: str = repo.DEFAULT_TENANT,
    artifact_dir: Optional[str] = None,
) -> List[ChurnScore]:
    """Score all stored accounts using the trained churn model.

    artifact_dir should be the versioned run path from store.get_current_model_run().
    If not provided, falls back to the flat per-tenant path (legacy).

    Returns a list of ChurnScore objects (also persisted to DB).
    """
    module = get_module("churn")
    if artifact_dir is None:
        artifact_dir = module.get_artifact_dir(tenant_id)
    model_path = os.path.join(artifact_dir, "model.joblib")
    base_model_path = os.path.join(artifact_dir, "base_model.joblib")
    shap_bg_path = os.path.join(artifact_dir, "shap_background.npy")
    meta_path = os.path.join(artifact_dir, "metadata.json")

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No trained model found at {model_path}. Train the model first."
        )

    df = _build_scoring_dataframe(tenant_id=tenant_id)
    if df.empty:
        logger.info("No accounts to score")
        return []

    feature_meta_path = os.path.join(artifact_dir, "feature_meta.json")
    with open(feature_meta_path) as _f:
        feature_meta = json.load(_f)

    # Load feature_stats_by_outcome from metadata for explanation baselines
    feature_stats_by_outcome: Dict[str, Any] = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as _f:
                metadata_json = json.load(_f)
            feature_stats_by_outcome = metadata_json.get("feature_stats_by_outcome", {})
        except Exception:
            logger.warning("Could not load feature_stats_by_outcome from metadata")

    df = normalize_columns(df)
    df = add_derived_features(df)

    from app.engine.features import prepare_features

    model = joblib.load(model_path)

    X, _y, feat_names, _meta = prepare_features(
        df, module, fit=False, feature_meta=feature_meta,
    )

    probs = model.predict_proba(X)[:, 1]
    probs = probs.clip(module.calibration.prob_floor, module.calibration.prob_ceil)

    # SHAP per-account driver extraction
    from app.engine.shap_utils import (
        build_explainer, compute_shap_values, extract_top_drivers,
        compute_confidence_level, aggregate_portfolio_shap,
    )
    import numpy as _np
    shap_vals_arr = None
    raw_drivers_all: list = []
    if not os.path.exists(base_model_path):
        logger.warning(
            "score_accounts: base_model.joblib not found at %s — SHAP drivers disabled. "
            "Retrain the model to generate this artifact.", base_model_path
        )
    if not os.path.exists(shap_bg_path):
        logger.warning(
            "score_accounts: shap_background.npy not found at %s — SHAP drivers disabled. "
            "Retrain the model to generate this artifact.", shap_bg_path
        )

    if os.path.exists(base_model_path) and os.path.exists(shap_bg_path):
        try:
            base_model = joblib.load(base_model_path)
            shap_background = _np.load(shap_bg_path)
            explainer = build_explainer(base_model, shap_background)
            shap_vals_arr = compute_shap_values(explainer, X)
            raw_drivers_all = [
                extract_top_drivers(shap_vals_arr[i], feat_names, n=5)
                for i in range(len(shap_vals_arr))
            ]
        except Exception:
            logger.exception("SHAP computation failed in score_accounts")

    # LLM labeling — single batch call for all unique features
    from app.engine.driver_labels import label_drivers_batch
    labeled_drivers_all = label_drivers_batch(raw_drivers_all) if raw_drivers_all else []

    # Build scores
    now = datetime.now(timezone.utc)
    scores: List[ChurnScore] = []
    arr_values: List[Optional[float]] = []

    for row_i, (_, row) in enumerate(df.iterrows()):
        prob = float(probs[row_i])
        tier = module.tiers.classify(prob)
        arr = row.get("arr")
        arr_num = float(arr) if arr is not None and pd.notna(arr) else None
        arr_at_risk = round(prob * arr_num, 2) if arr_num is not None else None
        arr_values.append(arr_num)

        dur = row.get("days_until_renewal")
        urgency = compute_urgency_score(prob, dur) if pd.notna(dur) else None

        renewal_label = compute_renewal_window_label(dur) if pd.notna(dur) else "unknown"
        dsl = row.get("days_since_last_login") or row.get("days_since_last_activity") or 0
        action = compute_recommended_action(prob * 100, renewal_label, dsl)

        # SHAP drivers + confidence
        raw_drivers: list = labeled_drivers_all[row_i] if row_i < len(labeled_drivers_all) else []
        confidence_level: Optional[str] = None
        if shap_vals_arr is not None:
            row_dict = row.to_dict()
            n_valued = sum(
                1 for k, v in row_dict.items()
                if k not in ("account_id", "snapshot_date")
                and v is not None
                and not (isinstance(v, float) and pd.isna(v))
            )
            confidence_level = compute_confidence_level(n_valued, len(feat_names))
            # Enrich drivers with raw values and baselines
            raw_drivers = _enrich_drivers_with_baselines(
                raw_drivers, row, feature_stats_by_outcome, feat_names, X[row_i]
            )

        action_tier = compute_action_tier(urgency, confidence_level, prob * 100)

        scores.append(ChurnScore(
            external_id=row["account_id"],
            scored_at=now,
            churn_probability=round(prob, 4),
            tier=tier,
            arr_at_risk=arr_at_risk,
            urgency_score=urgency,
            recommended_action=action,
            renewal_window_label=renewal_label,
            top_drivers=raw_drivers,
            confidence_level=confidence_level,
            action_tier=action_tier,
        ))

    # Portfolio SHAP aggregation — persist summary for dashboard
    if shap_vals_arr is not None and len(feat_names) > 0:
        try:
            portfolio_drivers = aggregate_portfolio_shap(
                shap_vals_arr, feat_names, arr_values, arr_cap_pct=0.20, top_n=10,
            )
            # Add labels to portfolio drivers using the rule-based cleaner
            # (LLM labeling happens per-account above; portfolio uses fast path)
            from app.engine.driver_labels import clean_feature_name
            for pd_item in portfolio_drivers:
                pd_item["label"] = clean_feature_name(pd_item["feature"], pd_item["direction"])

            from app.engine.explanation import build_portfolio_narrative
            narrative = build_portfolio_narrative(portfolio_drivers, n_accounts=len(scores))

            outputs_dir = os.path.join(
                os.environ.get("DATA_DIR", "/data"), "outputs", tenant_id
            )
            os.makedirs(outputs_dir, exist_ok=True)
            summary_path = os.path.join(outputs_dir, "portfolio_shap_summary.json")
            summary = {
                "scored_at": now.isoformat(),
                "n_accounts": len(scores),
                "total_arr": sum(v for v in arr_values if v is not None),
                "drivers": portfolio_drivers,
                "narrative": narrative,
            }
            with open(summary_path, "w") as _f:
                json.dump(summary, _f, indent=2)
            logger.info("Portfolio SHAP summary written to %s", summary_path)
        except Exception:
            logger.exception("Portfolio SHAP aggregation failed")

    # Persist
    repo.insert_scores(scores, tenant_id=tenant_id)
    logger.info("Scored %d accounts", len(scores))

    return scores

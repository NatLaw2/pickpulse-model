"""Live scoring — builds a DataFrame from stored accounts + signals, runs the model."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd

from app.engine.config import get_module
from app.modules.churn.adapter import (
    add_derived_features,
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

    # Fetch all signals in one query (keyed by internal account UUID) rather
    # than making N+1 per-account calls which are fragile under load.
    signals_by_account = repo.bulk_latest_signals(tenant_id=tenant_id)

    # TEMPORARY DIAGNOSTIC
    print(f"[scoring] accounts={len(accounts)} signals_by_account keys={len(signals_by_account)}")
    if accounts:
        sample_acct = accounts[0]
        sample_id = sample_acct.get("id")
        sample_ext = sample_acct.get("external_id")
        sample_sig = signals_by_account.get(sample_id)
        print(f"[scoring] sample acct id={sample_id!r} external_id={sample_ext!r}")
        print(f"[scoring] sample sig found={sample_sig is not None} dur={sample_sig.get('days_until_renewal') if sample_sig else 'N/A'}")
        if not sample_sig and signals_by_account:
            # Show a sample key from signals_by_account to check UUID format
            sample_sig_key = next(iter(signals_by_account))
            print(f"[scoring] first signals_by_account key={sample_sig_key!r} (vs acct id={sample_id!r})")

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
                # Universal CRM-derived signals stored in sig.extra by HubSpot connector
                "contact_count": extra.get("contact_count"),
                "deal_count": extra.get("deal_count"),
                "days_since_last_activity": extra.get("days_since_last_activity"),
            })
        rows.append(row)

    return pd.DataFrame(rows)


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

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No trained model found at {model_path}. Train the model first."
        )

    df = _build_scoring_dataframe(tenant_id=tenant_id)
    if df.empty:
        logger.info("No accounts to score")
        return []

    import json as _json
    meta_path = os.path.join(artifact_dir, "feature_meta.json")
    with open(meta_path) as _f:
        feature_meta = _json.load(_f)

    df = normalize_columns(df)
    df = add_derived_features(df)

    # Prepare features using the engine
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
        compute_confidence_level,
    )
    shap_vals_arr = None
    if os.path.exists(base_model_path) and os.path.exists(shap_bg_path):
        try:
            import numpy as _np
            base_model = joblib.load(base_model_path)
            shap_background = _np.load(shap_bg_path)
            explainer = build_explainer(base_model, shap_background)
            shap_vals_arr = compute_shap_values(explainer, X)
        except Exception as _exc:
            logger.warning("SHAP computation failed in score_accounts: %s", _exc)

    # Build scores
    now = datetime.now(timezone.utc)
    scores: List[ChurnScore] = []

    for i, row in df.iterrows():
        prob = float(probs[i])
        tier = module.tiers.classify(prob)
        arr = row.get("arr")
        arr_at_risk = round(prob * arr, 2) if arr and pd.notna(arr) else None

        dur = row.get("days_until_renewal")
        urgency = compute_urgency_score(prob, dur) if pd.notna(dur) else None

        renewal_label = compute_renewal_window_label(dur) if pd.notna(dur) else "unknown"
        dsl = row.get("days_since_last_login") or row.get("days_since_last_activity") or 0
        action = compute_recommended_action(prob * 100, renewal_label, dsl)

        # SHAP drivers + confidence for this account
        drivers: list = []
        confidence_level: str | None = None
        if shap_vals_arr is not None:
            drivers = extract_top_drivers(shap_vals_arr[i], feat_names, n=5)
            # Count non-null features from original row (proxy for data completeness)
            row_dict = row.to_dict()
            n_valued = sum(
                1 for k, v in row_dict.items()
                if k not in ("account_id", "snapshot_date")
                and v is not None
                and not (isinstance(v, float) and pd.isna(v))
            )
            confidence_level = compute_confidence_level(n_valued, len(feat_names))

        scores.append(ChurnScore(
            external_id=row["account_id"],
            scored_at=now,
            churn_probability=round(prob, 4),
            tier=tier,
            arr_at_risk=arr_at_risk,
            urgency_score=urgency,
            recommended_action=action,
            renewal_window_label=renewal_label,
            top_drivers=drivers,
            confidence_level=confidence_level,
        ))

    # TEMPORARY DIAGNOSTIC
    if scores:
        s0 = scores[0]
        print(f"[scoring] sample score: ext={s0.external_id!r} prob={s0.churn_probability} renewal={s0.renewal_window_label!r} urgency={s0.urgency_score}")

    # Persist
    repo.insert_scores(scores, tenant_id=tenant_id)
    logger.info("Scored %d accounts", len(scores))

    return scores

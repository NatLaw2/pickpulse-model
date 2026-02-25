"""Live scoring — builds a DataFrame from stored accounts + signals, runs the model."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

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


def _build_scoring_dataframe() -> pd.DataFrame:
    """Merge accounts + latest signals into a flat DataFrame ready for scoring."""
    accounts = repo.list_accounts(limit=50000)
    if not accounts:
        return pd.DataFrame()

    rows = []
    for acct in accounts:
        sig = repo.latest_signals(acct["external_id"])
        row: Dict[str, Any] = {
            "customer_id": acct["external_id"],
            "snapshot_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "arr": acct.get("arr"),
            "plan": acct.get("plan"),
            "seats": acct.get("seats") or (sig.get("seats") if sig else None),
            "industry": acct.get("industry"),
            "company_size": acct.get("company_size"),
        }
        if sig:
            row.update({
                "monthly_logins": sig.get("monthly_logins"),
                "support_tickets": sig.get("support_tickets"),
                "nps_score": sig.get("nps_score"),
                "days_since_last_login": sig.get("days_since_last_login"),
                "contract_months_remaining": sig.get("contract_months_remaining"),
                "days_until_renewal": sig.get("days_until_renewal"),
                "auto_renew_flag": sig.get("auto_renew_flag"),
                "renewal_status": sig.get("renewal_status"),
            })
        rows.append(row)

    return pd.DataFrame(rows)


def score_accounts() -> List[ChurnScore]:
    """Score all stored accounts using the trained churn model.

    Returns a list of ChurnScore objects (also persisted to DB).
    """
    module = get_module("churn")
    model_path = os.path.join(module.artifact_dir, "model.joblib")

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No trained model found at {model_path}. Train the model first."
        )

    df = _build_scoring_dataframe()
    if df.empty:
        logger.info("No accounts to score")
        return []

    # Normalize and add derived features (same pipeline as predict.py)
    df = normalize_columns(df)
    df = add_derived_features(df)

    # Load model + feature metadata
    model = joblib.load(model_path)
    meta_path = os.path.join(module.artifact_dir, "feature_meta.json")

    # Prepare features using the engine
    from app.engine.features import prepare_features

    feature_df = prepare_features(df, module, fit=False, meta_path=meta_path)

    # Get probabilities
    probs = model.predict_proba(feature_df)[:, 1]
    probs = probs.clip(module.calibration.prob_floor, module.calibration.prob_ceil)

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
        dsl = row.get("days_since_last_login", 0) or 0
        action = compute_recommended_action(prob * 100, renewal_label, dsl)

        scores.append(ChurnScore(
            external_id=row["customer_id"],
            scored_at=now,
            churn_probability=round(prob, 4),
            tier=tier,
            arr_at_risk=arr_at_risk,
            urgency_score=urgency,
            recommended_action=action,
        ))

    # Persist
    repo.insert_scores(scores)
    logger.info("Scored %d accounts", len(scores))

    return scores

"""Label auditor — counts labeled examples, assesses reliability, and returns
a ViabilityReport that determines whether model training should proceed.

Requires an active HubSpot connector to pull real account data.
Generalizes to any portal — no company-specific logic.

Usage:
    report = run_audit(connector, candidate, tenant_id)
    save_audit(tenant_id, report)
    # Later:
    report = load_audit(tenant_id)
"""
from __future__ import annotations

import json
import logging
import os
import statistics
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.integrations.label_discovery import LabelSourceCandidate
from app.integrations.normalization import safe_date, days_since

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Viability thresholds
# ---------------------------------------------------------------------------

PROCEED_MIN_POSITIVE       = 100
PROCEED_MAX_CLASS_RATIO    = 10.0
PROCEED_MIN_RELIABILITY    = 0.70

EXPLORATORY_MIN_POSITIVE   = 50
EXPLORATORY_MAX_CLASS_RATIO = 15.0
EXPLORATORY_MIN_RELIABILITY = 0.50

INSUFFICIENT_MIN_POSITIVE  = 20

# Max records fetched during audit (keeps it fast on large portals)
MAX_AUDIT_RECORDS = 500
MAX_DEAL_RECORDS  = 800


# ---------------------------------------------------------------------------
# Property-based label counting
# ---------------------------------------------------------------------------

def _count_property_labels(
    connector: Any,
    candidate: LabelSourceCandidate,
    max_records: int = MAX_AUDIT_RECORDS,
) -> Tuple[int, int, int, List[Dict[str, Any]]]:
    """Pull companies with the label field populated and count outcomes.

    Returns:
        (positive_count, negative_count, unlabeled_count, sample_records)
        where sample_records contain {label_value, modified_date} for
        reliability assessment.
    """
    prop_name = candidate.raw_field
    positive_set = {v.lower() for v in candidate.positive_values}
    negative_set = {v.lower() for v in candidate.negative_values}

    positive_count = 0
    negative_count = 0
    unlabeled_count = 0
    sample_records: List[Dict[str, Any]] = []

    after: Optional[str] = None
    total_fetched = 0

    while total_fetched < max_records:
        batch_size = min(100, max_records - total_fetched)
        payload: Dict[str, Any] = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": prop_name,
                    "operator": "HAS_PROPERTY",
                }]
            }],
            "properties": [prop_name, "hs_lastmodifieddate", "notes_last_activity_date"],
            "limit": batch_size,
        }
        if after:
            payload["after"] = after

        try:
            r = connector._request(
                "POST",
                "https://api.hubapi.com/crm/v3/objects/companies/search",
                json=payload,
                timeout=20,
            )
            if r.status_code != 200:
                logger.warning("[label_auditor] property search returned %d", r.status_code)
                break
            data = r.json()
        except Exception as exc:
            logger.warning("[label_auditor] property fetch error: %s", exc)
            break

        for company in data.get("results", []):
            props = company.get("properties", {})
            raw_val = (props.get(prop_name) or "").lower().strip()

            if raw_val in positive_set:
                positive_count += 1
                outcome = 1
            elif raw_val in negative_set:
                negative_count += 1
                outcome = 0
            else:
                unlabeled_count += 1
                outcome = None

            if outcome is not None:
                modified = safe_date(
                    props.get("hs_lastmodifieddate") or
                    props.get("notes_last_activity_date")
                )
                sample_records.append({
                    "outcome": outcome,
                    "date": modified,
                    "days_since": days_since(modified) if modified else None,
                })

            total_fetched += 1

        paging = data.get("paging", {}).get("next", {})
        after = paging.get("after") if paging else None
        if not after:
            break

    return positive_count, negative_count, unlabeled_count, sample_records


# ---------------------------------------------------------------------------
# Deal-based label counting
# ---------------------------------------------------------------------------

def _count_deal_labels(
    connector: Any,
    candidate: LabelSourceCandidate,
    max_records: int = MAX_DEAL_RECORDS,
) -> Tuple[int, int, int, List[Dict[str, Any]]]:
    """Pull closed deals from the identified pipeline and count outcomes.

    Uses the associations batch endpoint to resolve company IDs efficiently.
    Deduplicates to latest deal per company.

    Returns:
        (positive_count, negative_count, 0, sample_records)
    """
    pipeline_id = candidate.details.get("pipeline_id", candidate.raw_field)
    lost_stage_ids = set(candidate.positive_values)
    won_stage_ids = set(candidate.negative_values)
    all_stage_ids = list(lost_stage_ids | won_stage_ids)

    # Pull deals from pipeline with closed stages
    deals: List[Dict[str, Any]] = []
    after: Optional[str] = None

    while len(deals) < max_records:
        batch_size = min(100, max_records - len(deals))
        payload: Dict[str, Any] = {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "pipeline", "operator": "EQ", "value": pipeline_id},
                    {"propertyName": "dealstage", "operator": "IN", "values": all_stage_ids},
                ]
            }],
            "properties": ["dealstage", "closedate"],
            "limit": batch_size,
        }
        if after:
            payload["after"] = after

        try:
            r = connector._request(
                "POST",
                "https://api.hubapi.com/crm/v3/objects/deals/search",
                json=payload,
                timeout=20,
            )
            if r.status_code != 200:
                logger.warning("[label_auditor] deal search returned %d", r.status_code)
                break
            data = r.json()
        except Exception as exc:
            logger.warning("[label_auditor] deal fetch error: %s", exc)
            break

        results = data.get("results", [])
        if not results:
            break

        deals.extend(results)
        paging = data.get("paging", {}).get("next", {})
        after = paging.get("after") if paging else None
        if not after:
            break

    if not deals:
        return 0, 0, 0, []

    # Resolve company associations in batches of 100
    deal_ids = [d["id"] for d in deals]
    company_by_deal: Dict[str, str] = {}  # deal_id → company_id

    for i in range(0, len(deal_ids), 100):
        batch = deal_ids[i:i + 100]
        try:
            r = connector._request(
                "POST",
                "https://api.hubapi.com/crm/v3/associations/deals/companies/batch/read",
                json={"inputs": [{"id": did} for did in batch]},
                timeout=20,
            )
            if r.status_code == 200:
                for item in r.json().get("results", []):
                    fid = item.get("from", {}).get("id")
                    associations = item.get("to", [])
                    if fid and associations:
                        company_by_deal[fid] = associations[0]["id"]
        except Exception as exc:
            logger.warning("[label_auditor] deal→company association batch failed: %s", exc)

    # Build deal metadata index
    deal_meta: Dict[str, Dict] = {d["id"]: d for d in deals}

    # Deduplicate: keep latest deal per company
    latest_per_company: Dict[str, Dict] = {}
    for deal in deals:
        cid = company_by_deal.get(deal["id"])
        if not cid:
            continue
        close_date = safe_date(deal.get("properties", {}).get("closedate"))
        existing = latest_per_company.get(cid)
        if existing is None:
            latest_per_company[cid] = {**deal, "_company_id": cid, "_close_date": close_date}
        else:
            # Keep later close_date
            if close_date and (not existing["_close_date"] or close_date > existing["_close_date"]):
                latest_per_company[cid] = {**deal, "_company_id": cid, "_close_date": close_date}

    # Count outcomes
    positive_count = 0
    negative_count = 0
    sample_records: List[Dict[str, Any]] = []

    for deal in latest_per_company.values():
        stage = (deal.get("properties", {}).get("dealstage") or "").strip()
        close_date = deal.get("_close_date")

        if stage in lost_stage_ids:
            positive_count += 1
            outcome = 1
        elif stage in won_stage_ids:
            negative_count += 1
            outcome = 0
        else:
            continue

        sample_records.append({
            "outcome": outcome,
            "date": close_date,
            "days_since": days_since(close_date) if close_date else None,
        })

    return positive_count, negative_count, 0, sample_records


# ---------------------------------------------------------------------------
# Reliability assessment
# ---------------------------------------------------------------------------

def _assess_reliability(
    sample_records: List[Dict[str, Any]],
    positive_count: int,
    negative_count: int,
    connector: Any,
) -> Dict[str, Any]:
    """Score label reliability from 0.0 to 1.0 on four factors.

    Returns a dict with score, factor scores, issues list, and diagnostics.
    """
    issues: List[str] = []
    factor_scores: Dict[str, float] = {}

    records_with_dates = [r for r in sample_records if r.get("date")]

    # Factor 1: Temporal spread (0.30 weight)
    # Are labeled outcomes spread over ≥ 6 months?
    temporal_spread_months = 0
    temporal_score = 0.0
    if len(records_with_dates) >= 2:
        dates = sorted(r["date"] for r in records_with_dates)
        try:
            d_first = datetime.strptime(dates[0], "%Y-%m-%d")
            d_last = datetime.strptime(dates[-1], "%Y-%m-%d")
            temporal_spread_months = (d_last - d_first).days // 30

            if temporal_spread_months >= 12:
                temporal_score = 1.0
            elif temporal_spread_months >= 6:
                temporal_score = 0.75
            elif temporal_spread_months >= 3:
                temporal_score = 0.50
            else:
                temporal_score = 0.15
                issues.append(
                    f"All labeled outcomes span only {temporal_spread_months} months — "
                    "may be a data entry event rather than historical tracking"
                )
        except (ValueError, TypeError):
            temporal_score = 0.5
    elif records_with_dates:
        temporal_score = 0.4
        issues.append("Most labeled records have no date — temporal spread cannot be assessed")
    else:
        temporal_score = 0.0
        issues.append("No dates found on labeled records — reliability cannot be verified")

    factor_scores["temporal_spread"] = temporal_score

    # Factor 2: Recency (0.25 weight)
    # Is the most recent outcome ≤ 18 months ago?
    recency_score = 0.0
    recency_ok = False
    most_recent_date: Optional[str] = None
    if records_with_dates:
        most_recent_date = max(r["date"] for r in records_with_dates)
        days_ago = days_since(most_recent_date) or 9999
        if days_ago <= 180:
            recency_score = 1.0
            recency_ok = True
        elif days_ago <= 365:
            recency_score = 0.80
            recency_ok = True
        elif days_ago <= 548:  # 18 months
            recency_score = 0.55
            recency_ok = True
        else:
            recency_score = 0.20
            issues.append(
                f"Most recent labeled outcome is {days_ago // 30} months ago — "
                "data may not reflect current patterns"
            )

    factor_scores["recency"] = recency_score

    # Factor 3: Balance sanity (0.20 weight)
    # Is churn rate between 5% and 60%?
    balance_score = 0.0
    balance_ok = False
    total = positive_count + negative_count
    churn_rate = positive_count / total if total > 0 else 0.0

    if 0.05 <= churn_rate <= 0.60:
        balance_score = 1.0
        balance_ok = True
    elif 0.02 <= churn_rate < 0.05 or 0.60 < churn_rate <= 0.80:
        balance_score = 0.50
        issues.append(
            f"Class balance is skewed ({churn_rate:.0%} churn rate) — "
            "model will use class weighting to compensate"
        )
    else:
        balance_score = 0.10
        issues.append(
            f"Extreme class imbalance ({churn_rate:.0%} churn rate) — "
            "model training will be unreliable; consider expanding label coverage"
        )

    factor_scores["balance"] = balance_score

    # Factor 4: Consistency check (0.25 weight)
    # Are there companies with no recent activity that are labeled "retained"?
    # Heuristic: pull a small sample of oldest-activity companies and check labels.
    suspicious_count = 0
    consistency_score = 0.8  # default to OK; degraded if suspicious accounts found

    try:
        r = connector._request(
            "POST",
            "https://api.hubapi.com/crm/v3/objects/companies/search",
            json={
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "notes_last_activity_date",
                        "operator": "LT",
                        "value": (
                            datetime.now(timezone.utc) - timedelta(days=730)
                        ).strftime("%Y-%m-%d"),
                    }]
                }],
                "properties": ["notes_last_activity_date"],
                "limit": 100,
            },
            timeout=15,
        )
        if r.status_code == 200:
            old_companies_total = r.json().get("total", 0)
            # These are companies with no activity in 2+ years
            # If the portfolio has many of these AND they're mostly labeled "retained",
            # something is wrong with the labels.
            # We approximate: if old_inactive > 20% of negative_count, flag it
            if negative_count > 0 and old_companies_total > negative_count * 0.20:
                suspicious_count = old_companies_total
                consistency_score = 0.55
                issues.append(
                    f"{old_companies_total} companies have had no activity for 2+ years — "
                    "verify that non-renewed accounts are correctly labeled"
                )
    except Exception as exc:
        logger.debug("[label_auditor] consistency check failed: %s", exc)

    factor_scores["consistency"] = consistency_score

    # Weighted reliability score
    weights = {
        "temporal_spread": 0.30,
        "recency": 0.25,
        "balance": 0.20,
        "consistency": 0.25,
    }
    reliability_score = sum(
        factor_scores[k] * weights[k] for k in weights
    )

    oldest_date: Optional[str] = None
    if records_with_dates:
        oldest_date = min(r["date"] for r in records_with_dates)

    return {
        "score": round(reliability_score, 3),
        "factor_scores": {k: round(v, 3) for k, v in factor_scores.items()},
        "issues": issues,
        "temporal_spread_months": temporal_spread_months,
        "recency_ok": recency_ok,
        "balance_ok": balance_ok,
        "most_recent_outcome": most_recent_date,
        "oldest_outcome": oldest_date,
        "suspicious_unlabeled_count": suspicious_count,
    }


# ---------------------------------------------------------------------------
# Viability decision
# ---------------------------------------------------------------------------

def _make_viability_decision(
    positive_count: int,
    negative_count: int,
    reliability: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply threshold logic to produce the final viability decision."""
    total = positive_count + negative_count
    class_ratio = (negative_count / positive_count) if positive_count > 0 else float("inf")
    rel_score = reliability.get("score", 0.0)
    next_steps: List[str] = list(reliability.get("issues", []))

    # Blocked: not enough data to learn from
    if positive_count == 0:
        return {
            "viability": "blocked",
            "rationale": "No positive (churned/non-renewed) examples found. Label source may exist but contains no labeled positive outcomes.",
            "confidence_mode": None,
            "next_steps": [
                "Verify the selected label source is correctly identifying churned accounts",
                "Consider manually labeling historical non-renewed accounts",
                "Check if non-renewals are tracked in a different pipeline or property",
            ],
        }

    if positive_count < INSUFFICIENT_MIN_POSITIVE:
        return {
            "viability": "blocked",
            "rationale": f"Only {positive_count} positive examples — minimum {INSUFFICIENT_MIN_POSITIVE} required. Model cannot learn reliable patterns from this sample.",
            "confidence_mode": None,
            "next_steps": [
                f"Identify and label at least {INSUFFICIENT_MIN_POSITIVE - positive_count} additional churned/non-renewed accounts",
                "Consider whether historical deal data or a different property captures more outcomes",
            ],
        }

    # Proceed: sufficient data, good quality
    if (
        positive_count >= PROCEED_MIN_POSITIVE
        and class_ratio <= PROCEED_MAX_CLASS_RATIO
        and rel_score >= PROCEED_MIN_RELIABILITY
    ):
        return {
            "viability": "proceed",
            "rationale": (
                f"{positive_count} positive examples, {negative_count} negative, "
                f"class ratio {class_ratio:.1f}:1, reliability {rel_score:.2f}. "
                "Model training viable."
            ),
            "confidence_mode": "standard",
            "next_steps": next_steps,
        }

    # Exploratory: marginal but trainable
    exploratory_reasons: List[str] = []
    if positive_count < PROCEED_MIN_POSITIVE:
        exploratory_reasons.append(f"only {positive_count} positive examples (target: {PROCEED_MIN_POSITIVE}+)")
    if class_ratio > PROCEED_MAX_CLASS_RATIO:
        exploratory_reasons.append(f"class ratio {class_ratio:.1f}:1 (target: ≤{PROCEED_MAX_CLASS_RATIO}:1)")
    if rel_score < PROCEED_MIN_RELIABILITY:
        exploratory_reasons.append(f"reliability score {rel_score:.2f} (target: ≥{PROCEED_MIN_RELIABILITY})")

    if (
        positive_count >= EXPLORATORY_MIN_POSITIVE
        and class_ratio <= EXPLORATORY_MAX_CLASS_RATIO
        and rel_score >= EXPLORATORY_MIN_RELIABILITY
    ):
        next_steps.append(
            "Outputs will be marked as exploratory — treat predictions as directional, not authoritative"
        )
        if class_ratio > PROCEED_MAX_CLASS_RATIO:
            next_steps.append("Class weighting will be applied automatically to compensate for imbalance")
        return {
            "viability": "exploratory",
            "rationale": (
                f"Training viable but marginal: {', '.join(exploratory_reasons)}. "
                "Predictions will carry a confidence downgrade."
            ),
            "confidence_mode": "downgraded",
            "next_steps": next_steps,
        }

    # Insufficient: below exploratory threshold
    next_steps.append(
        f"Expand labeling to at least {EXPLORATORY_MIN_POSITIVE} positive examples before training"
    )
    return {
        "viability": "insufficient",
        "rationale": (
            f"Below exploratory threshold: {', '.join(exploratory_reasons)}. "
            "Training is possible but outputs will have very low confidence."
        ),
        "confidence_mode": "downgraded",
        "next_steps": next_steps,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_audit(
    connector: Any,
    candidate: LabelSourceCandidate,
    tenant_id: str,
) -> Dict[str, Any]:
    """Run the full label audit for a given candidate.

    Pulls actual account data from the portal, counts labeled examples,
    assesses reliability, and produces a ViabilityReport.

    Args:
        connector:  Active HubSpotConnector with valid token.
        candidate:  Best LabelSourceCandidate from label_discovery.
        tenant_id:  Tenant identifier for logging.

    Returns:
        ViabilityReport dict ready to be serialised and stored.
    """
    logger.info(
        "[label_auditor] Starting audit for tenant=%s label_type=%s field=%s",
        tenant_id, candidate.type, candidate.raw_field,
    )

    # Count labels
    if candidate.type in ("property", "lifecycle"):
        positive_count, negative_count, unlabeled_count, sample_records = (
            _count_property_labels(connector, candidate)
        )
    elif candidate.type == "deal":
        positive_count, negative_count, unlabeled_count, sample_records = (
            _count_deal_labels(connector, candidate)
        )
    else:
        logger.warning("[label_auditor] Unknown candidate type: %s", candidate.type)
        positive_count = negative_count = unlabeled_count = 0
        sample_records = []

    total_labeled = positive_count + negative_count
    class_ratio = (
        round(negative_count / positive_count, 2) if positive_count > 0 else None
    )

    # Oldest / most recent date from sample
    dated = [r for r in sample_records if r.get("date")]
    oldest_outcome = min(r["date"] for r in dated) if dated else None
    most_recent_outcome = max(r["date"] for r in dated) if dated else None

    # Reliability assessment
    reliability = _assess_reliability(
        sample_records, positive_count, negative_count, connector
    )

    # Viability decision
    decision = _make_viability_decision(positive_count, negative_count, reliability)

    report: Dict[str, Any] = {
        "viability": decision["viability"],
        "label_source": candidate.to_dict(),
        "counts": {
            "positive_examples": positive_count,
            "negative_examples": negative_count,
            "unlabeled_companies": unlabeled_count,
            "total_labeled": total_labeled,
            "class_ratio": class_ratio,
            "oldest_outcome": oldest_outcome,
            "most_recent_outcome": most_recent_outcome,
        },
        "reliability": reliability,
        "decision": decision,
        "audit_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
    }

    logger.info(
        "[label_auditor] Audit complete: viability=%s positive=%d negative=%d reliability=%.2f",
        decision["viability"], positive_count, negative_count, reliability["score"],
    )
    return report


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _audit_path(tenant_id: str) -> str:
    data_dir = os.environ.get("DATA_DIR", "data")
    out_dir = os.path.join(data_dir, "outputs", tenant_id)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, "viability_audit.json")


def save_audit(tenant_id: str, report: Dict[str, Any]) -> None:
    """Persist a ViabilityReport to disk."""
    path = _audit_path(tenant_id)
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("[label_auditor] Saved viability audit → %s", path)


def load_audit(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Load the most recent ViabilityReport for a tenant. Returns None if absent."""
    path = _audit_path(tenant_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[label_auditor] Could not load audit for %s: %s", tenant_id, exc)
        return None

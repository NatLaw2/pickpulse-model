"""Prediction vs Actual Reconciliation Layer.

Matches churn_scores_daily predictions to account_outcomes and computes
production accuracy metrics: calibration, lift@top10, precision/recall,
and time lag distribution.

Matching rule (per spec):
  For each 'churned' or 'renewed' outcome on effective_date D:
    Find the latest churn score for that account where:
      score_date <= D  AND  score_date >= D - 90 days
  If multiple scores qualify, use the one closest to D (latest).
  If none qualify, exclude this outcome from the dataset.

Edge cases handled:
  - Multiple outcomes per account: deduplicate to the latest effective_date.
  - 'expanded' outcomes: ignored (excluded from reconciliation).
  - Outcomes within the last 7 days: excluded (incomplete labeling risk).
  - No predictions found in window: outcome excluded (not counted as wrong).
  - Division by zero in metrics: returns None instead of crashing.

Cache:
  Results are stored as JSON in:
    {DATA_DIR}/outputs/{tenant_id}/production_accuracy.json
  Reads from cache if file is < CACHE_MAX_AGE_HOURS old.
  Force-refresh available via get_or_refresh(force=True).
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Predictions must fall within this many days before the outcome date.
MATCH_WINDOW_DAYS = 90

# Outcomes recorded within this many days of today may be incomplete.
EXCLUDE_RECENT_DAYS = 7

# Cached result is considered fresh for this many hours.
CACHE_MAX_AGE_HOURS = 24

# Outcome types we reconcile against. 'expanded' excluded in v1.
RECONCILE_OUTCOME_TYPES = ("churned", "renewed")

# Calibration bin edges: 10 equal-width bins across [0, 1].
BIN_EDGES = [i / 10 for i in range(11)]  # [0.0, 0.1, ..., 1.0]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(tenant_id: str) -> str:
    data_dir = os.environ.get("DATA_DIR", "data")
    out_dir = os.path.join(data_dir, "outputs", tenant_id)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, "production_accuracy.json")


def _cache_is_fresh(path: str, max_age_hours: int = CACHE_MAX_AGE_HOURS) -> bool:
    if not os.path.exists(path):
        return False
    age_hours = (datetime.now().timestamp() - os.path.getmtime(path)) / 3600
    return age_hours < max_age_hours


# ---------------------------------------------------------------------------
# Data fetchers (Supabase)
# ---------------------------------------------------------------------------

def _fetch_outcomes(tenant_id: str, before_date: str) -> List[Dict[str, Any]]:
    """Fetch churned/renewed outcomes with effective_date <= before_date.

    Ordered descending so that dedupe keeps the latest outcome per account.
    """
    from app.storage.db import get_client
    try:
        sb = get_client()
        res = (
            sb.table("account_outcomes")
            .select("account_id, outcome_type, effective_date")
            .eq("tenant_id", tenant_id)
            .in_("outcome_type", list(RECONCILE_OUTCOME_TYPES))
            .lte("effective_date", before_date)
            .order("effective_date", desc=True)
            .limit(5000)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning("reconciliation: _fetch_outcomes failed (%s)", exc)
        return []


def _fetch_scores(tenant_id: str, earliest_date: str) -> List[Dict[str, Any]]:
    """Fetch all churn scores with score_date >= earliest_date.

    Ordered ascending so _build_score_index can iterate in chronological order.
    churn_risk_pct is stored as 0-100; callers normalize to 0-1.
    """
    from app.storage.db import get_client
    try:
        sb = get_client()
        res = (
            sb.table("churn_scores_daily")
            .select("account_id, score_date, churn_risk_pct")
            .eq("tenant_id", tenant_id)
            .gte("score_date", earliest_date)
            .order("score_date", desc=False)
            .limit(50000)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning("reconciliation: _fetch_scores failed (%s)", exc)
        return []


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _dedupe_outcomes(outcomes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only the latest outcome per account_id.

    Rows are already ordered by effective_date DESC from the query, so the
    first occurrence per account is the latest valid outcome.
    """
    seen: set = set()
    result = []
    for row in outcomes:
        aid = row["account_id"]
        if aid not in seen:
            seen.add(aid)
            result.append(row)
    return result


def _build_score_index(
    scores: List[Dict[str, Any]],
) -> Dict[str, List[tuple]]:
    """Build {account_id: [(score_date_str, probability_0_to_1), ...]} sorted ascending.

    The query already returns rows ordered by score_date ASC, so we just group them.
    Normalizes churn_risk_pct (0-100) to probability (0.0-1.0).
    """
    index: Dict[str, List[tuple]] = {}
    for row in scores:
        aid = row["account_id"]
        prob = float(row["churn_risk_pct"]) / 100.0
        index.setdefault(aid, []).append((str(row["score_date"]), prob))
    return index


def _find_best_prediction(
    score_list: List[tuple],
    outcome_date: str,
    window_start: str,
) -> Optional[tuple]:
    """Return (score_date_str, probability) for the latest qualifying prediction.

    score_list is sorted ascending. We scan backwards to find the last entry
    with score_date <= outcome_date and >= window_start.
    """
    for score_date_str, prob in reversed(score_list):
        if score_date_str <= outcome_date:
            if score_date_str >= window_start:
                return (score_date_str, prob)
            # score_date < window_start: nothing further back will qualify
            break
    return None


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _bin_index(prob: float) -> int:
    """Map probability [0, 1] to a 0-9 bin index."""
    return min(int(prob * 10), 9)  # 1.0 would give index 10 → clamp to 9


def _safe_div(numerator: float, denominator: float) -> Optional[float]:
    return None if denominator == 0 else numerator / denominator


def _percentile(sorted_vals: List[float], p: float) -> float:
    """Linear-interpolation percentile from a sorted list."""
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    pos = p * (n - 1)
    lo = int(pos)
    hi = lo + 1
    if hi >= n:
        return float(sorted_vals[-1])
    return sorted_vals[lo] + (pos - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _compute_metrics(
    pairs: List[Dict[str, Any]],
    n_eligible: int,
) -> Dict[str, Any]:
    """Compute all accuracy metrics from a list of matched prediction-outcome pairs.

    Args:
        pairs:      Matched prediction-outcome pairs.
        n_eligible: Total eligible outcomes (after dedup) before matching.
                    Used to compute n_unmatched = n_eligible - n_pairs.
    """
    n_pairs = len(pairs)
    n_churned = sum(1 for p in pairs if p["churned"])
    n_renewed = n_pairs - n_churned
    overall_churn_rate = n_churned / n_pairs  # n_pairs > 0 guaranteed by caller

    # --- Calibration ---
    # Bucket into 10 equal-width bins; report only bins that have data.
    bin_probs: List[List[float]] = [[] for _ in range(10)]
    bin_labels: List[List[int]] = [[] for _ in range(10)]
    for p in pairs:
        idx = _bin_index(p["predicted_probability"])
        bin_probs[idx].append(p["predicted_probability"])
        bin_labels[idx].append(1 if p["churned"] else 0)

    calibration = []
    for i in range(10):
        n = len(bin_probs[i])
        if n == 0:
            continue
        calibration.append({
            "bin_lo": BIN_EDGES[i],
            "bin_hi": BIN_EDGES[i + 1],
            "predicted_avg": sum(bin_probs[i]) / n,
            "actual_rate": sum(bin_labels[i]) / n,
            "n": n,
        })

    # --- Lift at top 10% ---
    sorted_pairs = sorted(pairs, key=lambda p: p["predicted_probability"], reverse=True)
    top_k = max(1, math.ceil(n_pairs * 0.1))
    top_pairs = sorted_pairs[:top_k]
    top_10_churn_rate: Optional[float] = sum(1 for p in top_pairs if p["churned"]) / len(top_pairs)
    lift_top_10 = _safe_div(top_10_churn_rate, overall_churn_rate)

    # --- Precision / recall at threshold = 0.5 ---
    threshold = 0.5
    tp = sum(1 for p in pairs if p["predicted_probability"] >= threshold and p["churned"])
    fp = sum(1 for p in pairs if p["predicted_probability"] >= threshold and not p["churned"])
    fn = sum(1 for p in pairs if p["predicted_probability"] < threshold and p["churned"])
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)

    # --- Time lag distribution ---
    lags = sorted(p["days_between"] for p in pairs)
    time_lag_stats = {
        "min": lags[0],
        "max": lags[-1],
        "mean": round(sum(lags) / len(lags), 1),
        "median": round(_percentile(lags, 0.50), 1),
        "p25": round(_percentile(lags, 0.25), 1),
        "p75": round(_percentile(lags, 0.75), 1),
    }

    return {
        # Coverage stats: how many eligible outcomes were actually matchable
        "n_eligible_outcomes": n_eligible,
        "n_pairs": n_pairs,
        "n_unmatched": n_eligible - n_pairs,
        "n_churned": n_churned,
        "n_renewed": n_renewed,
        "overall_churn_rate": overall_churn_rate,
        "top_10_churn_rate": top_10_churn_rate,
        "lift_top_10": lift_top_10,
        "precision": precision,
        "recall": recall,
        "threshold": threshold,
        "calibration": calibration,
        "time_lag_stats": time_lag_stats,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _empty_result(n_eligible: int = 0) -> Dict[str, Any]:
    """Returned when there are no matched pairs."""
    return {
        # Coverage: how many outcomes were eligible vs. actually matched
        "n_eligible_outcomes": n_eligible,
        "n_pairs": 0,
        "n_unmatched": n_eligible,
        "n_churned": 0,
        "n_renewed": 0,
        "overall_churn_rate": None,
        "top_10_churn_rate": None,
        "lift_top_10": None,
        "precision": None,
        "recall": None,
        "threshold": 0.5,
        "calibration": [],
        "time_lag_stats": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_production_accuracy(tenant_id: str) -> Dict[str, Any]:
    """Build prediction-outcome pairs and return all production accuracy metrics.

    Returns an _empty_result() dict (n_pairs=0, all metrics None) when:
      - No outcomes exist yet
      - No predictions exist in the match window for any outcome
    """
    today = date.today()
    # Use effective_date, not recorded_at; exclude last 7 days (incomplete labeling).
    before_date = (today - timedelta(days=EXCLUDE_RECENT_DAYS)).isoformat()

    # 1. Fetch and deduplicate outcomes (latest per account)
    raw_outcomes = _fetch_outcomes(tenant_id, before_date)
    if not raw_outcomes:
        return _empty_result(n_eligible=0)

    outcomes = _dedupe_outcomes(raw_outcomes)
    n_eligible = len(outcomes)  # denominator for coverage stats

    # 2. Determine the earliest score date we could ever need
    min_outcome_date = min(str(row["effective_date"]) for row in outcomes)
    earliest_score = (
        date.fromisoformat(min_outcome_date) - timedelta(days=MATCH_WINDOW_DAYS)
    ).isoformat()

    # 3. Fetch scores and build per-account index
    scores = _fetch_scores(tenant_id, earliest_score)
    if not scores:
        return _empty_result(n_eligible=n_eligible)

    score_index = _build_score_index(scores)

    # 4. Match each outcome to a prediction
    pairs = []
    for outcome in outcomes:
        aid = outcome["account_id"]
        d_str = str(outcome["effective_date"])
        window_start = (
            date.fromisoformat(d_str) - timedelta(days=MATCH_WINDOW_DAYS)
        ).isoformat()

        account_scores = score_index.get(aid)
        if not account_scores:
            continue  # account was never scored → excluded from dataset

        match = _find_best_prediction(account_scores, d_str, window_start)
        if match is None:
            continue  # no prediction in the 90-day window → excluded from dataset

        score_date_str, prob = match
        pairs.append({
            "predicted_probability": prob,
            "prediction_date": score_date_str,
            "outcome_type": outcome["outcome_type"],
            "outcome_date": d_str,
            "days_between": (date.fromisoformat(d_str) - date.fromisoformat(score_date_str)).days,
            "churned": outcome["outcome_type"] == "churned",
        })

    if not pairs:
        return _empty_result(n_eligible=n_eligible)

    return _compute_metrics(pairs, n_eligible=n_eligible)


def get_or_refresh(
    tenant_id: str,
    force: bool = False,
    max_age_hours: int = CACHE_MAX_AGE_HOURS,
) -> Dict[str, Any]:
    """Return cached production accuracy result, recomputing if stale or forced.

    Args:
        tenant_id: Tenant to compute for.
        force:     If True, bypass cache and recompute from live data.
        max_age_hours: How old (in hours) the cache may be before recomputing.
    """
    path = _cache_path(tenant_id)

    if not force and _cache_is_fresh(path, max_age_hours):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("reconciliation: stale cache read failed (%s) — recomputing", exc)

    result = compute_production_accuracy(tenant_id)

    try:
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
    except Exception as exc:
        logger.warning("reconciliation: cache write failed (%s)", exc)

    return result

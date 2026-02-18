"""Agent 5: Error Attribution — loss categorization and actionable recommendations.

Categories:
  - bad_line:        negative CLV (locked bad odds)
  - model_miss:      positive CLV but wrong prediction
  - variance:        positive CLV, correct lean, unlucky outcome
  - calibration_gap: predicted confidence >> actual win rate in bucket
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ._supabase import fetch_pick_results, since_date
from ._math import safe_float


def _categorize_loss(
    pick: Dict[str, Any],
    clv: Optional[float],
    bucket_gap: float,
) -> str:
    """Assign one of the four error categories to a loss."""
    # calibration_gap: confidence significantly above bucket win rate
    if bucket_gap > 0.10:
        return "calibration_gap"

    if clv is not None and math.isfinite(clv):
        if clv < -0.005:
            return "bad_line"
        if clv > 0.005:
            return "model_miss"

    return "variance"


def _bucket_win_rates(results: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute actual win rate by confidence bucket."""
    buckets: Dict[str, List[int]] = {"low": [], "mid": [], "high": []}
    for r in results:
        conf = safe_float(r.get("confidence"))
        won = 1 if r.get("result") == "win" else 0
        if r.get("result") not in ("win", "loss"):
            continue
        if conf is None or conf < 0.50:
            buckets["low"].append(won)
        elif conf < 0.65:
            buckets["mid"].append(won)
        else:
            buckets["high"].append(won)

    rates: Dict[str, float] = {}
    for k, vs in buckets.items():
        if vs:
            rates[k] = sum(vs) / len(vs)
    return rates


def _get_bucket(conf: Optional[float]) -> str:
    if conf is None or conf < 0.50:
        return "low"
    if conf < 0.65:
        return "mid"
    return "high"


def _build_recommendations(categorized: List[Dict[str, Any]]) -> List[str]:
    """Generate actionable recommendations from error patterns."""
    recs: List[str] = []

    cats = {}
    for c in categorized:
        cat = c["category"]
        cats.setdefault(cat, []).append(c)

    n_total = len(categorized)
    if not n_total:
        return recs

    # bad_line analysis
    bad_lines = cats.get("bad_line", [])
    if bad_lines:
        pct = len(bad_lines) / n_total * 100
        recs.append(
            f"{len(bad_lines)} losses ({pct:.0f}%) attributed to bad_line (negative CLV). "
            "Investigate: lock timing relative to late news, line movement velocity "
            "between lock and close, cross-book disagreement at lock time."
        )
        # Check tier concentration
        tier_counts: Dict[str, int] = {}
        for b in bad_lines:
            tier_counts[b.get("tier", "unknown")] = tier_counts.get(b.get("tier", "unknown"), 0) + 1
        worst_tier = max(tier_counts, key=tier_counts.get) if tier_counts else None  # type: ignore
        if worst_tier and tier_counts[worst_tier] >= 3:
            recs.append(
                f"Tier '{worst_tier}' has the most bad_line losses ({tier_counts[worst_tier]}). "
                "Consider tighter edge thresholds or different lock timing for this tier."
            )

    # model_miss analysis
    model_misses = cats.get("model_miss", [])
    if model_misses:
        pct = len(model_misses) / n_total * 100
        recs.append(
            f"{len(model_misses)} losses ({pct:.0f}%) are model_miss (positive CLV but wrong). "
            "Investigate rest/travel patterns, injury timing gaps (player ruled out after lock), "
            "and whether Elo seeds need updating for teams with roster changes."
        )

    # calibration_gap analysis
    cal_gaps = cats.get("calibration_gap", [])
    if cal_gaps:
        pct = len(cal_gaps) / n_total * 100
        recs.append(
            f"{len(cal_gaps)} losses ({pct:.0f}%) show calibration_gap (confidence >> actual win rate). "
            "The confidence curve may need re-fitting with more recent data."
        )

    # variance is expected — only flag if disproportionate
    variance = cats.get("variance", [])
    if variance and len(variance) / n_total > 0.6:
        recs.append(
            f"{len(variance)} losses ({len(variance)/n_total*100:.0f}%) attributed to variance. "
            "This is healthy if CLV remains positive overall."
        )

    # Market-level patterns
    market_counts: Dict[str, int] = {}
    for c in categorized:
        m = c.get("market", "unknown")
        market_counts[m] = market_counts.get(m, 0) + 1
    for m, cnt in market_counts.items():
        if cnt >= 5:
            cat_dist = {}
            for c in categorized:
                if c.get("market") == m:
                    cat_dist[c["category"]] = cat_dist.get(c["category"], 0) + 1
            if cat_dist.get("bad_line", 0) / cnt > 0.5:
                recs.append(
                    f"Market '{m}' has >50% bad_line losses — "
                    "likely systematically locking stale lines."
                )

    return recs


def run(
    days: int = 180,
    clv_data: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run error attribution over recent losses.

    Args:
        days: lookback window
        clv_data: CLV report from clv_auditor (optional, enriches categorization)
    """
    since = since_date(days)
    print(f"[error_attribution] Fetching pick results since {since}...")
    results = fetch_pick_results(since)
    print(f"[error_attribution] Total results: {len(results)}")

    # Filter to losses only
    losses = [r for r in results if r.get("result") == "loss"]
    print(f"[error_attribution] Losses: {len(losses)}")

    if not losses:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lookback_days": days,
            "n_losses": 0,
            "categorized": [],
            "summary": {},
            "recommendations": ["No losses to analyze."],
        }

    # Build CLV lookup from agent 3 data
    clv_by_event: Dict[str, float] = {}
    if clv_data:
        for p in clv_data.get("picks", []):
            eid = str(p.get("event_id", ""))
            mkt = p.get("market", "")
            clv_val = p.get("clv")
            if eid and clv_val is not None:
                clv_by_event[f"{eid}_{mkt}"] = clv_val

    # Compute bucket win rates for calibration gap detection
    bucket_rates = _bucket_win_rates(results)

    # Categorize each loss
    categorized: List[Dict[str, Any]] = []
    for loss in losses:
        eid = str(loss.get("event_id", ""))
        mkt = loss.get("market", "")
        clv = clv_by_event.get(f"{eid}_{mkt}")

        conf = safe_float(loss.get("confidence"))
        bucket = _get_bucket(conf)
        actual_rate = bucket_rates.get(bucket, 0.5)
        bucket_gap = (conf or 0.5) - actual_rate

        category = _categorize_loss(loss, clv, bucket_gap)

        categorized.append({
            "event_id": eid,
            "market": mkt,
            "tier": loss.get("tier"),
            "confidence": conf,
            "side": loss.get("side"),
            "home_team": loss.get("home_team"),
            "away_team": loss.get("away_team"),
            "run_date": loss.get("run_date"),
            "clv": clv,
            "category": category,
            "bucket_gap": round(bucket_gap, 4),
        })

    # Summary counts
    summary: Dict[str, int] = {}
    for c in categorized:
        cat = c["category"]
        summary[cat] = summary.get(cat, 0) + 1

    recommendations = _build_recommendations(categorized)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "n_losses": len(losses),
        "summary": summary,
        "recommendations": recommendations,
        "categorized": categorized,
    }

    return report

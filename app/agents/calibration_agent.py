"""Agent 4: Calibration Agent — isotonic confidence recalibration.

Computes Brier score, log-loss, reliability diagram bins.
If sample >= 50, fits a candidate confidence curve (does NOT auto-deploy).
Reuses PAVA isotonic patterns from app/calibration/confidence_calibrate.py.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ._supabase import fetch_pick_results, since_date
from ._math import safe_float


# ---------------------------------------------------------------------------
# PAVA Isotonic Regression (from confidence_calibrate.py)
# ---------------------------------------------------------------------------

@dataclass
class IsoBlock:
    y: float    # fitted probability
    w: float    # weight (count)
    x_min: float
    x_max: float


def _clamp_prob(p: float) -> float:
    return max(1e-6, min(1 - 1e-6, float(p)))


def isotonic_fit(
    x: List[float], y: List[int], w: Optional[List[float]] = None
) -> List[IsoBlock]:
    """Fit monotone non-decreasing function via PAVA on samples."""
    if w is None:
        w = [1.0] * len(x)

    order = sorted(range(len(x)), key=lambda i: x[i])
    xs = [float(x[i]) for i in order]
    ys = [float(y[i]) for i in order]
    ws = [float(w[i]) for i in order]

    blocks: List[IsoBlock] = []
    for xi, yi, wi in zip(xs, ys, ws):
        yi = _clamp_prob(yi)
        blocks.append(IsoBlock(y=yi, w=wi, x_min=xi, x_max=xi))

        while len(blocks) >= 2 and blocks[-2].y > blocks[-1].y:
            b2 = blocks.pop()
            b1 = blocks.pop()
            tw = b1.w + b2.w
            avg = (b1.y * b1.w + b2.y * b2.w) / tw if tw > 0 else (b1.y + b2.y) / 2.0
            blocks.append(IsoBlock(
                y=_clamp_prob(avg),
                w=tw,
                x_min=b1.x_min,
                x_max=b2.x_max,
            ))

    return blocks


def _blocks_to_knots(blocks: List[IsoBlock]) -> List[Dict[str, Any]]:
    knots = []
    for b in blocks:
        knots.append({
            "x_max": float(b.x_max),
            "p": float(_clamp_prob(b.y)),
            "n": int(round(b.w)),
        })
    knots.sort(key=lambda k: k["x_max"])
    return knots


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _logloss(y_true: int, y_pred: float) -> float:
    p = _clamp_prob(y_pred)
    if y_true == 1:
        return -math.log(p)
    return -math.log(1 - p)


def _brier(y_true: int, y_pred: float) -> float:
    return (y_true - y_pred) ** 2


def _reliability_bins(
    confs: List[float], outcomes: List[int], n_bins: int = 10
) -> List[Dict[str, Any]]:
    """Reliability diagram: group by predicted confidence, compare to actual rate."""
    if not confs:
        return []

    paired = sorted(zip(confs, outcomes), key=lambda t: t[0])
    chunk = max(1, len(paired) // n_bins)
    bins = []
    for i in range(0, len(paired), chunk):
        sl = paired[i:i + chunk]
        cs = [c for c, _ in sl]
        os_ = [o for _, o in sl]
        bins.append({
            "bin_lo": round(min(cs), 4),
            "bin_hi": round(max(cs), 4),
            "n": len(sl),
            "predicted_avg": round(sum(cs) / len(cs), 4),
            "actual_win_rate": round(sum(os_) / len(os_), 4),
        })
    return bins


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(days: int = 180, dry_run: bool = False) -> Dict[str, Any]:
    """Run calibration analysis on recent pick results."""
    since = since_date(days)
    print(f"[calibration] Fetching pick results since {since}...")
    results = fetch_pick_results(since)
    print(f"[calibration] Total results: {len(results)}")

    # Filter to graded picks with confidence
    usable = []
    for r in results:
        if r.get("result") not in ("win", "loss"):
            continue
        conf = safe_float(r.get("confidence"))
        if conf is None:
            continue
        outcome = 1 if r["result"] == "win" else 0
        usable.append((conf, outcome))

    print(f"[calibration] Usable picks with confidence: {len(usable)}")

    if not usable:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lookback_days": days,
            "n_usable": 0,
            "metrics": {},
            "reliability_bins": [],
            "candidate_curve": None,
        }

    confs = [c for c, _ in usable]
    outcomes = [o for _, o in usable]

    # Compute metrics against current confidence values
    total_ll = sum(_logloss(o, c) for c, o in usable)
    total_brier = sum(_brier(o, c) for c, o in usable)
    n = len(usable)

    metrics = {
        "n": n,
        "logloss": round(total_ll / n, 5),
        "brier": round(total_brier / n, 5),
        "avg_confidence": round(sum(confs) / n, 4),
        "avg_win_rate": round(sum(outcomes) / n, 4),
    }

    # Reliability diagram
    bins = _reliability_bins(confs, outcomes, n_bins=min(10, max(3, n // 10)))

    # Fit candidate curve if enough data
    candidate_curve = None
    if n >= 50:
        print(f"[calibration] Fitting candidate isotonic curve (n={n})...")
        blocks = isotonic_fit(confs, outcomes)
        knots = _blocks_to_knots(blocks)
        candidate_curve = {
            "method": "isotonic_pava",
            "n_samples": n,
            "n_knots": len(knots),
            "knots": knots,
            "fitted_at": datetime.now(timezone.utc).isoformat(),
        }

        # Evaluate fitted curve
        import bisect
        xs = [k["x_max"] for k in knots]
        def _lookup(edge: float) -> float:
            i = bisect.bisect_left(xs, edge)
            return float(knots[i]["p"]) if i < len(knots) else float(knots[-1]["p"])

        fitted_ll = sum(_logloss(o, _lookup(c)) for c, o in usable) / n
        fitted_brier = sum(_brier(o, _lookup(c)) for c, o in usable) / n
        candidate_curve["train_logloss"] = round(fitted_ll, 5)
        candidate_curve["train_brier"] = round(fitted_brier, 5)
        candidate_curve["improvement_logloss"] = round(metrics["logloss"] - fitted_ll, 5)
        candidate_curve["improvement_brier"] = round(metrics["brier"] - fitted_brier, 5)

        if not dry_run:
            # Write candidate (does NOT overwrite production curve)
            out_path = "artifacts/confidence_curve_candidate.json"
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(candidate_curve, f, indent=2)
            print(f"[calibration] Wrote candidate curve to {out_path}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "n_usable": n,
        "metrics": metrics,
        "reliability_bins": bins,
        "candidate_curve": candidate_curve,
    }

    return report

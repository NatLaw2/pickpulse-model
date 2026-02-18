"""Experiment: CLV timing filter sweep.

Tests simple CLV-based filtering rules on historical locked picks:
  - keep bets where steam_15m >= 0 (avoid reverse steam)
  - keep bets where range_30m <= threshold
  - keep bets where snap gaps are small
  - keep bets where clv_prob > 0 (positive CLV picks only)

Outputs summary tables to reports/experiments/{ts}/clv_filter_sweep.md

Data source: Supabase locked_picks + closing_lines (--days N)

CLI:
  python -m app.experiments.clv_filter_sweep --days 365
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from app.agents._supabase import (
    fetch_locked_picks,
    fetch_closing_lines,
    fetch_pick_results,
    since_date,
)
from app.agents._math import implied_prob, normalize_no_vig, american_profit, safe_float
from app.clv_timing.features import compute_batch
from app.clv_timing.report import summarize_features


# ---------------------------------------------------------------------------
# Filter definitions
# ---------------------------------------------------------------------------

FILTERS = {
    "baseline": lambda f, p: True,
    "steam_15m >= 0": lambda f, p: f.get("steam_15m") is not None and f["steam_15m"] >= 0,
    "steam_15m >= 0.005": lambda f, p: f.get("steam_15m") is not None and f["steam_15m"] >= 0.005,
    "range_30m <= 0.03": lambda f, p: f.get("range_30m") is not None and f["range_30m"] <= 0.03,
    "range_30m <= 0.02": lambda f, p: f.get("range_30m") is not None and f["range_30m"] <= 0.02,
    "snap_gap_close <= 300s": lambda f, p: f.get("snap_gap_close_sec") is not None and f["snap_gap_close_sec"] <= 300,
    "snap_gap_close <= 120s": lambda f, p: f.get("snap_gap_close_sec") is not None and f["snap_gap_close_sec"] <= 120,
    "clv_prob > 0": lambda f, p: f.get("clv_prob") is not None and f["clv_prob"] > 0,
    "clv_prob > 0.01": lambda f, p: f.get("clv_prob") is not None and f["clv_prob"] > 0.01,
}


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _compute_filter_metrics(
    features: List[Dict[str, Any]],
    picks: List[Dict[str, Any]],
    results_by_eid: Dict[str, Dict[str, Any]],
    filter_fn,
) -> Dict[str, Any]:
    """Compute metrics for picks passing a filter."""
    passing = []
    for feat, pick in zip(features, picks):
        if filter_fn(feat, pick):
            passing.append((feat, pick))

    n = len(passing)
    if n == 0:
        return {"n": 0}

    # CLV stats
    clvs = [f["clv_prob"] for f, _ in passing
            if f.get("clv_prob") is not None and math.isfinite(f["clv_prob"])]
    mean_clv = sum(clvs) / len(clvs) if clvs else None
    pct_positive = sum(1 for c in clvs if c > 0) / len(clvs) * 100 if clvs else None

    # ROI from pick_results
    total_units = 0.0
    graded = 0
    wins = 0
    for feat, pick in passing:
        eid = str(pick.get("event_id", ""))
        res = results_by_eid.get(eid)
        if res and res.get("units") is not None:
            u = safe_float(res["units"])
            if u is not None:
                total_units += u
                graded += 1
                if res.get("result") == "win":
                    wins += 1

    roi_pct = (total_units / graded * 100) if graded > 0 else None
    win_rate = (wins / graded * 100) if graded > 0 else None

    return {
        "n": n,
        "n_with_clv": len(clvs),
        "mean_clv": round(mean_clv, 5) if mean_clv is not None else None,
        "pct_positive_clv": round(pct_positive, 1) if pct_positive is not None else None,
        "n_graded": graded,
        "wins": wins,
        "win_rate": round(win_rate, 1) if win_rate is not None else None,
        "units": round(total_units, 2) if graded > 0 else None,
        "roi_pct": round(roi_pct, 1) if roi_pct is not None else None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(days: int = 365) -> Dict[str, Any]:
    """Run CLV filter sweep."""
    since = since_date(days)

    print(f"[clv_filter] Fetching locked picks since {since}...")
    picks = fetch_locked_picks(since)
    print(f"[clv_filter] Locked picks: {len(picks)}")

    print("[clv_filter] Fetching closing lines...")
    closing = fetch_closing_lines()
    print(f"[clv_filter] Events with closing lines: {len(closing)}")

    print("[clv_filter] Fetching pick results...")
    results = fetch_pick_results(since)
    results_by_eid: Dict[str, Dict[str, Any]] = {}
    for r in results:
        eid = str(r.get("event_id", ""))
        if eid:
            results_by_eid[eid] = r
    print(f"[clv_filter] Pick results: {len(results)}")

    print("[clv_filter] Computing timing features...")
    features, coverage = compute_batch(picks, closing)
    print(f"[clv_filter] Coverage: {coverage}")

    # Run each filter
    filter_results = {}
    for name, fn in FILTERS.items():
        metrics = _compute_filter_metrics(features, picks, results_by_eid, fn)
        filter_results[name] = metrics
        print(f"  {name:30s}: n={metrics['n']:4d}, "
              f"CLV={metrics.get('mean_clv', 'n/a')}, "
              f"pct+={metrics.get('pct_positive_clv', 'n/a')}%, "
              f"ROI={metrics.get('roi_pct', 'n/a')}%")

    # Feature distribution summary
    feat_summary = summarize_features(features, coverage)

    report = {
        "experiment": "clv_filter_sweep",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "n_picks": len(picks),
        "coverage": coverage,
        "filters": filter_results,
    }

    # Write report
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = f"reports/experiments/{ts}"
    os.makedirs(report_dir, exist_ok=True)

    json_path = os.path.join(report_dir, "clv_filter_sweep.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[clv_filter] JSON -> {json_path}")

    md = _render_markdown(report, feat_summary)
    md_path = os.path.join(report_dir, "clv_filter_sweep.md")
    with open(md_path, "w") as f:
        f.write(md)
    print(f"[clv_filter] Report -> {md_path}")

    return report


def _render_markdown(report: Dict[str, Any], feat_summary: str) -> str:
    """Render filter sweep as markdown."""
    lines = []
    lines.append("# CLV Filter Sweep")
    lines.append("")
    lines.append(f"**Timestamp:** {report['timestamp']}")
    lines.append(f"**Lookback:** {report['days']} days, {report['n_picks']} picks")
    lines.append("")

    # Coverage
    cov = report.get("coverage", {})
    total = cov.get("total", 0)
    lines.append("## Snapshot Coverage")
    lines.append("")
    for key in ["has_lock_snap", "has_close_snap", "has_both", "has_clv", "has_steam"]:
        count = cov.get(key, 0)
        pct = count / total * 100 if total > 0 else 0
        label = key.replace("has_", "").replace("_", " ").title()
        lines.append(f"- **{label}:** {count}/{total} ({pct:.0f}%)")
    lines.append("")

    # Filter results table
    lines.append("## Filter Results")
    lines.append("")
    lines.append("| Filter | N | Mean CLV | % CLV+ | N Graded | Win Rate | ROI |")
    lines.append("|--------|---|----------|--------|----------|----------|-----|")
    for name, m in report.get("filters", {}).items():
        if m["n"] == 0:
            lines.append(f"| {name} | 0 | — | — | — | — | — |")
            continue
        clv = f"{m['mean_clv']:.4f}" if m.get("mean_clv") is not None else "—"
        pct = f"{m['pct_positive_clv']:.0f}%" if m.get("pct_positive_clv") is not None else "—"
        wr = f"{m['win_rate']:.0f}%" if m.get("win_rate") is not None else "—"
        roi = f"{m['roi_pct']:+.1f}%" if m.get("roi_pct") is not None else "—"
        lines.append(f"| {name} | {m['n']} | {clv} | {pct} | {m.get('n_graded', 0)} | {wr} | {roi} |")

    lines.append("")

    # Feature distributions
    if feat_summary:
        lines.append(feat_summary)

    lines.append("")
    lines.append("*Shadow mode only. Do not deploy filters without further validation.*")
    lines.append("")
    return "\n".join(lines)


def cli():
    parser = argparse.ArgumentParser(description="CLV filter sweep experiment")
    parser.add_argument("--days", type=int, default=365,
                        help="Lookback days (default: 365)")
    args = parser.parse_args()

    report = run(days=args.days)
    if report.get("n_picks", 0) == 0:
        print("\nNo picks found.")
        sys.exit(1)


if __name__ == "__main__":
    cli()

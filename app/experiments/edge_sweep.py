"""Experiment 1: MIN_EDGE threshold sweep.

Sweeps MIN_EDGE thresholds across historical data to find the value that
best balances bet volume, calibration, ROI, and CLV.

Uses the production ML predict path (joblib artifacts) on historical games,
then filters bets at each threshold and computes metrics.

Data source:
  --csv data/nba_calibration_ml.csv   (preferred: 3 seasons)
  Falls back to Supabase locked_picks if CSV missing.

CLI:
  python -m app.experiments.edge_sweep --csv data/nba_calibration_ml.csv
  python -m app.experiments.edge_sweep --csv data/nba_calibration_ml.csv --compare-baseline
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Reuse existing math helpers
from app.agents._math import implied_prob, normalize_no_vig, american_profit


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05]
BASELINE_FILENAME = "edge_sweep_baseline.json"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_csv(csv_path: str) -> pd.DataFrame:
    """Load historical CSV, keep only matched rows with valid odds."""
    df = pd.read_csv(csv_path)
    df = df[df["match_status"] == "matched"].copy()
    df = df.dropna(subset=["p_home_nv", "p_away_nv", "home_win", "home_odds", "away_odds"])
    df["p_home_nv"] = df["p_home_nv"].astype(float)
    df["p_away_nv"] = df["p_away_nv"].astype(float)
    df["home_win"] = df["home_win"].astype(int)
    df["home_odds"] = df["home_odds"].astype(float)
    df["away_odds"] = df["away_odds"].astype(float)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _load_supabase(days: int = 365) -> pd.DataFrame:
    """Fallback: load from Supabase locked_picks."""
    from app.ml.dataset import build_dataset
    df = build_dataset(days=days)
    rename = {"locked_home_nv": "p_home_nv", "locked_away_nv": "p_away_nv", "won": "home_win"}
    for old, new in rename.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
    return df


# ---------------------------------------------------------------------------
# ML prediction (batch)
# ---------------------------------------------------------------------------

def _predict_batch(df: pd.DataFrame) -> pd.DataFrame:
    """Run production ML predict on each game (home perspective).

    Adds columns: p_model_home, p_model_away, edge_home, edge_away,
                  best_side, best_edge, best_prob, best_won, best_odds.
    """
    from app.ml.predict import is_available, predict_win_prob

    if not is_available():
        raise RuntimeError("ML model artifacts not found. Run: python -m app.ml.train --csv data/nba_calibration_ml.csv")

    p_model_home = []
    p_model_away = []

    for _, row in df.iterrows():
        ph = predict_win_prob(
            locked_home_nv=row["p_home_nv"],
            locked_away_nv=row["p_away_nv"],
            is_home=1,
        )
        pa = predict_win_prob(
            locked_home_nv=row["p_home_nv"],
            locked_away_nv=row["p_away_nv"],
            is_home=0,
        )
        p_model_home.append(ph if ph is not None else 0.5)
        p_model_away.append(pa if pa is not None else 0.5)

    work = df.copy()
    work["p_model_home"] = p_model_home
    work["p_model_away"] = p_model_away
    work["edge_home"] = work["p_model_home"] - work["p_home_nv"]
    work["edge_away"] = work["p_model_away"] - work["p_away_nv"]

    # Best side: pick the one with higher edge
    work["best_side"] = np.where(work["edge_home"] >= work["edge_away"], "home", "away")
    work["best_edge"] = np.where(
        work["best_side"] == "home", work["edge_home"], work["edge_away"]
    )
    work["best_prob"] = np.where(
        work["best_side"] == "home", work["p_model_home"], work["p_model_away"]
    )
    work["best_won"] = np.where(
        work["best_side"] == "home", work["home_win"], 1 - work["home_win"]
    )
    work["best_odds"] = np.where(
        work["best_side"] == "home", work["home_odds"], work["away_odds"]
    )
    work["best_market_nv"] = np.where(
        work["best_side"] == "home", work["p_home_nv"], work["p_away_nv"]
    )

    return work


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _compute_metrics(bets: pd.DataFrame) -> Dict[str, Any]:
    """Compute full metrics for a filtered set of bets."""
    n = len(bets)
    if n == 0:
        return {"n_bets": 0}

    y = bets["best_won"].values.astype(float)
    probs = bets["best_prob"].values.astype(float)
    odds = bets["best_odds"].values.astype(float)
    edges = bets["best_edge"].values.astype(float)
    market_nv = bets["best_market_nv"].values.astype(float)

    # Win rate
    wins = int(y.sum())
    win_rate = wins / n

    # ROI (units): +profit on win, -1 on loss
    units = 0.0
    for i in range(n):
        if y[i] >= 0.5:
            units += american_profit(odds[i])
        else:
            units -= 1.0
    roi_pct = (units / n) * 100 if n > 0 else 0.0

    # Brier score
    brier = float(np.mean((y - probs) ** 2))

    # Log loss
    eps = 1e-15
    clipped = np.clip(probs, eps, 1 - eps)
    logloss = float(-np.mean(y * np.log(clipped) + (1 - y) * np.log(1 - clipped)))

    # Average edge and probability
    avg_edge = float(np.mean(edges))
    avg_prob = float(np.mean(probs))
    avg_market_nv = float(np.mean(market_nv))

    # Calibration bins (10 quantile bins)
    n_bins = min(10, max(2, n // 20))
    cal_bins = []
    sorted_idx = np.argsort(probs)
    chunk = max(1, n // n_bins)
    for i in range(0, n, chunk):
        sl = sorted_idx[i:i + chunk]
        if len(sl) == 0:
            continue
        p_sl = probs[sl]
        y_sl = y[sl]
        cal_bins.append({
            "bin_lo": round(float(p_sl.min()), 4),
            "bin_hi": round(float(p_sl.max()), 4),
            "n": len(sl),
            "predicted_avg": round(float(p_sl.mean()), 4),
            "actual_win_rate": round(float(y_sl.mean()), 4),
            "cal_error": round(abs(float(p_sl.mean()) - float(y_sl.mean())), 4),
        })

    return {
        "n_bets": n,
        "wins": wins,
        "win_rate": round(win_rate, 4),
        "units": round(units, 2),
        "roi_pct": round(roi_pct, 2),
        "avg_edge": round(avg_edge, 4),
        "avg_prob": round(avg_prob, 4),
        "avg_market_nv": round(avg_market_nv, 4),
        "brier": round(brier, 5),
        "logloss": round(logloss, 5),
        "calibration_bins": cal_bins,
    }


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def run_sweep(
    df: pd.DataFrame,
    thresholds: List[float] = DEFAULT_THRESHOLDS,
) -> Dict[str, Any]:
    """Run the full edge sweep experiment."""
    print(f"[edge_sweep] Running ML predictions on {len(df)} games...")
    work = _predict_batch(df)

    print(f"[edge_sweep] Edge stats: mean={work['best_edge'].mean():.4f}, "
          f"std={work['best_edge'].std():.4f}, "
          f"max={work['best_edge'].max():.4f}")

    results = []
    for t in thresholds:
        bets = work[work["best_edge"] >= t]
        metrics = _compute_metrics(bets)
        metrics["threshold"] = t
        results.append(metrics)
        print(f"  MIN_EDGE={t:.3f}: n={metrics['n_bets']:5d}, "
              f"WR={metrics.get('win_rate',0):.3f}, "
              f"ROI={metrics.get('roi_pct',0):+.1f}%, "
              f"LL={metrics.get('logloss','n/a')}, "
              f"Brier={metrics.get('brier','n/a')}")

    # Also compute "all games" baseline (threshold=0)
    all_metrics = _compute_metrics(work)
    all_metrics["threshold"] = 0.0

    # Date range
    date_range = {"start": str(df["date"].iloc[0]), "end": str(df["date"].iloc[-1])}

    return {
        "experiment": "edge_sweep",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_rows": len(df),
        "date_range": date_range,
        "thresholds": thresholds,
        "all_games_baseline": all_metrics,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Recommendation logic
# ---------------------------------------------------------------------------

def _recommend(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pick the best threshold balancing volume, calibration, and ROI."""
    # Filter to thresholds with >= 50 bets
    viable = [r for r in results if r["n_bets"] >= 50]
    if not viable:
        viable = [r for r in results if r["n_bets"] >= 10]
    if not viable:
        return {"recommended_threshold": 0.03, "reason": "No viable thresholds with enough bets"}

    # Score each threshold: weighted combination
    # - Lower brier is better (calibration)
    # - Higher ROI is better
    # - More bets is better (log scale to avoid dominating)
    # - Lower logloss is better
    scored = []
    for r in viable:
        # Normalize: ROI in [-X, X], brier in [0.15, 0.25], logloss in [0.5, 0.7]
        score = (
            r["roi_pct"] * 0.35              # ROI weight
            - r["brier"] * 100 * 0.25        # Brier penalty
            - r["logloss"] * 10 * 0.20       # Logloss penalty
            + np.log1p(r["n_bets"]) * 0.20   # Volume bonus (log)
        )
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]

    return {
        "recommended_threshold": best["threshold"],
        "n_bets": best["n_bets"],
        "win_rate": best["win_rate"],
        "roi_pct": best["roi_pct"],
        "brier": best["brier"],
        "logloss": best["logloss"],
        "reason": (
            f"Best composite score: {best['n_bets']} bets, "
            f"{best['win_rate']:.1%} WR, {best['roi_pct']:+.1f}% ROI, "
            f"Brier={best['brier']:.5f}"
        ),
    }


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------

def _load_baseline(report_dir: str) -> Optional[Dict[str, Any]]:
    """Load the stored baseline from reports/experiments/."""
    path = os.path.join(os.path.dirname(report_dir), BASELINE_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save_baseline(report_dir: str, report: Dict[str, Any]) -> str:
    """Save current results as the new baseline."""
    path = os.path.join(os.path.dirname(report_dir), BASELINE_FILENAME)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return path


def _compare_to_baseline(
    current: Dict[str, Any],
    baseline: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Compare current sweep results against stored baseline."""
    baseline_by_t = {r["threshold"]: r for r in baseline.get("results", [])}
    current_by_t = {r["threshold"]: r for r in current.get("results", [])}

    diffs = []
    for t in sorted(set(list(baseline_by_t.keys()) + list(current_by_t.keys()))):
        b = baseline_by_t.get(t, {})
        c = current_by_t.get(t, {})
        if not b or not c:
            continue
        diff = {
            "threshold": t,
            "n_bets_baseline": b.get("n_bets", 0),
            "n_bets_current": c.get("n_bets", 0),
            "roi_baseline": b.get("roi_pct", 0),
            "roi_current": c.get("roi_pct", 0),
            "roi_delta": round(c.get("roi_pct", 0) - b.get("roi_pct", 0), 2),
            "brier_baseline": b.get("brier", 0),
            "brier_current": c.get("brier", 0),
            "brier_delta": round(c.get("brier", 0) - b.get("brier", 0), 5),
            "logloss_baseline": b.get("logloss", 0),
            "logloss_current": c.get("logloss", 0),
            "logloss_delta": round(c.get("logloss", 0) - b.get("logloss", 0), 5),
            "wr_baseline": b.get("win_rate", 0),
            "wr_current": c.get("win_rate", 0),
            "wr_delta": round(c.get("win_rate", 0) - b.get("win_rate", 0), 4),
        }
        diffs.append(diff)
    return diffs


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _render_markdown(
    report: Dict[str, Any],
    recommendation: Dict[str, Any],
    baseline_comparison: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Render the sweep results as a markdown report."""
    lines = []
    lines.append("# Experiment 1: MIN_EDGE Threshold Sweep")
    lines.append("")
    lines.append(f"**Timestamp:** {report['timestamp']}")
    lines.append(f"**Data:** {report['data_rows']} games "
                 f"({report['date_range']['start']} to {report['date_range']['end']})")
    lines.append("")

    # Summary table
    lines.append("## Results")
    lines.append("")
    lines.append("| MIN_EDGE | N Bets | Win Rate | ROI (%) | Avg Edge | Avg Prob | Brier | LogLoss |")
    lines.append("|----------|--------|----------|---------|----------|----------|-------|---------|")
    for r in report["results"]:
        if r["n_bets"] == 0:
            lines.append(f"| {r['threshold']:.3f} | 0 | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {r['threshold']:.3f} "
            f"| {r['n_bets']} "
            f"| {r['win_rate']:.1%} "
            f"| {r['roi_pct']:+.1f} "
            f"| {r['avg_edge']:.4f} "
            f"| {r['avg_prob']:.4f} "
            f"| {r['brier']:.5f} "
            f"| {r['logloss']:.5f} |"
        )

    # All-games baseline
    ab = report["all_games_baseline"]
    if ab["n_bets"] > 0:
        lines.append("")
        lines.append(f"**All games (no filter):** {ab['n_bets']} bets, "
                     f"WR={ab['win_rate']:.1%}, ROI={ab['roi_pct']:+.1f}%, "
                     f"Brier={ab['brier']:.5f}, LL={ab['logloss']:.5f}")

    # Calibration detail for recommended threshold
    rec_t = recommendation["recommended_threshold"]
    rec_result = next((r for r in report["results"] if r["threshold"] == rec_t), None)
    if rec_result and rec_result.get("calibration_bins"):
        lines.append("")
        lines.append(f"## Calibration Bins (MIN_EDGE = {rec_t})")
        lines.append("")
        lines.append("| Bin Range | N | Predicted | Actual | Error |")
        lines.append("|-----------|---|-----------|--------|-------|")
        for b in rec_result["calibration_bins"]:
            lines.append(
                f"| {b['bin_lo']:.3f}–{b['bin_hi']:.3f} "
                f"| {b['n']} "
                f"| {b['predicted_avg']:.3f} "
                f"| {b['actual_win_rate']:.3f} "
                f"| {b['cal_error']:.3f} |"
            )

    # Baseline comparison
    if baseline_comparison:
        lines.append("")
        lines.append("## Baseline Comparison")
        lines.append("")
        lines.append("| MIN_EDGE | N (base/cur) | ROI Delta | Brier Delta | LL Delta | WR Delta |")
        lines.append("|----------|--------------|-----------|-------------|----------|----------|")
        for d in baseline_comparison:
            roi_arrow = "+" if d["roi_delta"] > 0 else ""
            brier_arrow = "+" if d["brier_delta"] > 0 else ""
            ll_arrow = "+" if d["logloss_delta"] > 0 else ""
            wr_arrow = "+" if d["wr_delta"] > 0 else ""
            lines.append(
                f"| {d['threshold']:.3f} "
                f"| {d['n_bets_baseline']}/{d['n_bets_current']} "
                f"| {roi_arrow}{d['roi_delta']:.1f}pp "
                f"| {brier_arrow}{d['brier_delta']:.5f} "
                f"| {ll_arrow}{d['logloss_delta']:.5f} "
                f"| {wr_arrow}{d['wr_delta']:.3f} |"
            )

    # Recommendation
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    lines.append(f"**Recommended MIN_EDGE: {recommendation['recommended_threshold']}**")
    lines.append("")
    lines.append(f"> {recommendation['reason']}")
    lines.append("")
    lines.append("*Shadow mode only. Do NOT deploy without reviewing the full report.*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(
    csv_path: Optional[str] = None,
    days: int = 365,
    thresholds: Optional[List[float]] = None,
    compare_baseline: bool = False,
    save_as_baseline: bool = False,
) -> Dict[str, Any]:
    """Run the edge sweep experiment end-to-end."""
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    # Load data
    if csv_path and os.path.exists(csv_path):
        df = _load_csv(csv_path)
        print(f"[edge_sweep] Loaded {len(df)} games from {csv_path}")
    else:
        if csv_path:
            print(f"[edge_sweep] CSV not found at {csv_path}, falling back to Supabase")
        df = _load_supabase(days)
        print(f"[edge_sweep] Loaded {len(df)} games from Supabase")

    if len(df) < 50:
        print(f"[edge_sweep] Only {len(df)} rows — need >= 50. Aborting.")
        return {"error": "insufficient_data", "n_rows": len(df)}

    # Run sweep
    report = run_sweep(df, thresholds)
    recommendation = _recommend(report["results"])
    report["recommendation"] = recommendation

    # Output directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = f"reports/experiments/{ts}"
    os.makedirs(report_dir, exist_ok=True)

    # Baseline comparison
    baseline_comparison = None
    baseline_dir = os.path.dirname(report_dir)
    if compare_baseline:
        baseline = _load_baseline(report_dir)
        if baseline:
            baseline_comparison = _compare_to_baseline(report, baseline)
            report["baseline_comparison"] = baseline_comparison
            print(f"\n[edge_sweep] Compared against baseline from {baseline.get('timestamp', 'unknown')}")
        else:
            print(f"\n[edge_sweep] No baseline found at {os.path.join(baseline_dir, BASELINE_FILENAME)}")

    # Save JSON
    json_path = os.path.join(report_dir, "edge_sweep.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[edge_sweep] JSON -> {json_path}")

    # Save markdown
    md = _render_markdown(report, recommendation, baseline_comparison)
    md_path = os.path.join(report_dir, "edge_sweep.md")
    with open(md_path, "w") as f:
        f.write(md)
    print(f"[edge_sweep] Report -> {md_path}")

    # Save as baseline if requested or if no baseline exists
    baseline_path = os.path.join(baseline_dir, BASELINE_FILENAME)
    if save_as_baseline or not os.path.exists(baseline_path):
        bp = _save_baseline(report_dir, report)
        print(f"[edge_sweep] Saved as baseline -> {bp}")

    # Print recommendation
    print(f"\n{'='*60}")
    print(f"  RECOMMENDED MIN_EDGE: {recommendation['recommended_threshold']}")
    print(f"  {recommendation['reason']}")
    print(f"{'='*60}")

    return report


def cli():
    parser = argparse.ArgumentParser(description="Experiment 1: MIN_EDGE threshold sweep")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to historical CSV")
    parser.add_argument("--days", type=int, default=365,
                        help="Supabase lookback days (fallback)")
    parser.add_argument("--thresholds", type=str, default=None,
                        help="Comma-separated thresholds (e.g. '0.01,0.02,0.03')")
    parser.add_argument("--compare-baseline", action="store_true",
                        help="Compare results against stored baseline")
    parser.add_argument("--save-baseline", action="store_true",
                        help="Save results as new baseline")
    args = parser.parse_args()

    csv = args.csv
    if csv is None and os.path.exists("data/nba_calibration_ml.csv"):
        csv = "data/nba_calibration_ml.csv"

    thresholds = None
    if args.thresholds:
        thresholds = [float(t.strip()) for t in args.thresholds.split(",")]

    report = main(
        csv_path=csv,
        days=args.days,
        thresholds=thresholds,
        compare_baseline=args.compare_baseline,
        save_as_baseline=args.save_baseline,
    )

    if "error" in report:
        print(f"\nExperiment failed: {report['error']}")
        sys.exit(1)


if __name__ == "__main__":
    cli()

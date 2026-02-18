"""Auto-run loop: re-runs edge_sweep after each model change.

Watches artifacts/ml_model.joblib and artifacts/ml_calibrator.joblib for
modifications. When a change is detected, re-runs the edge sweep and
compares results against the stored baseline.

Usage:
  python -m app.experiments.auto_run --csv data/nba_calibration_ml.csv
  python -m app.experiments.auto_run --csv data/nba_calibration_ml.csv --once
  python -m app.experiments.auto_run --csv data/nba_calibration_ml.csv --watch

Modes:
  --once   : Run once, compare to baseline, exit. (default)
  --watch  : Poll artifacts every 10s, re-run on change.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from typing import Optional

from app.experiments.edge_sweep import main as run_edge_sweep


# ---------------------------------------------------------------------------
# Artifact fingerprinting
# ---------------------------------------------------------------------------

WATCHED_FILES = [
    "artifacts/ml_model.joblib",
    "artifacts/ml_calibrator.joblib",
]


def _fingerprint() -> str:
    """SHA256 hash of watched artifact files."""
    h = hashlib.sha256()
    for path in WATCHED_FILES:
        if os.path.exists(path):
            h.update(path.encode())
            h.update(str(os.path.getmtime(path)).encode())
            h.update(str(os.path.getsize(path)).encode())
        else:
            h.update(f"MISSING:{path}".encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Run + compare
# ---------------------------------------------------------------------------

def _run_and_compare(
    csv_path: Optional[str],
    days: int,
    save_baseline: bool = False,
) -> dict:
    """Run edge sweep with baseline comparison.

    Forces the ML predict module to reload artifacts by clearing its cache.
    """
    # Force reload of ML model (clear per-process cache)
    try:
        from app.ml import predict as pred_mod
        pred_mod._LOADED = False
        pred_mod._MODEL = None
        pred_mod._CALIBRATOR = None
        pred_mod._FEATURES = None
        pred_mod._FORMAT = None
    except ImportError:
        pass

    return run_edge_sweep(
        csv_path=csv_path,
        days=days,
        compare_baseline=True,
        save_as_baseline=save_baseline,
    )


# ---------------------------------------------------------------------------
# Watch loop
# ---------------------------------------------------------------------------

def watch_loop(
    csv_path: Optional[str],
    days: int,
    poll_seconds: int = 10,
):
    """Poll for artifact changes, re-run on each change."""
    last_fp = _fingerprint()
    print(f"[auto_run] Watching artifacts for changes (poll={poll_seconds}s)")
    print(f"[auto_run] Initial fingerprint: {last_fp}")
    print(f"[auto_run] Press Ctrl+C to stop.\n")

    # Initial run
    print("[auto_run] === Initial run ===")
    _run_and_compare(csv_path, days, save_baseline=False)

    run_count = 1
    try:
        while True:
            time.sleep(poll_seconds)
            fp = _fingerprint()
            if fp != last_fp:
                run_count += 1
                print(f"\n[auto_run] === Model change detected (run #{run_count}) ===")
                print(f"[auto_run] Old fingerprint: {last_fp}")
                print(f"[auto_run] New fingerprint: {fp}")
                last_fp = fp
                _run_and_compare(csv_path, days, save_baseline=False)
            else:
                sys.stdout.write(".")
                sys.stdout.flush()
    except KeyboardInterrupt:
        print(f"\n[auto_run] Stopped after {run_count} run(s).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli():
    parser = argparse.ArgumentParser(description="Auto-run edge sweep on model changes")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to historical CSV")
    parser.add_argument("--days", type=int, default=365,
                        help="Supabase lookback days (fallback)")
    parser.add_argument("--once", action="store_true", default=True,
                        help="Run once, compare to baseline, exit (default)")
    parser.add_argument("--watch", action="store_true",
                        help="Poll for artifact changes and re-run")
    parser.add_argument("--save-baseline", action="store_true",
                        help="Overwrite baseline with current results")
    parser.add_argument("--poll", type=int, default=10,
                        help="Poll interval in seconds (watch mode)")
    args = parser.parse_args()

    csv = args.csv
    if csv is None and os.path.exists("data/nba_calibration_ml.csv"):
        csv = "data/nba_calibration_ml.csv"

    if args.watch:
        watch_loop(csv, args.days, args.poll)
    else:
        report = _run_and_compare(csv, args.days, save_baseline=args.save_baseline)
        if "error" in report:
            sys.exit(1)


if __name__ == "__main__":
    cli()

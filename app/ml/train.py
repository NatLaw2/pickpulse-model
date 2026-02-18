"""Train NBA moneyline probability model.

Trains a logistic regression optimizing log-loss on historical game data.
Outputs:
  - artifacts/ml_model.joblib   (sklearn LogisticRegression)
  - artifacts/ml_calibrator.joblib (sklearn IsotonicRegression)
  - artifacts/ml_metadata.json  (features, train range, metrics)

Two data sources supported:
  --csv data/nba_calibration_ml.csv   (historical: 3 seasons from BRef + Odds API)
  --days 365                          (production: Supabase locked_picks + pick_results)

CLI:
  python -m app.ml.train --csv data/nba_calibration_ml.csv
  python -m app.ml.train --days 365
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from .calibrate import fit_calibrator, apply_calibrator, save_calibrator


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    "p_home_nv",       # no-vig implied prob for home
    "p_away_nv",       # no-vig implied prob for away
    "is_home",         # 1 if we're evaluating from home perspective
]

DERIVED_FEATURES = [
    "favorite_nv",     # no-vig prob of the side we're evaluating
    "underdog_nv",     # no-vig prob of the opponent
    "log_odds_ratio",  # log(p_home_nv / p_away_nv) — line magnitude signal
]

ALL_FEATURES = FEATURE_COLS + DERIVED_FEATURES


def _load_csv_dataset(csv_path: str) -> pd.DataFrame:
    """Load and prepare training data from historical CSV."""
    df = pd.read_csv(csv_path)

    # Only use rows with matched odds
    df = df[df["match_status"] == "matched"].copy()
    df = df.dropna(subset=["p_home_nv", "p_away_nv", "home_win"])

    # Ensure numeric
    df["p_home_nv"] = df["p_home_nv"].astype(float)
    df["p_away_nv"] = df["p_away_nv"].astype(float)
    df["home_win"] = df["home_win"].astype(int)

    # Sort by date for time-based split
    df = df.sort_values("date").reset_index(drop=True)

    print(f"[train] Loaded {len(df)} matched rows from {csv_path}")
    print(f"[train] Date range: {df['date'].iloc[0]} to {df['date'].iloc[-1]}")
    if "season" in df.columns:
        for s in sorted(df["season"].unique()):
            print(f"  Season {int(s)}: {len(df[df['season']==s])} games")

    return df


def _load_supabase_dataset(days: int) -> pd.DataFrame:
    """Load training data from Supabase (production picks)."""
    from .dataset import build_dataset
    df = build_dataset(days=days)
    # Rename columns to match CSV format
    rename = {
        "locked_home_nv": "p_home_nv",
        "locked_away_nv": "p_away_nv",
        "won": "home_win",  # Note: in Supabase dataset, 'won' is per-pick, not always home
    }
    for old, new in rename.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
    return df


def _build_features(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[str], pd.DataFrame]:
    """Build feature matrix for home-win prediction.

    Each row = one game, label = home_win (1 if home team won).
    """
    work = df.copy()

    # Core features
    work["is_home"] = 1.0  # All rows are from home perspective

    # Derived features
    work["favorite_nv"] = work[["p_home_nv", "p_away_nv"]].max(axis=1)
    work["underdog_nv"] = work[["p_home_nv", "p_away_nv"]].min(axis=1)
    eps = 1e-6
    work["log_odds_ratio"] = np.log(
        (work["p_home_nv"] + eps) / (work["p_away_nv"] + eps)
    )

    # Optional: snapshot_offset_minutes as feature if available
    features = ALL_FEATURES.copy()
    if "snapshot_offset_minutes" in work.columns:
        work["snapshot_offset_minutes"] = work["snapshot_offset_minutes"].fillna(60.0)
        features.append("snapshot_offset_minutes")

    # Drop rows with NaN in feature columns
    work = work.dropna(subset=features)

    X = work[features].values.astype(np.float64)
    y = work["home_win"].values.astype(np.int32)

    return X, y, features, work


def _train_logistic(X: np.ndarray, y: np.ndarray, C: float = 1.0):
    """Train logistic regression optimizing log-loss."""
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression(
        C=C,
        penalty="l2",
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    model.fit(X, y)
    return model


def _evaluate(probs: np.ndarray, y: np.ndarray, label: str = "") -> Dict[str, Any]:
    """Compute evaluation metrics."""
    n = len(y)
    eps = 1e-15
    probs_clipped = np.clip(probs, eps, 1 - eps)

    logloss = -np.mean(y * np.log(probs_clipped) + (1 - y) * np.log(1 - probs_clipped))
    brier = np.mean((y - probs) ** 2)
    avg_conf = float(np.mean(probs))
    avg_win = float(np.mean(y))

    # Calibration bins (decile-based)
    n_bins = min(10, max(2, n // 50))
    bins = []
    sorted_idx = np.argsort(probs)
    chunk = max(1, n // n_bins)
    for i in range(0, n, chunk):
        sl = sorted_idx[i:i + chunk]
        if len(sl) == 0:
            continue
        p_slice = probs[sl]
        y_slice = y[sl]
        bins.append({
            "bin_lo": round(float(p_slice.min()), 4),
            "bin_hi": round(float(p_slice.max()), 4),
            "n": len(sl),
            "predicted_avg": round(float(p_slice.mean()), 4),
            "actual_win_rate": round(float(y_slice.mean()), 4),
        })

    result = {
        "n": n,
        "logloss": round(float(logloss), 5),
        "brier": round(float(brier), 5),
        "avg_confidence": round(avg_conf, 4),
        "avg_win_rate": round(avg_win, 4),
        "calibration_bins": bins,
    }

    if label:
        prefix = f"[train] {label}"
        print(f"{prefix}: n={n}, LL={result['logloss']}, Brier={result['brier']}, "
              f"avg_pred={avg_conf:.4f}, avg_actual={avg_win:.4f}")

    return result


# ---------------------------------------------------------------------------
# Main training function
# ---------------------------------------------------------------------------

def train(
    csv_path: Optional[str] = None,
    days: int = 365,
    C: float = 1.0,
    val_frac: float = 0.2,
) -> Dict[str, Any]:
    """Train the probability model end-to-end.

    Args:
        csv_path: Path to historical CSV (preferred, 3+ seasons).
        days: Lookback days for Supabase dataset (fallback).
        C: L2 regularization strength.
        val_frac: Fraction of data for time-based validation split.

    Returns:
        Report dict with metrics and artifact paths.
    """
    print(f"\n{'='*60}")
    print(f"  NBA ML Model Training")
    print(f"  C={C} | val_frac={val_frac}")
    print(f"{'='*60}\n")

    # Load data
    if csv_path and os.path.exists(csv_path):
        df = _load_csv_dataset(csv_path)
    else:
        if csv_path:
            print(f"[train] CSV not found at {csv_path}, falling back to Supabase")
        df = _load_supabase_dataset(days)

    if len(df) < 50:
        print(f"[train] Only {len(df)} rows — need >= 50. Aborting.")
        return {"error": "insufficient_data", "n_rows": len(df)}

    # Build features
    X, y, feature_names, work = _build_features(df)
    n = len(y)
    print(f"[train] Feature matrix: {n} rows x {len(feature_names)} features")
    print(f"[train] Features: {feature_names}")
    print(f"[train] Home win rate: {y.mean():.3f}")

    # Time-based split: oldest (1-val_frac) for train, newest val_frac for val
    split_idx = int(n * (1 - val_frac))
    if split_idx < 30 or (n - split_idx) < 10:
        print(f"[train] Not enough for split. Training on all {n} rows.")
        split_idx = n

    X_train, y_train = X[:split_idx], y[:split_idx]
    X_val, y_val = X[split_idx:], y[split_idx:]

    # Record date ranges
    train_dates = work.iloc[:split_idx]
    val_dates = work.iloc[split_idx:]
    train_range = {
        "start": str(train_dates["date"].iloc[0]) if len(train_dates) > 0 else None,
        "end": str(train_dates["date"].iloc[-1]) if len(train_dates) > 0 else None,
    }
    val_range = {
        "start": str(val_dates["date"].iloc[0]) if len(val_dates) > 0 else None,
        "end": str(val_dates["date"].iloc[-1]) if len(val_dates) > 0 else None,
    }

    print(f"[train] Train: {len(y_train)} rows ({train_range['start']} to {train_range['end']})")
    print(f"[train] Val:   {len(y_val)} rows ({val_range['start']} to {val_range['end']})")

    # Train logistic regression
    model = _train_logistic(X_train, y_train, C=C)

    # Raw train metrics
    train_probs_raw = model.predict_proba(X_train)[:, 1]
    train_metrics_raw = _evaluate(train_probs_raw, y_train, "Train (raw)")

    # Fit isotonic calibrator on training predictions
    from sklearn.isotonic import IsotonicRegression
    calibrator = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip")
    calibrator.fit(train_probs_raw, y_train)
    print(f"[train] Isotonic calibrator fitted on {len(train_probs_raw)} training samples")

    # Calibrated train metrics
    train_probs_cal = calibrator.predict(train_probs_raw)
    train_metrics_cal = _evaluate(train_probs_cal, y_train, "Train (calibrated)")

    # Validation metrics
    val_metrics_raw = None
    val_metrics_cal = None
    if len(y_val) >= 10:
        val_probs_raw = model.predict_proba(X_val)[:, 1]
        val_metrics_raw = _evaluate(val_probs_raw, y_val, "Val (raw)")
        val_probs_cal = calibrator.predict(val_probs_raw)
        val_metrics_cal = _evaluate(val_probs_cal, y_val, "Val (calibrated)")

    # Feature importance
    coef = model.coef_[0]
    importance = []
    for i, name in enumerate(feature_names):
        importance.append({"feature": name, "coefficient": round(float(coef[i]), 5)})
    importance.sort(key=lambda x: abs(x["coefficient"]), reverse=True)
    print(f"\n[train] Feature importance:")
    for f in importance:
        print(f"  {f['feature']:25s} coef={f['coefficient']:+.5f}")

    # Save artifacts
    os.makedirs("artifacts", exist_ok=True)

    model_path = "artifacts/ml_model.joblib"
    joblib.dump(model, model_path)
    print(f"\n[train] Saved model -> {model_path}")

    cal_path = "artifacts/ml_calibrator.joblib"
    joblib.dump(calibrator, cal_path)
    print(f"[train] Saved calibrator -> {cal_path}")

    # Also save JSON calibrator for backward compat with existing predict.py JSON loader
    cal_json = {
        "method": "isotonic",
        "x": calibrator.X_thresholds_.tolist(),
        "y": calibrator.y_thresholds_.tolist(),
        "n_samples": len(train_probs_raw),
    }
    cal_json_path = "artifacts/ml_calibrator.json"
    with open(cal_json_path, "w") as f:
        json.dump(cal_json, f, indent=2)

    metadata = {
        "version": "ml_v2",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_source": csv_path or f"supabase:{days}d",
        "C": C,
        "features": feature_names,
        "n_features": len(feature_names),
        "n_train": len(y_train),
        "n_val": len(y_val),
        "train_range": train_range,
        "val_range": val_range,
        "train_metrics_raw": train_metrics_raw,
        "train_metrics_calibrated": train_metrics_cal,
        "val_metrics_raw": val_metrics_raw,
        "val_metrics_calibrated": val_metrics_cal,
        "feature_importance": importance,
        "model_path": model_path,
        "calibrator_path": cal_path,
    }
    meta_path = "artifacts/ml_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"[train] Saved metadata -> {meta_path}")

    print(f"\n{'='*60}")
    print(f"  TRAINING COMPLETE")
    print(f"  Train: n={len(y_train)}, LL(cal)={train_metrics_cal['logloss']}, Brier(cal)={train_metrics_cal['brier']}")
    if val_metrics_cal:
        print(f"  Val:   n={len(y_val)}, LL(cal)={val_metrics_cal['logloss']}, Brier(cal)={val_metrics_cal['brier']}")
    print(f"  Artifacts: {model_path}, {cal_path}, {meta_path}")
    print(f"{'='*60}\n")

    return metadata


def main():
    parser = argparse.ArgumentParser(description="Train NBA ML probability model")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to historical CSV (default: data/nba_calibration_ml.csv)")
    parser.add_argument("--days", type=int, default=365,
                        help="Lookback days for Supabase data (fallback)")
    parser.add_argument("--C", type=float, default=1.0,
                        help="Regularization strength (default: 1.0)")
    parser.add_argument("--val-frac", type=float, default=0.2,
                        help="Validation fraction (default: 0.2)")
    args = parser.parse_args()

    csv = args.csv
    if csv is None and os.path.exists("data/nba_calibration_ml.csv"):
        csv = "data/nba_calibration_ml.csv"

    report = train(csv_path=csv, days=args.days, C=args.C, val_frac=args.val_frac)

    if "error" in report:
        print(f"\nTraining failed: {report['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()

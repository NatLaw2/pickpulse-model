"""Train NBA moneyline probability model.

Trains a logistic regression optimizing log-loss on locked_picks + game_results.
Outputs model artifact to artifacts/ml_model.json.

CLI: python -m app.ml.train --days 365
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .dataset import build_dataset, FEATURE_COLS, OPTIONAL_FEATURES
from .calibrate import fit_calibrator, apply_calibrator, save_calibrator


def _prepare_features(df, feature_cols: List[str]) -> Tuple:
    """Prepare feature matrix. Fill missing spread with 0, drop rows with NaN in core features."""
    import pandas as pd

    work = df.copy()

    # Fill spread_home_point with 0 if missing (no spread available)
    if "spread_home_point" in work.columns:
        work["spread_home_point"] = work["spread_home_point"].fillna(0.0)

    # Add derived features
    # Selected-side no-vig prob (what the market thinks of our pick)
    work["selected_nv"] = np.where(
        work["is_home"] == 1,
        work["locked_home_nv"],
        work["locked_away_nv"],
    )
    # Opponent no-vig prob
    work["opponent_nv"] = np.where(
        work["is_home"] == 1,
        work["locked_away_nv"],
        work["locked_home_nv"],
    )

    all_features = feature_cols + ["selected_nv", "opponent_nv"]

    # Drop rows with NaN in required features
    work = work.dropna(subset=all_features)

    X = work[all_features].values.astype(np.float64)
    y = work["won"].values.astype(np.int32)
    return X, y, work, all_features


def _train_logistic(X: np.ndarray, y: np.ndarray, C: float = 1.0):
    """Train logistic regression with sklearn."""
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


def _evaluate(model, X: np.ndarray, y: np.ndarray, calibrator=None) -> Dict[str, Any]:
    """Compute evaluation metrics."""
    probs = model.predict_proba(X)[:, 1]

    if calibrator is not None:
        probs = apply_calibrator(calibrator, probs)

    n = len(y)
    eps = 1e-15
    probs_clipped = np.clip(probs, eps, 1 - eps)

    logloss = -np.mean(y * np.log(probs_clipped) + (1 - y) * np.log(1 - probs_clipped))
    brier = np.mean((y - probs) ** 2)
    avg_conf = float(np.mean(probs))
    avg_win = float(np.mean(y))

    # Calibration bins
    bins = []
    n_bins = min(5, max(2, n // 10))
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

    return {
        "n": n,
        "logloss": round(float(logloss), 5),
        "brier": round(float(brier), 5),
        "avg_confidence": round(avg_conf, 4),
        "avg_win_rate": round(avg_win, 4),
        "calibration_bins": bins,
    }


def _model_to_dict(model, feature_names: List[str]) -> Dict[str, Any]:
    """Serialize sklearn LogisticRegression to JSON-safe dict."""
    coef = model.coef_[0].tolist()
    intercept = float(model.intercept_[0])
    return {
        "type": "logistic_regression",
        "features": feature_names,
        "coefficients": coef,
        "intercept": intercept,
        "classes": model.classes_.tolist(),
    }


def train(days: int = 365, C: float = 1.0, val_frac: float = 0.2) -> Dict[str, Any]:
    """Train the probability model end-to-end.

    Returns report dict with metrics and artifact paths.
    """
    print(f"\n{'='*60}")
    print(f"  NBA ML Model Training")
    print(f"  Lookback: {days} days | C={C} | val_frac={val_frac}")
    print(f"{'='*60}\n")

    df = build_dataset(days=days)
    if len(df) < 20:
        print(f"[train] Only {len(df)} rows — not enough to train. Need >= 20.")
        return {"error": "insufficient_data", "n_rows": len(df)}

    X, y, work, feature_names = _prepare_features(df, FEATURE_COLS)
    n = len(y)
    print(f"[train] Feature matrix: {n} rows x {len(feature_names)} features")
    print(f"[train] Win rate: {y.mean():.3f}")

    # Time-based split: oldest (1-val_frac) for train, newest val_frac for val
    split_idx = int(n * (1 - val_frac))
    if split_idx < 10 or (n - split_idx) < 5:
        print(f"[train] Not enough data for train/val split. Training on all {n} rows.")
        split_idx = n

    X_train, y_train = X[:split_idx], y[:split_idx]
    X_val, y_val = X[split_idx:], y[split_idx:]

    print(f"[train] Train: {len(y_train)} rows | Val: {len(y_val)} rows")

    # Train
    model = _train_logistic(X_train, y_train, C=C)

    # Train metrics (uncalibrated)
    train_metrics = _evaluate(model, X_train, y_train)
    print(f"[train] Train LL={train_metrics['logloss']}, Brier={train_metrics['brier']}")

    # Fit calibrator on training predictions
    train_probs = model.predict_proba(X_train)[:, 1]
    calibrator = fit_calibrator(train_probs, y_train)
    print(f"[train] Calibrator fitted (isotonic, {len(train_probs)} samples)")

    # Calibrated train metrics
    train_cal = _evaluate(model, X_train, y_train, calibrator)
    print(f"[train] Train (calibrated) LL={train_cal['logloss']}, Brier={train_cal['brier']}")

    # Val metrics
    val_metrics = None
    if len(y_val) >= 5:
        val_metrics = _evaluate(model, X_val, y_val)
        val_cal = _evaluate(model, X_val, y_val, calibrator)
        print(f"[train] Val LL={val_metrics['logloss']}, Brier={val_metrics['brier']}")
        print(f"[train] Val (calibrated) LL={val_cal['logloss']}, Brier={val_cal['brier']}")
    else:
        val_cal = None

    # Feature importance
    coef = model.coef_[0]
    importance = []
    for i, name in enumerate(feature_names):
        importance.append({"feature": name, "coefficient": round(float(coef[i]), 5)})
    importance.sort(key=lambda x: abs(x["coefficient"]), reverse=True)

    # Overconfidence check
    avg_conf = train_cal.get("avg_confidence", 0.5)
    if avg_conf > 0.62:
        print(f"[train] WARNING: avg predicted confidence = {avg_conf:.3f} (> 0.62 threshold)")

    # Save artifacts
    os.makedirs("artifacts", exist_ok=True)

    model_dict = _model_to_dict(model, feature_names)
    model_artifact = {
        "version": "ml_v1",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "C": C,
        "n_train": len(y_train),
        "n_val": len(y_val),
        "model": model_dict,
        "train_metrics": train_cal,
        "val_metrics": val_cal,
        "feature_importance": importance,
    }

    model_path = "artifacts/ml_model.json"
    with open(model_path, "w") as f:
        json.dump(model_artifact, f, indent=2)
    print(f"[train] Wrote {model_path}")

    cal_path = "artifacts/ml_calibrator.json"
    save_calibrator(calibrator, cal_path)
    print(f"[train] Wrote {cal_path}")

    report = {
        "model_path": model_path,
        "calibrator_path": cal_path,
        "n_train": len(y_train),
        "n_val": len(y_val),
        "train_metrics": train_cal,
        "val_metrics": val_cal,
        "feature_importance": importance,
        "avg_confidence": avg_conf,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Train NBA ML probability model")
    parser.add_argument("--days", type=int, default=365, help="Lookback days (default: 365)")
    parser.add_argument("--C", type=float, default=1.0, help="Regularization strength (default: 1.0)")
    parser.add_argument("--val-frac", type=float, default=0.2, help="Validation fraction (default: 0.2)")
    args = parser.parse_args()

    report = train(days=args.days, C=args.C, val_frac=args.val_frac)

    if "error" in report:
        print(f"\nTraining failed: {report['error']}")
        sys.exit(1)

    print(f"\nTraining complete.")
    print(f"  Train: n={report['n_train']}, LL={report['train_metrics']['logloss']}")
    if report.get("val_metrics"):
        print(f"  Val:   n={report['n_val']}, LL={report['val_metrics']['logloss']}")


if __name__ == "__main__":
    main()

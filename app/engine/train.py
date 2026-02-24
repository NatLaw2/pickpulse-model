"""Generic model training — time-based split, calibration, artifact storage."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from .config import ModuleConfig, get_module
from .features import prepare_features


def train_model(
    df: pd.DataFrame,
    module: ModuleConfig,
    val_frac: float = 0.2,
    model_type: str = "auto",
) -> Dict[str, Any]:
    """Train a binary classifier for the given module.

    Args:
        df: Prepared DataFrame with label + features.
        module: Module configuration.
        val_frac: Fraction for time-based validation holdout.
        model_type: "logistic", "gradient_boosting", or "auto" (picks based on data size).

    Returns:
        Report dict with metrics and artifact paths.
    """
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, brier_score_loss, log_loss,
    )

    print(f"\n{'=' * 60}")
    print(f"  Predictive Engine — Training: {module.display_name}")
    print(f"{'=' * 60}\n")

    # Sort by timestamp for time-based split
    ts_col = module.timestamp_column
    if ts_col in df.columns:
        df = df.copy()
        df["_ts_parsed"] = pd.to_datetime(df[ts_col], errors="coerce")
        df = df.sort_values("_ts_parsed").reset_index(drop=True)
        df = df.drop(columns=["_ts_parsed"])
    else:
        print(f"[train] Warning: timestamp column '{ts_col}' not found. Using row order.")

    n = len(df)
    print(f"[train] Dataset: {n} rows")

    if n < 50:
        return {"error": "insufficient_data", "n_rows": n,
                "message": f"Need at least 50 rows, got {n}."}

    # Build features
    X, y, feature_names, feature_meta = prepare_features(df, module, fit=True)
    print(f"[train] Features: {len(feature_names)} columns")
    print(f"[train] Label distribution: {dict(zip(*np.unique(y, return_counts=True)))}")

    # Time-based split
    split_idx = int(n * (1 - val_frac))
    if split_idx < 30 or (n - split_idx) < 10:
        print(f"[train] Not enough for split. Training on all {n} rows.")
        split_idx = n

    X_train, y_train = X[:split_idx], y[:split_idx]
    X_val, y_val = X[split_idx:], y[split_idx:]

    print(f"[train] Train: {len(y_train)} rows")
    print(f"[train] Val:   {len(y_val)} rows")

    # Choose model
    if model_type == "auto":
        model_type = "gradient_boosting" if n >= 500 else "logistic"
    print(f"[train] Model type: {model_type}")

    # Compute sample weights for class imbalance
    from sklearn.utils.class_weight import compute_sample_weight
    sample_weights = compute_sample_weight("balanced", y_train)

    if model_type == "gradient_boosting":
        base_model = HistGradientBoostingClassifier(
            max_iter=300,
            max_depth=5,
            learning_rate=0.05,
            min_samples_leaf=20,
            random_state=42,
            class_weight="balanced",
        )
        base_model.fit(X_train, y_train)
    else:
        base_model = Pipeline([
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(
                C=1.0, penalty="l2", solver="lbfgs",
                max_iter=2000, random_state=42,
                class_weight="balanced",
            )),
        ])
        base_model.fit(X_train, y_train)

    # Calibrate with Platt scaling (sigmoid) via cross-validation
    print(f"[train] Calibrating with CalibratedClassifierCV (sigmoid, cv={module.calibration.cv_folds})")
    calibrated_model = CalibratedClassifierCV(
        estimator=base_model,
        method=module.calibration.method,
        cv=module.calibration.cv_folds,
    )
    calibrated_model.fit(X_train, y_train)

    # Clamp helper
    floor, ceil = module.calibration.prob_floor, module.calibration.prob_ceil

    def clamp_probs(p: np.ndarray) -> np.ndarray:
        return np.clip(p, floor, ceil)

    # Train metrics
    train_probs = clamp_probs(calibrated_model.predict_proba(X_train)[:, 1])
    train_metrics = _compute_metrics(train_probs, y_train, "Train")

    # Val metrics
    val_metrics = None
    val_probs = None
    if len(y_val) >= 10:
        val_probs = clamp_probs(calibrated_model.predict_proba(X_val)[:, 1])
        val_metrics = _compute_metrics(val_probs, y_val, "Val")

    # Feature importance (from the base model, not the calibration wrapper)
    importance = _extract_importance(base_model, feature_names, model_type, X_train, y_train)
    print(f"\n[train] Top features:")
    for f in importance[:10]:
        print(f"  {f['feature']:30s}  importance={f['importance']:+.5f}")

    # Save artifacts
    os.makedirs(module.artifact_dir, exist_ok=True)

    model_path = os.path.join(module.artifact_dir, "model.joblib")
    joblib.dump(calibrated_model, model_path)
    print(f"\n[train] Saved model -> {model_path}")

    base_model_path = os.path.join(module.artifact_dir, "base_model.joblib")
    joblib.dump(base_model, base_model_path)

    feature_meta_path = os.path.join(module.artifact_dir, "feature_meta.json")
    # Convert numpy types for JSON serialization
    serializable_meta = _make_serializable(feature_meta)
    with open(feature_meta_path, "w") as f:
        json.dump(serializable_meta, f, indent=2)

    # Model versioning — increment from previous version
    version_num = 1
    prev_meta_path = os.path.join(module.artifact_dir, "metadata.json")
    if os.path.exists(prev_meta_path):
        try:
            with open(prev_meta_path) as f:
                prev = json.load(f)
            prev_ver = prev.get("version", f"{module.name}_v0")
            prev_num = int(prev_ver.rsplit("_v", 1)[-1])
            version_num = prev_num + 1
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
    version_str = f"{module.name}_v{version_num}"
    print(f"[train] Version: {version_str}")

    metadata = {
        "module": module.name,
        "version": version_str,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "model_type": model_type,
        "n_features": len(feature_names),
        "features": feature_names,
        "n_train": len(y_train),
        "n_val": len(y_val),
        "calibration_method": module.calibration.method,
        "prob_range": [floor, ceil],
        "train_metrics": train_metrics,
        "val_metrics": val_metrics,
        "feature_importance": importance,
        "artifact_paths": {
            "model": model_path,
            "base_model": base_model_path,
            "feature_meta": feature_meta_path,
        },
    }

    meta_path = os.path.join(module.artifact_dir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"[train] Saved metadata -> {meta_path}")

    print(f"\n{'=' * 60}")
    print(f"  TRAINING COMPLETE — {module.display_name}")
    if train_metrics:
        print(f"  Train AUC: {train_metrics.get('auc', 'N/A')}")
    if val_metrics:
        print(f"  Val AUC:   {val_metrics.get('auc', 'N/A')}")
        print(f"  Val Brier: {val_metrics.get('brier', 'N/A')}")
    print(f"{'=' * 60}\n")

    return metadata


def _compute_metrics(probs: np.ndarray, y: np.ndarray, label: str = "") -> Dict[str, Any]:
    """Compute standard classification metrics."""
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, brier_score_loss, log_loss,
        confusion_matrix, precision_recall_curve,
    )

    n = len(y)
    eps = 1e-15
    probs_clipped = np.clip(probs, eps, 1 - eps)

    metrics: Dict[str, Any] = {"n": n}

    try:
        metrics["auc"] = round(float(roc_auc_score(y, probs)), 5)
    except ValueError:
        metrics["auc"] = None

    try:
        metrics["pr_auc"] = round(float(average_precision_score(y, probs)), 5)
    except ValueError:
        metrics["pr_auc"] = None

    metrics["brier"] = round(float(brier_score_loss(y, probs)), 5)
    metrics["logloss"] = round(float(log_loss(y, probs_clipped)), 5)

    # Calibration bins
    n_bins = min(10, max(2, n // 50))
    sorted_idx = np.argsort(probs)
    chunk = max(1, n // n_bins)
    cal_bins = []
    for i in range(0, n, chunk):
        sl = sorted_idx[i:i + chunk]
        if len(sl) == 0:
            continue
        cal_bins.append({
            "bin_lo": round(float(probs[sl].min()), 4),
            "bin_hi": round(float(probs[sl].max()), 4),
            "n": int(len(sl)),
            "predicted_avg": round(float(probs[sl].mean()), 4),
            "actual_rate": round(float(y[sl].mean()), 4),
        })
    metrics["calibration_bins"] = cal_bins

    # Lift by decile
    decile_table = _compute_lift_table(probs, y)
    metrics["lift_table"] = decile_table

    # Confusion matrix at 0.5 threshold
    preds = (probs >= 0.5).astype(int)
    cm = confusion_matrix(y, preds, labels=[0, 1]).tolist()
    metrics["confusion_matrix"] = cm

    if label:
        print(f"[train] {label}: n={n}, AUC={metrics.get('auc')}, "
              f"Brier={metrics['brier']}, LogLoss={metrics['logloss']}")

    return metrics


def _compute_lift_table(probs: np.ndarray, y: np.ndarray) -> List[Dict[str, Any]]:
    """Compute lift/decile table."""
    n = len(y)
    n_deciles = min(10, max(2, n // 20))
    sorted_idx = np.argsort(-probs)  # descending
    chunk = max(1, n // n_deciles)
    base_rate = float(y.mean())
    table = []
    cumulative_positives = 0
    total_positives = int(y.sum())

    for i in range(0, n, chunk):
        sl = sorted_idx[i:i + chunk]
        if len(sl) == 0:
            continue
        decile = len(table) + 1
        actual_rate = float(y[sl].mean())
        cumulative_positives += int(y[sl].sum())
        capture_rate = cumulative_positives / total_positives if total_positives > 0 else 0.0
        lift = actual_rate / base_rate if base_rate > 0 else 0.0
        table.append({
            "decile": decile,
            "n": int(len(sl)),
            "avg_prob": round(float(probs[sl].mean()), 4),
            "actual_rate": round(actual_rate, 4),
            "lift": round(lift, 2),
            "cumulative_capture": round(capture_rate, 4),
        })

    return table


def _extract_importance(
    model: Any, feature_names: List[str], model_type: str,
    X_train: Optional[np.ndarray] = None, y_train: Optional[np.ndarray] = None,
) -> List[Dict[str, Any]]:
    """Extract feature importance from trained model."""
    importance = []

    if model_type == "gradient_boosting":
        try:
            imp = model.feature_importances_
            for i, name in enumerate(feature_names):
                importance.append({
                    "feature": name,
                    "importance": round(float(imp[i]), 5),
                })
        except AttributeError:
            # Fallback: permutation importance
            if X_train is not None and y_train is not None:
                importance = _permutation_importance(model, X_train, y_train, feature_names)
            else:
                for name in feature_names:
                    importance.append({"feature": name, "importance": 0.0})
    else:
        try:
            if hasattr(model, "named_steps"):
                lr = model.named_steps["lr"]
            else:
                lr = model
            coef = lr.coef_[0]
            for i, name in enumerate(feature_names):
                importance.append({
                    "feature": name,
                    "importance": round(float(coef[i]), 5),
                })
        except (AttributeError, IndexError):
            for name in feature_names:
                importance.append({"feature": name, "importance": 0.0})

    importance.sort(key=lambda x: abs(x["importance"]), reverse=True)
    return importance


def _permutation_importance(
    model: Any, X: np.ndarray, y: np.ndarray, feature_names: List[str],
) -> List[Dict[str, Any]]:
    """Compute permutation importance as a fallback."""
    from sklearn.metrics import roc_auc_score

    try:
        base_probs = model.predict_proba(X)[:, 1]
        base_auc = roc_auc_score(y, base_probs)
    except Exception:
        return [{"feature": n, "importance": 0.0} for n in feature_names]

    importance = []
    rng = np.random.RandomState(42)
    for i, name in enumerate(feature_names):
        X_perm = X.copy()
        X_perm[:, i] = rng.permutation(X_perm[:, i])
        try:
            perm_probs = model.predict_proba(X_perm)[:, 1]
            perm_auc = roc_auc_score(y, perm_probs)
            drop = base_auc - perm_auc
        except Exception:
            drop = 0.0
        importance.append({"feature": name, "importance": round(float(drop), 5)})

    return importance


def _make_serializable(obj: Any) -> Any:
    """Convert numpy types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

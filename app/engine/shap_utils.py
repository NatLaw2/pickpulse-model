"""SHAP-based per-account driver extraction.

Wraps shap library calls with fallbacks so a missing or incompatible shap
installation never blocks predictions — it just skips driver computation.

Usage (at predict time):
    explainer = build_explainer(base_model, shap_background)
    shap_vals = compute_shap_values(explainer, X)
    drivers = extract_top_drivers(shap_vals[i], feature_names, n=5)
    confidence = compute_confidence_level(scored_features, total_features)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)


def build_explainer(base_model: Any, X_background: np.ndarray) -> Any:
    """Build a SHAP explainer appropriate for *base_model*.

    Tries (in order): TreeExplainer → LinearExplainer → KernelExplainer.
    Returns None on complete failure so callers can skip SHAP gracefully.
    """
    try:
        import shap
    except ImportError:
        logger.warning("shap not installed — driver extraction disabled")
        return None

    # --- TreeExplainer: fast, exact for gradient-boosted trees ---
    try:
        explainer = shap.TreeExplainer(base_model)
        logger.info("shap_utils: TreeExplainer selected")
        return explainer
    except Exception:
        pass

    # --- LinearExplainer: for LogisticRegression wrapped in a Pipeline ---
    try:
        from sklearn.pipeline import Pipeline
        if isinstance(base_model, Pipeline) and "scaler" in base_model.named_steps:
            scaler = base_model.named_steps["scaler"]
            lr = base_model.named_steps["lr"]
            X_bg_scaled = scaler.transform(X_background)
            explainer = shap.LinearExplainer(lr, X_bg_scaled)
            logger.info("shap_utils: LinearExplainer selected (Pipeline)")
            return explainer
    except Exception:
        pass

    # --- KernelExplainer: model-agnostic fallback (slow) ---
    try:
        sample_size = min(50, len(X_background))
        bg_sample = shap.sample(X_background, sample_size)
        explainer = shap.KernelExplainer(
            lambda X: base_model.predict_proba(X)[:, 1],
            bg_sample,
        )
        logger.info("shap_utils: KernelExplainer selected (fallback)")
        return explainer
    except Exception as exc:
        logger.warning("shap_utils: all explainer types failed: %s", exc)
        return None


def compute_shap_values(
    explainer: Any,
    X: np.ndarray,
) -> np.ndarray:
    """Compute SHAP values for *X*.

    Returns a 2-D array (n_samples, n_features). On failure returns zeros
    so callers always get a usable array shape.
    """
    if explainer is None:
        return np.zeros_like(X, dtype=float)

    try:
        sv = explainer.shap_values(X)
        # Binary classifiers from TreeExplainer return [neg_class, pos_class].
        # Take the positive (churn) class.
        if isinstance(sv, list) and len(sv) == 2:
            sv = sv[1]
        return np.asarray(sv, dtype=float)
    except Exception as exc:
        logger.warning("shap_utils: SHAP value computation failed: %s", exc)
        return np.zeros_like(X, dtype=float)


def extract_top_drivers(
    shap_row: np.ndarray,
    feature_names: List[str],
    n: int = 5,
) -> List[Dict[str, Any]]:
    """Extract the top *n* SHAP drivers for a single account row.

    Args:
        shap_row: 1-D array of SHAP values for one prediction.
        feature_names: Feature names aligned with positions in shap_row.
        n: Maximum number of drivers to return.

    Returns:
        List of dicts (feature, shap_value, direction).
        Empty list if shap_row and feature_names lengths differ.
    """
    if len(shap_row) != len(feature_names):
        return []

    abs_vals = np.abs(shap_row)
    sorted_idx = np.argsort(-abs_vals)  # descending by magnitude

    drivers = []
    for idx in sorted_idx[:n]:
        sv = float(shap_row[idx])
        if abs(sv) < 1e-7:
            break
        drivers.append({
            "feature": feature_names[idx],
            "shap_value": round(sv, 5),
            "direction": "increases_risk" if sv > 0 else "decreases_risk",
        })
    return drivers


def compute_confidence_level(scored_features: int, total_features: int) -> str:
    """Return "high" | "medium" | "low" based on feature data completeness.

    Args:
        scored_features: Number of features that had real (non-null) data.
        total_features: Total features the model expects.
    """
    if total_features == 0:
        return "low"
    coverage = scored_features / total_features
    if coverage >= 0.7:
        return "high"
    if coverage >= 0.4:
        return "medium"
    return "low"

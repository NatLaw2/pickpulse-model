"""SHAP-based per-account driver extraction.

Wraps shap library calls with fallbacks so a missing or incompatible shap
installation never blocks predictions — it just skips driver computation.

Usage (at predict time):
    explainer = build_explainer(base_model, shap_background)
    shap_vals = compute_shap_values(explainer, X)
    drivers = extract_top_drivers(shap_vals[i], feature_names, n=5)
    confidence = compute_confidence_level(scored_features, total_features)
    portfolio = aggregate_portfolio_shap(shap_vals, feature_names, arr_values)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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
    except Exception as exc:
        logger.warning("shap_utils: TreeExplainer failed (%s: %s) — trying next", type(exc).__name__, exc)

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
    except Exception as exc:
        logger.warning("shap_utils: LinearExplainer failed (%s: %s) — trying next", type(exc).__name__, exc)

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


def aggregate_portfolio_shap(
    shap_vals_arr: np.ndarray,
    feature_names: List[str],
    arr_values: Optional[List[Optional[float]]] = None,
    arr_cap_pct: float = 0.20,
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """Aggregate SHAP values across all scored accounts into portfolio-level drivers.

    Uses capped ARR-weighted signed SHAP as the primary ranking metric.
    Also computes mean absolute SHAP (unweighted) for secondary diagnostic view.

    Args:
        shap_vals_arr: 2-D array (n_accounts, n_features) of per-account SHAP values.
        feature_names:  Feature names aligned with columns in shap_vals_arr.
        arr_values:     Per-account ARR (aligned with rows). None entries use 0 weight.
        arr_cap_pct:    Maximum fraction of total ARR any single account contributes (0.20 = 20%).
        top_n:          Number of top drivers to return.

    Returns:
        List of dicts sorted by abs(arr_weighted_shap) descending:
          feature, arr_weighted_shap, mean_abs_shap, direction,
          pct_accounts_positive, n_accounts_material, pct_accounts_material
    """
    n_accounts, n_features = shap_vals_arr.shape
    if n_accounts == 0 or n_features == 0:
        return []

    # Build ARR weight vector with cap
    if arr_values and len(arr_values) == n_accounts:
        raw_arr = np.array(
            [float(v) if v is not None and not np.isnan(float(v)) else 0.0
             for v in arr_values],
            dtype=float,
        )
    else:
        raw_arr = np.ones(n_accounts, dtype=float)

    total_arr = float(raw_arr.sum())
    if total_arr <= 0:
        weights = np.ones(n_accounts, dtype=float) / n_accounts
    else:
        cap = total_arr * arr_cap_pct
        capped_arr = np.minimum(raw_arr, cap)
        capped_total = float(capped_arr.sum())
        weights = capped_arr / capped_total if capped_total > 0 else np.ones(n_accounts) / n_accounts

    # Compute per-feature aggregates
    results = []
    for fi in range(n_features):
        col = shap_vals_arr[:, fi]
        arr_weighted_shap = float(np.dot(weights, col))
        mean_abs_shap = float(np.mean(np.abs(col)))

        # Direction: sign of ARR-weighted sum
        direction = "increases_risk" if arr_weighted_shap >= 0 else "decreases_risk"

        # How many accounts have positive SHAP (pushes toward churn) for this feature?
        n_positive = int(np.sum(col > 0))
        pct_accounts_positive = n_positive / n_accounts if n_accounts > 0 else 0.0

        # Material = |shap| >= 1% of mean absolute across all features
        mean_abs_all = float(np.mean(np.abs(shap_vals_arr))) if shap_vals_arr.size > 0 else 1.0
        material_threshold = max(1e-6, mean_abs_all * 0.01)
        n_material = int(np.sum(np.abs(col) >= material_threshold))
        pct_accounts_material = n_material / n_accounts if n_accounts > 0 else 0.0

        results.append({
            "feature": feature_names[fi],
            "arr_weighted_shap": round(arr_weighted_shap, 6),
            "mean_abs_shap": round(mean_abs_shap, 6),
            "direction": direction,
            "pct_accounts_positive": round(pct_accounts_positive, 4),
            "n_accounts_material": n_material,
            "pct_accounts_material": round(pct_accounts_material, 4),
        })

    # Sort by magnitude of ARR-weighted SHAP descending, return top_n
    results.sort(key=lambda x: abs(x["arr_weighted_shap"]), reverse=True)
    return results[:top_n]


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

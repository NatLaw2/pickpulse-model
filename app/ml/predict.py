"""Load trained model artifacts and return calibrated win probability.

Used by model_nba.py at inference time (FastAPI endpoint).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .calibrate import apply_calibrator, load_calibrator


# ---------------------------------------------------------------------------
# Artifact loading (cached per-process)
# ---------------------------------------------------------------------------

_MODEL_CACHE: Optional[Dict[str, Any]] = None
_CAL_CACHE: Optional[Dict[str, Any]] = None
_LOADED = False


def _load_artifacts() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    global _MODEL_CACHE, _CAL_CACHE, _LOADED
    if _LOADED:
        return _MODEL_CACHE, _CAL_CACHE

    model_path = os.getenv("ML_MODEL_PATH", "artifacts/ml_model.json")
    cal_path = os.getenv("ML_CALIBRATOR_PATH", "artifacts/ml_calibrator.json")

    try:
        with open(model_path, "r") as f:
            _MODEL_CACHE = json.load(f)
        print(f"[ml.predict] Loaded model from {model_path}")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[ml.predict] Model not found at {model_path}: {e}")
        _MODEL_CACHE = None

    _CAL_CACHE = load_calibrator(cal_path)
    if _CAL_CACHE:
        print(f"[ml.predict] Loaded calibrator from {cal_path}")
    else:
        print(f"[ml.predict] Calibrator not found at {cal_path}")

    _LOADED = True
    return _MODEL_CACHE, _CAL_CACHE


def is_available() -> bool:
    """Check if ML model artifacts are available."""
    model, _ = _load_artifacts()
    return model is not None


def predict_win_prob(
    locked_home_nv: float,
    locked_away_nv: float,
    spread_home_point: float,
    is_home: int,
) -> Optional[float]:
    """Predict calibrated win probability for a pick.

    Args:
        locked_home_nv: no-vig implied prob for home at lock/current time
        locked_away_nv: no-vig implied prob for away at lock/current time
        spread_home_point: home spread point (0 if unavailable)
        is_home: 1 if picking home, 0 if picking away

    Returns:
        Calibrated probability of winning (0-1), or None if model unavailable.
    """
    model_data, cal_data = _load_artifacts()
    if model_data is None:
        return None

    model_info = model_data.get("model", {})
    features = model_info.get("features", [])
    coef = model_info.get("coefficients", [])
    intercept = model_info.get("intercept", 0.0)

    if not coef or not features:
        return None

    # Build feature vector matching training feature order
    # Features: locked_home_nv, locked_away_nv, spread_home_point, is_home,
    #           selected_nv, opponent_nv
    selected_nv = locked_home_nv if is_home == 1 else locked_away_nv
    opponent_nv = locked_away_nv if is_home == 1 else locked_home_nv

    feature_map = {
        "locked_home_nv": locked_home_nv,
        "locked_away_nv": locked_away_nv,
        "spread_home_point": spread_home_point,
        "is_home": float(is_home),
        "selected_nv": selected_nv,
        "opponent_nv": opponent_nv,
    }

    x = np.array([feature_map.get(f, 0.0) for f in features], dtype=np.float64)

    # Logistic regression: p = sigmoid(x @ coef + intercept)
    logit = float(np.dot(x, coef) + intercept)
    raw_prob = 1.0 / (1.0 + np.exp(-logit))

    # Apply calibrator if available
    if cal_data is not None:
        calibrated = apply_calibrator(cal_data, np.array([raw_prob]))[0]
        return float(np.clip(calibrated, 0.01, 0.99))

    return float(np.clip(raw_prob, 0.01, 0.99))

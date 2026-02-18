"""Load trained model artifacts and return calibrated win probability.

Used by model_nba.py at inference time (FastAPI endpoint).

Supports two artifact formats:
  - joblib (preferred): artifacts/ml_model.joblib + ml_calibrator.joblib
  - JSON (legacy): artifacts/ml_model.json + ml_calibrator.json
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Artifact loading (cached per-process)
# ---------------------------------------------------------------------------

_MODEL = None          # sklearn LogisticRegression (joblib) or dict (JSON)
_CALIBRATOR = None     # sklearn IsotonicRegression (joblib) or dict (JSON)
_FEATURES = None       # list of feature names
_FORMAT = None         # "joblib" or "json"
_LOADED = False


def _load_artifacts():
    global _MODEL, _CALIBRATOR, _FEATURES, _FORMAT, _LOADED
    if _LOADED:
        return

    # Try joblib first (preferred)
    model_joblib = os.getenv("ML_MODEL_PATH", "artifacts/ml_model.joblib")
    cal_joblib = os.getenv("ML_CALIBRATOR_PATH", "artifacts/ml_calibrator.joblib")

    if os.path.exists(model_joblib):
        try:
            import joblib
            _MODEL = joblib.load(model_joblib)
            print(f"[ml.predict] Loaded model from {model_joblib}")

            # Load features from metadata
            meta_path = os.path.join(os.path.dirname(model_joblib), "ml_metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
                _FEATURES = meta.get("features", [])

            if os.path.exists(cal_joblib):
                _CALIBRATOR = joblib.load(cal_joblib)
                print(f"[ml.predict] Loaded calibrator from {cal_joblib}")

            _FORMAT = "joblib"
            _LOADED = True
            return
        except Exception as e:
            print(f"[ml.predict] Failed to load joblib artifacts: {e}")

    # Fallback to JSON format
    model_json = os.getenv("ML_MODEL_JSON_PATH", "artifacts/ml_model.json")
    cal_json = os.getenv("ML_CALIBRATOR_JSON_PATH", "artifacts/ml_calibrator.json")

    if os.path.exists(model_json):
        try:
            with open(model_json) as f:
                _MODEL = json.load(f)
            print(f"[ml.predict] Loaded model from {model_json} (JSON legacy)")

            model_info = _MODEL.get("model", {})
            _FEATURES = model_info.get("features", [])

            if os.path.exists(cal_json):
                with open(cal_json) as f:
                    _CALIBRATOR = json.load(f)
                print(f"[ml.predict] Loaded calibrator from {cal_json}")

            _FORMAT = "json"
            _LOADED = True
            return
        except Exception as e:
            print(f"[ml.predict] Failed to load JSON artifacts: {e}")

    print("[ml.predict] No model artifacts found")
    _LOADED = True  # Don't retry


def is_available() -> bool:
    """Check if ML model artifacts are available."""
    _load_artifacts()
    return _MODEL is not None


def predict_win_prob(
    locked_home_nv: float,
    locked_away_nv: float,
    spread_home_point: float = 0.0,
    is_home: int = 1,
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
    _load_artifacts()
    if _MODEL is None:
        return None

    if _FORMAT == "joblib":
        return _predict_joblib(locked_home_nv, locked_away_nv, is_home)
    else:
        return _predict_json(locked_home_nv, locked_away_nv, spread_home_point, is_home)


def _predict_joblib(
    locked_home_nv: float,
    locked_away_nv: float,
    is_home: int,
) -> Optional[float]:
    """Predict using sklearn joblib artifacts.

    The model is trained on home-win labels with is_home=1 for all rows.
    It always outputs P(home wins). When is_home=0 (asking for away side),
    we return 1 - P(home wins).
    """
    eps = 1e-6

    # Always build features from home perspective (matching training)
    feature_map = {
        "p_home_nv": locked_home_nv,
        "p_away_nv": locked_away_nv,
        "is_home": 1.0,  # Always predict from home perspective
        "favorite_nv": max(locked_home_nv, locked_away_nv),
        "underdog_nv": min(locked_home_nv, locked_away_nv),
        "log_odds_ratio": float(np.log((locked_home_nv + eps) / (locked_away_nv + eps))),
        "snapshot_offset_minutes": 15.0,  # Assume T-15 in production
        # Legacy feature names (for JSON model compat)
        "locked_home_nv": locked_home_nv,
        "locked_away_nv": locked_away_nv,
        "spread_home_point": 0.0,
        "selected_nv": locked_home_nv,
        "opponent_nv": locked_away_nv,
    }

    features = _FEATURES or list(feature_map.keys())
    x = np.array([[feature_map.get(f, 0.0) for f in features]], dtype=np.float64)

    try:
        raw_prob = _MODEL.predict_proba(x)[0, 1]  # P(home wins)

        if _CALIBRATOR is not None:
            p_home = float(_CALIBRATOR.predict(np.array([raw_prob]))[0])
        else:
            p_home = float(raw_prob)

        p_home = float(np.clip(p_home, 0.01, 0.99))

        # If asking for away side, return complement
        if is_home == 0:
            return float(np.clip(1.0 - p_home, 0.01, 0.99))
        return p_home

    except Exception as e:
        print(f"[ml.predict] Prediction error: {e}")
        return None


def _predict_json(
    locked_home_nv: float,
    locked_away_nv: float,
    spread_home_point: float,
    is_home: int,
) -> Optional[float]:
    """Predict using JSON-serialized model (legacy path)."""
    model_info = _MODEL.get("model", {})
    features = model_info.get("features", [])
    coef = model_info.get("coefficients", [])
    intercept = model_info.get("intercept", 0.0)

    if not coef or not features:
        return None

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
    logit = float(np.dot(x, coef) + intercept)
    raw_prob = 1.0 / (1.0 + np.exp(-logit))

    if _CALIBRATOR is not None and isinstance(_CALIBRATOR, dict):
        from .calibrate import apply_calibrator
        calibrated = apply_calibrator(_CALIBRATOR, np.array([raw_prob]))[0]
        return float(np.clip(calibrated, 0.01, 0.99))

    return float(np.clip(raw_prob, 0.01, 0.99))

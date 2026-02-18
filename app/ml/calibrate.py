"""Isotonic / Platt calibration for the probability model.

Fits on training predictions, applies at inference time.
Serializes to JSON for artifact storage.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np


def fit_calibrator(
    probs: np.ndarray, y: np.ndarray, method: str = "isotonic"
) -> Dict[str, Any]:
    """Fit a calibrator on predicted probabilities vs actual outcomes.

    Returns a JSON-serializable calibrator dict.
    """
    from sklearn.isotonic import IsotonicRegression

    if method == "isotonic":
        iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip")
        iso.fit(probs, y)
        # Serialize the fitted function as (x, y) pairs
        x_vals = iso.X_thresholds_.tolist()
        y_vals = iso.y_thresholds_.tolist()
        return {
            "method": "isotonic",
            "x": x_vals,
            "y": y_vals,
            "n_samples": len(probs),
        }
    else:
        raise ValueError(f"Unknown calibration method: {method}")


def apply_calibrator(cal: Dict[str, Any], probs: np.ndarray) -> np.ndarray:
    """Apply a fitted calibrator to raw probabilities."""
    method = cal.get("method", "isotonic")
    if method == "isotonic":
        x = np.array(cal["x"])
        y = np.array(cal["y"])
        # np.interp does linear interpolation between knots
        return np.clip(np.interp(probs, x, y), 0.01, 0.99)
    raise ValueError(f"Unknown calibration method: {method}")


def save_calibrator(cal: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(cal, f, indent=2)


def load_calibrator(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

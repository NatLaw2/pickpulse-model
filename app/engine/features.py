"""Generic feature engineering — numeric, categorical, datetime handling."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import ModuleConfig


def prepare_features(
    df: pd.DataFrame,
    module: ModuleConfig,
    fit: bool = True,
    feature_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[np.ndarray, np.ndarray, List[str], Dict[str, Any]]:
    """Build feature matrix X and label vector y from a DataFrame.

    Args:
        df: Input DataFrame (must have label and feature columns).
        module: Module configuration.
        fit: If True, learn encoding/imputation params; if False, apply existing.
        feature_meta: Previously learned params (required when fit=False).

    Returns:
        (X, y, feature_names, meta) where meta stores learned params.
    """
    work = df.copy()
    label_col = module.label_column

    # Ensure label is binary int
    if label_col in work.columns:
        work[label_col] = work[label_col].astype(int)
        y = work[label_col].values
    else:
        y = np.zeros(len(work), dtype=int)

    # Identify feature columns (exclude id, timestamp, label, value)
    exclude = {module.id_column, module.timestamp_column, label_col}
    if module.value_column:
        # Keep value column as a feature — it's predictive
        pass

    candidate_cols = [c for c in work.columns if c not in exclude]

    # Classify columns
    numeric_cols: List[str] = []
    categorical_cols: List[str] = []
    datetime_cols: List[str] = []

    for col in candidate_cols:
        series = work[col]
        if pd.api.types.is_numeric_dtype(series):
            numeric_cols.append(col)
        elif pd.api.types.is_datetime64_any_dtype(series):
            datetime_cols.append(col)
        else:
            # Try numeric conversion
            try:
                work[col] = pd.to_numeric(series, errors="raise")
                numeric_cols.append(col)
                continue
            except (ValueError, TypeError):
                pass
            # Try datetime
            try:
                work[col] = pd.to_datetime(series, errors="raise")
                datetime_cols.append(col)
                continue
            except (ValueError, TypeError):
                pass
            # Categorical
            if series.nunique() <= 50:
                categorical_cols.append(col)
            # else skip high-cardinality text

    meta: Dict[str, Any] = feature_meta or {}

    # --- Numeric: impute with median ---
    if fit:
        medians = {}
        for col in numeric_cols:
            medians[col] = float(work[col].median()) if not work[col].isna().all() else 0.0
        meta["numeric_cols"] = numeric_cols
        meta["medians"] = medians
    else:
        numeric_cols = meta.get("numeric_cols", numeric_cols)
        medians = meta.get("medians", {})

    for col in numeric_cols:
        if col in work.columns:
            work[col] = work[col].fillna(medians.get(col, 0.0)).astype(float)

    # --- Datetime: extract day_of_week, month, days_since_epoch ---
    dt_features: List[str] = []
    for col in datetime_cols:
        if col in work.columns:
            dt = pd.to_datetime(work[col], errors="coerce")
            dow_col = f"{col}_dow"
            month_col = f"{col}_month"
            work[dow_col] = dt.dt.dayofweek.fillna(0).astype(float)
            work[month_col] = dt.dt.month.fillna(1).astype(float)
            dt_features.extend([dow_col, month_col])
    if fit:
        meta["dt_features"] = dt_features

    # --- Categorical: one-hot encode (top N categories) ---
    ohe_cols: List[str] = []
    max_categories = 10
    if fit:
        cat_mappings: Dict[str, List[str]] = {}
        for col in categorical_cols:
            if col not in work.columns:
                continue
            top = work[col].fillna("__missing__").value_counts().head(max_categories).index.tolist()
            cat_mappings[col] = top
            for val in top:
                ohe_name = f"{col}_{val}"
                work[ohe_name] = (work[col].fillna("__missing__") == val).astype(float)
                ohe_cols.append(ohe_name)
        meta["cat_mappings"] = cat_mappings
        meta["ohe_cols"] = ohe_cols
    else:
        cat_mappings = meta.get("cat_mappings", {})
        ohe_cols = meta.get("ohe_cols", [])
        for col, vals in cat_mappings.items():
            if col in work.columns:
                for val in vals:
                    ohe_name = f"{col}_{val}"
                    work[ohe_name] = (work[col].fillna("__missing__") == val).astype(float)
            else:
                for val in vals:
                    ohe_name = f"{col}_{val}"
                    work[ohe_name] = 0.0

    # Assemble feature matrix
    feature_names = numeric_cols + meta.get("dt_features", dt_features) + ohe_cols
    # Only keep columns that exist
    feature_names = [f for f in feature_names if f in work.columns]

    if fit:
        meta["feature_names"] = feature_names

    if not feature_names:
        raise ValueError("No usable features found in the dataset.")

    X = work[feature_names].values.astype(np.float64)

    # Replace any remaining NaN/inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    return X, y, feature_names, meta

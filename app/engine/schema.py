"""Generic schema validation for uploaded datasets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from .config import ModuleConfig


@dataclass
class ColumnInfo:
    name: str
    dtype: str              # "numeric", "categorical", "datetime", "boolean", "unknown"
    missing_count: int = 0
    missing_pct: float = 0.0
    n_unique: int = 0
    sample_values: List[Any] = field(default_factory=list)


@dataclass
class ValidationResult:
    valid: bool
    module: str
    n_rows: int = 0
    n_columns: int = 0
    columns: List[ColumnInfo] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    label_distribution: Dict[str, int] = field(default_factory=dict)


def _infer_dtype(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    # Try parsing as date
    try:
        pd.to_datetime(series.dropna().head(20))
        return "datetime"
    except (ValueError, TypeError):
        pass
    n_unique = series.nunique()
    if n_unique <= 50 or n_unique / len(series) < 0.05:
        return "categorical"
    return "unknown"


def validate_dataset(df: pd.DataFrame, module: ModuleConfig) -> ValidationResult:
    """Validate an uploaded DataFrame against a module's schema."""
    result = ValidationResult(valid=True, module=module.name)
    result.n_rows = len(df)
    result.n_columns = len(df.columns)

    # Check required columns
    for col in module.required_columns:
        if col not in df.columns:
            result.missing_required.append(col)
            result.errors.append(f"Missing required column: '{col}'")
            result.valid = False

    # Column info
    for col_name in df.columns:
        series = df[col_name]
        missing = int(series.isna().sum())
        info = ColumnInfo(
            name=col_name,
            dtype=_infer_dtype(series),
            missing_count=missing,
            missing_pct=round(missing / len(df) * 100, 1) if len(df) > 0 else 0.0,
            n_unique=int(series.nunique()),
            sample_values=series.dropna().head(3).tolist(),
        )
        result.columns.append(info)

        if missing > 0 and col_name in module.required_columns:
            result.warnings.append(
                f"Required column '{col_name}' has {missing} missing values ({info.missing_pct}%)"
            )

    # Label distribution
    if module.label_column in df.columns:
        dist = df[module.label_column].value_counts().to_dict()
        result.label_distribution = {str(k): int(v) for k, v in dist.items()}
        n_classes = len(result.label_distribution)
        if n_classes < 2:
            result.errors.append(
                f"Label column '{module.label_column}' has only {n_classes} unique value(s). Need at least 2."
            )
            result.valid = False
        if n_classes > 2:
            result.warnings.append(
                f"Label column '{module.label_column}' has {n_classes} unique values. "
                "Will binarize: values matching positive_label='1' vs rest."
            )

    # Timestamp check
    if module.timestamp_column in df.columns:
        try:
            pd.to_datetime(df[module.timestamp_column].dropna().head(20))
        except (ValueError, TypeError):
            result.warnings.append(
                f"Timestamp column '{module.timestamp_column}' may not be parseable as dates."
            )

    # Size warnings
    if result.n_rows < 100:
        result.warnings.append(f"Dataset has only {result.n_rows} rows. Recommend 500+ for reliable models.")
    elif result.n_rows < 500:
        result.warnings.append(f"Dataset has {result.n_rows} rows. Results may be noisy with <500 rows.")

    return result

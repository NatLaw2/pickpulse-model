"""Messy data normalization and data quality auditing for CRM ingestion.

Goals:
  - Never crash on a single bad record
  - Parse whatever date/number format HubSpot sends
  - Strip placeholder strings ("N/A", "-", "none", etc.)
  - Produce a DataQualityReport showing field coverage before scoring

Usage:
    from app.integrations.normalization import normalize_value, normalize_record, audit_records

    clean = normalize_record(raw_props, schema_mapping)
    report = audit_records(all_clean_records)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Strings that are semantically equivalent to null
_NULL_STRINGS = frozenset({
    "", "n/a", "na", "none", "null", "nil", "-", "--", "unknown",
    "not set", "not available", "undefined", "#n/a", "0000-00-00",
})

# Field coverage thresholds
COVERAGE_USABLE = 0.70       # ≥70% non-null → usable
COVERAGE_LOW = 0.30          # 30–70% → low_coverage (use with caution)
# <30% → too_sparse (impute or drop)


# ---------------------------------------------------------------------------
# Primitive coercions
# ---------------------------------------------------------------------------

def safe_float(value: Any) -> Optional[float]:
    """Coerce value to float. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if s in _NULL_STRINGS:
        return None
    # Strip currency symbols and commas
    s = re.sub(r"[$€£,\s]", "", s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def safe_int(value: Any) -> Optional[int]:
    """Coerce value to int. Returns None on failure."""
    f = safe_float(value)
    return int(f) if f is not None else None


def safe_date(value: Any) -> Optional[str]:
    """Parse a date/datetime value to ISO date string (YYYY-MM-DD).

    Accepts:
      - ISO 8601 strings (with or without time / timezone)
      - Unix timestamps in milliseconds (HubSpot default)
      - Unix timestamps in seconds
    Returns None on failure.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _NULL_STRINGS:
        return None

    # Unix ms (HubSpot stores dates as ms since epoch)
    if re.match(r"^\d{13}$", s):
        try:
            dt = datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass

    # Unix seconds (10-digit integer)
    if re.match(r"^\d{10}$", s):
        try:
            dt = datetime.fromtimestamp(int(s), tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass

    # ISO 8601 / common formats
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
    ):
        try:
            dt = datetime.strptime(s[:len(fmt) + 5], fmt)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue

    # Last resort: try dateutil if available
    try:
        from dateutil import parser as _dp
        return _dp.parse(s).strftime("%Y-%m-%d")
    except Exception:
        pass

    logger.debug("safe_date: could not parse %r", s)
    return None


def clean_string(value: Any) -> Optional[str]:
    """Strip whitespace and return None for placeholder strings."""
    if value is None:
        return None
    s = str(value).strip()
    return None if s.lower() in _NULL_STRINGS else s


def days_since(date_str: Optional[str]) -> Optional[int]:
    """Return number of days from date_str to today. None if unparseable."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        delta = datetime.now(tz=timezone.utc) - dt
        return max(0, delta.days)
    except (ValueError, TypeError):
        return None


def days_until(date_str: Optional[str]) -> Optional[int]:
    """Return number of days from today to date_str. Negative = past."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        delta = dt - datetime.now(tz=timezone.utc)
        return delta.days
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------

def normalize_record(
    raw_props: Dict[str, Any],
    schema_mapping: Any,  # SchemaMapping from schema_mapper — avoid circular import
    business_mode: str = "saas",
) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize a single HubSpot company property dict into a clean record.

    Args:
        raw_props:      Raw property dict from HubSpot API.
        schema_mapping: SchemaMapping instance from schema_mapper.discover().
        business_mode:  "saas" or "services".

    Returns:
        (clean_record, warnings) where warnings is a list of field-level issues.
    """
    warnings: List[str] = []
    out: Dict[str, Any] = {}

    def _get(canonical: str) -> Any:
        raw_name = schema_mapping.get(canonical)
        return raw_props.get(raw_name) if raw_name else None

    # ARR / revenue
    arr_raw = _get("arr")
    arr = safe_float(arr_raw)
    if arr is not None:
        if schema_mapping.mrr_scale("arr"):
            arr = arr * 12
        if arr < 0:
            warnings.append(f"arr: negative value {arr} set to None")
            arr = None
    out["arr"] = arr

    # Company size
    emp = safe_int(_get("company_size_employees"))
    if emp is not None:
        if emp < 0:
            warnings.append(f"company_size_employees: negative {emp} ignored")
            emp = None
        else:
            # Bucket into string categories used by the model
            if emp < 50:
                out["company_size"] = "1-50"
            elif emp < 200:
                out["company_size"] = "51-200"
            elif emp <= 1000:
                out["company_size"] = "201-1000"
            else:
                out["company_size"] = "1001+"
    elif raw_size := clean_string(raw_props.get("company_size")):
        out["company_size"] = raw_size
    else:
        out["company_size"] = None

    # Renewal / contract date
    renewal_date = safe_date(_get("renewal_date"))
    out["renewal_date"] = renewal_date
    out["days_until_renewal"] = days_until(renewal_date) if renewal_date else None

    # Estimate contract_months_remaining from days_until_renewal
    dur = out["days_until_renewal"]
    out["contract_months_remaining"] = round(dur / 30.44, 1) if dur is not None else None

    # Industry
    out["industry"] = clean_string(_get("industry"))

    # Plan (SaaS mode)
    if business_mode == "saas":
        out["plan"] = clean_string(_get("plan"))

    # NPS (SaaS mode)
    if business_mode == "saas":
        nps = safe_float(_get("nps_score"))
        if nps is not None and not (0 <= nps <= 10):
            warnings.append(f"nps_score: out-of-range {nps} clipped")
            nps = max(0.0, min(10.0, nps))
        out["nps_score"] = nps

    # Last activity date (both modes)
    last_activity = safe_date(_get("last_activity_date"))
    out["days_since_last_activity"] = days_since(last_activity)

    if business_mode == "saas":
        # Map last_activity → days_since_last_login if no better field
        out["days_since_last_login"] = out["days_since_last_activity"]
    else:
        # Services: days_since_last_activity is the primary recency signal
        out["days_since_last_login"] = out["days_since_last_activity"]

    return out, warnings


def normalize_record_safe(
    raw_props: Dict[str, Any],
    schema_mapping: Any,
    business_mode: str = "saas",
    record_id: str = "",
) -> Optional[Tuple[Dict[str, Any], List[str]]]:
    """Wrapper that catches all exceptions so one bad record never breaks a batch."""
    try:
        return normalize_record(raw_props, schema_mapping, business_mode)
    except Exception as exc:
        logger.warning("normalization: record %s failed (%s) — skipped", record_id, exc)
        return None


# ---------------------------------------------------------------------------
# Data quality audit
# ---------------------------------------------------------------------------

def audit_records(
    records: List[Dict[str, Any]],
    fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compute per-field coverage and eligibility for a list of clean records.

    Args:
        records: List of normalized records (from normalize_record).
        fields:  If provided, audit only these fields; otherwise auto-detect.

    Returns:
        Dict with keys:
          n_records, field_stats, usable_fields, low_coverage_fields,
          sparse_fields, overall_coverage_pct
    """
    if not records:
        return {
            "n_records": 0,
            "field_stats": {},
            "usable_fields": [],
            "low_coverage_fields": [],
            "sparse_fields": [],
            "overall_coverage_pct": 0.0,
        }

    n = len(records)
    all_fields = fields or sorted({k for r in records for k in r})

    field_stats: Dict[str, Any] = {}
    usable: List[str] = []
    low: List[str] = []
    sparse: List[str] = []

    for field in all_fields:
        non_null = sum(
            1 for r in records
            if r.get(field) is not None and r.get(field) != ""
        )
        coverage = non_null / n

        if coverage >= COVERAGE_USABLE:
            eligibility = "usable"
            usable.append(field)
        elif coverage >= COVERAGE_LOW:
            eligibility = "low_coverage"
            low.append(field)
        else:
            eligibility = "too_sparse"
            sparse.append(field)

        field_stats[field] = {
            "coverage_pct": round(coverage * 100, 1),
            "non_null": non_null,
            "total": n,
            "eligibility": eligibility,
        }

    overall = (
        sum(s["coverage_pct"] for s in field_stats.values()) / len(field_stats)
        if field_stats else 0.0
    )

    return {
        "n_records": n,
        "field_stats": field_stats,
        "usable_fields": usable,
        "low_coverage_fields": low,
        "sparse_fields": sparse,
        "overall_coverage_pct": round(overall, 1),
    }

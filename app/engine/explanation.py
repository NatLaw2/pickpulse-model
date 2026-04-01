"""Schema-agnostic explanation text engine.

Converts enriched SHAP driver data (value, retained_mean, churned_mean,
direction) into business-readable comparison language and portfolio narratives.

Design constraints:
  1. No feature name hardcoding — format type is inferred from name patterns.
  2. No domain assumptions — works for SaaS, services, manufacturing, healthcare.
  3. Binary/OHE columns are detected and skipped (no meaningful comparison).
  4. Gracefully returns None when data is insufficient.
  5. Portfolio narrative is deterministic — no LLM dependency.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Format type inference
# ---------------------------------------------------------------------------

def infer_format_type(feature: str) -> str:
    """Infer display format from feature name patterns.

    Returns one of: 'days', 'count', 'score', 'currency', 'pct', 'number'
    """
    f = feature.lower()
    if re.search(r'\bdays\b', f):
        return 'days'
    if re.search(r'(count|tickets|seats|logins|deals|contacts|licenses|users)', f):
        return 'count'
    if re.search(r'(score|nps|rating|csat)', f):
        return 'score'
    if re.search(r'(arr|revenue|acv|mrr|contract_value)\b', f) and 'tier' not in f:
        return 'currency'
    if re.search(r'(pct|rate|ratio|fraction)', f):
        return 'pct'
    return 'number'


def format_value(value: float, format_type: str) -> str:
    """Format a numeric value for display using the inferred format type."""
    if format_type == 'days':
        v = int(round(value))
        return f"{v} day{'s' if v != 1 else ''}"
    if format_type == 'count':
        return str(int(round(value)))
    if format_type == 'score':
        return f"{value:.1f}"
    if format_type == 'currency':
        if value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"${value / 1_000:.0f}k"
        return f"${value:.0f}"
    if format_type == 'pct':
        return f"{value:.1f}%"
    return f"{value:.1f}"


# ---------------------------------------------------------------------------
# Comparison phrase helpers
# ---------------------------------------------------------------------------

_ABOVE_WORDS: Dict[str, str] = {
    'days': 'longer than', 'count': 'more than', 'score': 'higher than',
    'currency': 'above', 'pct': 'above', 'number': 'above',
}
_BELOW_WORDS: Dict[str, str] = {
    'days': 'shorter than', 'count': 'fewer than', 'score': 'lower than',
    'currency': 'below', 'pct': 'below', 'number': 'below',
}


def _vs_retained_phrase(value: float, retained_mean: float, fmt: str) -> str:
    """Describe how value compares to retained baseline."""
    if retained_mean == 0:
        return "above the retained average" if value > 0 else "near the retained average"

    is_above = value > retained_mean
    ratio = (value / retained_mean) if is_above else (retained_mean / value)

    direction = _ABOVE_WORDS.get(fmt, 'above') if is_above else _BELOW_WORDS.get(fmt, 'below')

    if ratio >= 4.0:
        return f"{ratio:.1f}× {direction}"
    if ratio >= 2.0:
        return f"{ratio:.1f}× {direction}"
    if ratio >= 1.4:
        return f"significantly {direction}"
    if ratio >= 1.1:
        return direction
    return "near the retained average"


def _vs_churned_clause(
    value: float,
    retained_mean: float,
    churned_mean: float,
    churned_formatted: str,
) -> Optional[str]:
    """Generate an optional clause describing proximity to churned baseline."""
    total_range = abs(churned_mean - retained_mean)
    if total_range < 0.01:
        return None  # Baselines indistinguishable — skip

    distance_to_churned = abs(value - churned_mean)
    closeness = 1.0 - min(1.0, distance_to_churned / total_range)

    if closeness >= 0.8:
        return f"at levels similar to churned accounts (avg {churned_formatted})"
    if closeness >= 0.5:
        return f"approaching churned accounts (avg {churned_formatted})"
    if closeness >= 0.25:
        return f"closer to churned accounts (avg {churned_formatted})"
    return None  # Far from churned baseline — omit clause


# ---------------------------------------------------------------------------
# Public: account-level explanation text
# ---------------------------------------------------------------------------

def build_explanation_text(
    feature: str,
    value: Optional[float],
    retained_mean: Optional[float],
    churned_mean: Optional[float],
    direction: str,
) -> Optional[str]:
    """Generate comparison explanation text for a single SHAP driver.

    Args:
        feature:       Raw feature name (used for format inference).
        value:         This account's actual feature value.
        retained_mean: Mean value for retained accounts from training data.
        churned_mean:  Mean value for churned accounts from training data.
        direction:     "increases_risk" or "decreases_risk".

    Returns:
        Human-readable explanation string, or None if data is insufficient.
    """
    # Need valid value and at least one baseline
    if value is None or retained_mean is None:
        return None
    if not all(isinstance(v, (int, float)) for v in [value, retained_mean]):
        return None
    # NaN / inf guard
    import math
    if not all(math.isfinite(v) for v in [value, retained_mean]):
        return None

    # Skip binary/categorical features (retained_mean in [0,1] range suggests OHE or flag)
    if 0.0 <= retained_mean <= 1.0 and (churned_mean is None or 0.0 <= churned_mean <= 1.0):
        return None

    fmt = infer_format_type(feature)
    val_str = format_value(value, fmt)
    ret_str = format_value(retained_mean, fmt)

    vs_retained = _vs_retained_phrase(value, retained_mean, fmt)

    # Build churned clause if we have the baseline and it adds context
    churned_clause = None
    if churned_mean is not None and math.isfinite(churned_mean):
        churn_str = format_value(churned_mean, fmt)
        churned_clause = _vs_churned_clause(value, retained_mean, churned_mean, churn_str)

    if churned_clause:
        return f"{val_str} — {vs_retained} retained accounts (avg {ret_str}), {churned_clause}"
    return f"{val_str} — {vs_retained} retained accounts (avg {ret_str})"


# ---------------------------------------------------------------------------
# Public: portfolio narrative
# ---------------------------------------------------------------------------

def build_portfolio_narrative(
    arr_weighted_drivers: List[Dict[str, Any]],
    n_accounts: int,
) -> Dict[str, str]:
    """Generate deterministic portfolio-level narrative from aggregated SHAP.

    Args:
        arr_weighted_drivers: Sorted list of portfolio drivers from aggregate_portfolio_shap().
                              Each must have: label, direction, pct_accounts_positive,
                              n_accounts_material, pct_accounts_material.
        n_accounts:           Total accounts scored in this run.

    Returns:
        {
          "risk_summary":       bullets for risk-increasing drivers,
          "protective_summary": bullets for risk-decreasing drivers,
        }
    """
    risk_bullets: List[str] = []
    protective_bullets: List[str] = []

    for d in arr_weighted_drivers:
        label = d.get("label") or d.get("feature", "Unknown signal")
        direction = d.get("direction", "increases_risk")
        pct_pos = d.get("pct_accounts_positive", 0.5)
        pct_mat = d.get("pct_accounts_material", 0.0)
        n_mat = d.get("n_accounts_material", 0)

        if direction == "increases_risk":
            if len(risk_bullets) >= 3:
                continue
            pct_affected = round(pct_pos * 100)
            if pct_mat >= 0.75:
                bullet = (
                    f"{label} — dominant risk signal across {pct_affected}% of "
                    f"scored accounts ({n_mat} of {n_accounts})"
                )
            elif pct_mat >= 0.40:
                bullet = (
                    f"{label} — elevated in {n_mat} of {n_accounts} accounts, "
                    f"driving {pct_affected}% of portfolio risk weight"
                )
            elif n_mat > 0:
                bullet = (
                    f"{label} — concentrated risk signal in {n_mat} account"
                    f"{'s' if n_mat != 1 else ''}"
                )
            else:
                bullet = f"{label} — contributing to portfolio risk"
            risk_bullets.append(bullet)

        else:  # decreases_risk
            if len(protective_bullets) >= 2:
                continue
            pct_protected = round((1.0 - pct_pos) * 100)
            bullet = (
                f"{label} — protective signal holding across "
                f"{pct_protected}% of accounts"
            )
            protective_bullets.append(bullet)

    return {
        "risk_summary": risk_bullets,
        "protective_summary": protective_bullets,
    }

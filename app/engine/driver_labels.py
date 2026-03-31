"""LLM-powered feature label generation for per-account risk drivers.

Converts raw model feature names (e.g. "days_since_last_login") into
business-readable labels (e.g. "No recent engagement") suitable for
presentation to a CRO or Customer Success leader.

Design:
  - Non-blocking: LLM failure always falls back to a rule-based cleaner.
  - Batch-efficient: one LLM call per prediction batch (unique features only).
  - Schema-agnostic: prompt never assumes SaaS, logins, or product-specific concepts.
  - Raw names always preserved: labels are additive, never replace feature identity.

Usage:
    labeled = label_drivers(drivers, context={"company_name": "Acme", "risk_pct": 72})
    # labeled[0] == {"feature": "days_since_last_login",
    #                "label": "No recent engagement",
    #                "shap_value": 0.18, "direction": "increases_risk"}
"""
from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule-based fallback cleaner
# ---------------------------------------------------------------------------

# OHE suffix patterns that should be stripped or reformatted
_OHE_STRIP = re.compile(r"^(.+?)_(low_value|mid_value|high_value|__missing__)$")
_OHE_STATUS = re.compile(r"^(.+?)_([a-z_]+)$")

# Rename map for known awkward raw names → cleaner versions before title-casing
_RAW_RENAMES: Dict[str, str] = {
    "days_since_last_login":    "days since last activity",
    "days_since_last_activity": "days since last activity",
    "monthly_logins":           "activity frequency",
    "arr_tier_low_value":       "lower-value account",
    "arr_tier_mid_value":       "mid-value account",
    "arr_tier_high_value":      "higher-value account",
    "auto_renew_flag":          "auto-renewal setting",
    "contract_months_remaining":"contract time remaining",
    "renewal_status_cancelled": "cancelled status",
    "renewal_status_in_notice": "cancellation notice",
    "renewal_status_unknown":   "unknown renewal status",
    "renewal_status_active":    "active renewal",
}


def clean_feature_name(raw: str) -> str:
    """Convert a raw feature name to a human-readable label without LLM.

    Handles OHE suffixes, snake_case, and known awkward names.
    """
    if raw in _RAW_RENAMES:
        return _RAW_RENAMES[raw].title()

    # Strip common OHE suffixes from arr_tier
    m = _OHE_STRIP.match(raw)
    if m:
        base = m.group(1).replace("_", " ")
        tier = m.group(2).replace("_", " ")
        return f"{base.title()} ({tier})"

    # Generic: snake_case → Title Case
    return raw.replace("_", " ").title()


# ---------------------------------------------------------------------------
# LLM labeling
# ---------------------------------------------------------------------------

def _build_prompt(pairs: List[Dict[str, str]]) -> str:
    """Build the LLM prompt for a list of (feature, direction) pairs."""
    items = json.dumps(pairs, indent=2)
    return f"""You are labeling predictive risk factors for a revenue intelligence platform used by CROs and Customer Success leaders.

For each item below, write a concise (2–5 words) business-readable label that:
- Describes what the feature represents, framed by its direction
- Reads naturally to a senior revenue leader — no jargon, no product-specific assumptions
- Does NOT use words like "factor", "signal", "metric", "score", "flag", or "level"
- Does NOT assume the customer uses software (avoid "logins", "sessions", "users")

direction "increases_risk" → frame the label as a concern or warning sign
direction "decreases_risk" → frame the label as a positive or stabilizing indicator

Items:
{items}

Return ONLY a valid JSON array: [{{"feature": "...", "label": "..."}}]
No markdown, no explanation, no extra keys."""


@lru_cache(maxsize=256)
def _label_pair_cached(feature: str, direction: str) -> str:
    """Cache wrapper — not called directly; used to persist batch results."""
    return clean_feature_name(feature)  # filled in by batch after LLM call


def _call_llm_batch(pairs: List[Dict[str, str]]) -> Dict[str, str]:
    """Call GPT-4o-mini with all unique (feature, direction) pairs.

    Returns dict: (feature, direction) key → label string.
    Falls back to clean_feature_name on any error.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        prompt = _build_prompt(pairs)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
            timeout=8,
        )
        raw = resp.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()

        labeled = json.loads(raw)
        return {item["feature"]: item["label"] for item in labeled}

    except Exception as exc:
        logger.warning("driver_labels: LLM call failed (%s) — using fallback", exc)
        return {}


def label_drivers(
    drivers: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
) -> List[Dict[str, Any]]:
    """Add human-readable labels to a list of SHAP drivers.

    This is the main entry point. Mutates a *copy* — originals unchanged.

    Args:
        drivers: List of driver dicts from extract_top_drivers().
                 Each has: feature, shap_value, direction.
        context: Optional dict with account context (unused for now, reserved
                 for future per-account prompt enrichment).
        use_llm: If False, skip LLM and use rule-based cleaner only.
                 Useful for tests and offline environments.

    Returns:
        New list of dicts with the original fields plus "label".
    """
    if not drivers:
        return []

    # Collect unique (feature, direction) pairs for a single LLM call
    unique_pairs = list({
        (d["feature"], d["direction"])
        for d in drivers
    })

    llm_labels: Dict[str, str] = {}
    if use_llm:
        pairs_for_llm = [
            {"feature": f, "direction": dir_}
            for f, dir_ in unique_pairs
        ]
        llm_labels = _call_llm_batch(pairs_for_llm)

    result = []
    for d in drivers:
        label = llm_labels.get(d["feature"]) or clean_feature_name(d["feature"])
        result.append({**d, "label": label})

    return result


def label_drivers_batch(
    all_drivers: List[List[Dict[str, Any]]],
    use_llm: bool = True,
) -> List[List[Dict[str, Any]]]:
    """Label drivers for a full prediction batch (all accounts) with one LLM call.

    More efficient than calling label_drivers() per account — deduplicates
    features across all accounts and makes a single API call.

    Args:
        all_drivers: List of per-account driver lists (from result["top_drivers"]).
        use_llm: If False, use rule-based cleaner only.

    Returns:
        List of labeled per-account driver lists.
    """
    if not any(all_drivers):
        return all_drivers

    # Collect unique (feature, direction) pairs across all accounts
    unique_pairs: set = set()
    for drivers in all_drivers:
        for d in drivers:
            unique_pairs.add((d["feature"], d["direction"]))

    llm_labels: Dict[str, str] = {}
    if use_llm and unique_pairs:
        pairs_for_llm = [
            {"feature": f, "direction": dir_}
            for f, dir_ in unique_pairs
        ]
        llm_labels = _call_llm_batch(pairs_for_llm)

    labeled_batch = []
    for drivers in all_drivers:
        labeled = []
        for d in drivers:
            label = llm_labels.get(d["feature"]) or clean_feature_name(d["feature"])
            labeled.append({**d, "label": label})
        labeled_batch.append(labeled)

    return labeled_batch

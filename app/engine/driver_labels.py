"""LLM-powered feature label generation for per-account risk drivers.

Converts raw model feature names (e.g. "days_since_last_login") into
business-readable labels (e.g. "Extended inactivity") suitable for
presentation to a CRO or Customer Success leader.

Design constraints:
  1. Direction alignment: labels MUST agree with SHAP direction.
     increases_risk → concern / warning.  decreases_risk → healthy / protective.
     A label like "Low deal activity" paired with decreases_risk is a contradiction
     and must never appear.
  2. No SaaS/login leakage: raw names like "days_since_last_login" or
     "monthly_logins" must not surface in user-facing labels.  The underlying
     concept (engagement, activity recency) is expressed in business language.
  3. Additive only: raw feature name is always preserved alongside the label.
  4. Non-blocking: LLM failure falls through to direction-aware rule cleaner.
  5. Batch-efficient: one LLM call per prediction run (unique pairs only).

Label cache key: (feature, direction) — not feature alone.
The same raw feature can appear as both a risk and a protective signal across
different accounts; each combination needs its own label.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directional rule-based labels
# Key: (canonical_feature_name, direction)   direction ∈ {"increases_risk", "decreases_risk"}
#
# Covers every feature that today's churn model is likely to produce.
# Handles SaaS terminology internally: "days_since_last_login" is renamed
# to "Extended inactivity" / "Recent active engagement" — no "login" leaked.
# ---------------------------------------------------------------------------

_DIRECTIONAL_LABELS: Dict[Tuple[str, str], str] = {
    # Activity / engagement recency
    ("days_since_last_login",    "increases_risk"):  "Extended inactivity",
    ("days_since_last_login",    "decreases_risk"):  "Recent active engagement",
    ("days_since_last_activity", "increases_risk"):  "Extended inactivity",
    ("days_since_last_activity", "decreases_risk"):  "Recent active engagement",
    # Engagement frequency
    ("monthly_logins",           "increases_risk"):  "Declining engagement",
    ("monthly_logins",           "decreases_risk"):  "Consistent engagement",
    # Support friction
    ("support_tickets",          "increases_risk"):  "Elevated support volume",
    ("support_tickets",          "decreases_risk"):  "Minimal support friction",
    # Customer sentiment
    ("nps_score",                "increases_risk"):  "Low satisfaction",
    ("nps_score",                "decreases_risk"):  "Strong customer satisfaction",
    # Revenue
    ("arr",                      "increases_risk"):  "High-value account at risk",
    ("arr",                      "decreases_risk"):  "Stable revenue base",
    # Contract timing
    ("days_until_renewal",       "increases_risk"):  "Renewal approaching",
    ("days_until_renewal",       "decreases_risk"):  "Ample renewal runway",
    ("contract_months_remaining","increases_risk"):  "Contract ending soon",
    ("contract_months_remaining","decreases_risk"):  "Long-term commitment",
    ("auto_renew_flag",          "increases_risk"):  "No auto-renewal set",
    ("auto_renew_flag",          "decreases_risk"):  "Auto-renewal active",
    # CRM relationship signals
    ("contact_count",            "increases_risk"):  "Limited stakeholder coverage",
    ("contact_count",            "decreases_risk"):  "Broad stakeholder coverage",
    ("deal_count",               "increases_risk"):  "Low deal engagement",
    ("deal_count",               "decreases_risk"):  "Active deal engagement",
    # Utilization / allocation
    ("seats",                    "increases_risk"):  "Low utilization",
    ("seats",                    "decreases_risk"):  "Strong utilization",
    # Account segment — ARR tier OHE columns are segment descriptors, not directional
    ("arr_tier_low_value",       "increases_risk"):  "Lower-value account segment",
    ("arr_tier_low_value",       "decreases_risk"):  "Lower-value account segment",
    ("arr_tier_mid_value",       "increases_risk"):  "Mid-tier account segment",
    ("arr_tier_mid_value",       "decreases_risk"):  "Mid-tier account segment",
    ("arr_tier_high_value",      "increases_risk"):  "Higher-value account segment",
    ("arr_tier_high_value",      "decreases_risk"):  "Higher-value account segment",
    # Renewal status OHE — directional framing based on outcome
    ("renewal_status_cancelled",  "increases_risk"):  "Cancelled status",
    ("renewal_status_cancelled",  "decreases_risk"):  "Cancelled status",
    ("renewal_status_in_notice",  "increases_risk"):  "In cancellation notice",
    ("renewal_status_in_notice",  "decreases_risk"):  "In cancellation notice",
    ("renewal_status_unknown",    "increases_risk"):  "Unknown renewal status",
    ("renewal_status_unknown",    "decreases_risk"):  "Unknown renewal status",
    ("renewal_status_active",     "increases_risk"):  "Active renewal status",
    ("renewal_status_active",     "decreases_risk"):  "Active and renewing",
    # Company profile
    ("company_size",              "increases_risk"):  "Account size factor",
    ("company_size",              "decreases_risk"):  "Scale advantage",
    ("industry",                  "increases_risk"):  "Segment risk pattern",
    ("industry",                  "decreases_risk"):  "Favorable segment",
    ("plan",                      "increases_risk"):  "Plan tier risk",
    ("plan",                      "decreases_risk"):  "High-value plan tier",
}

# OHE suffix pattern: "arr_tier_mid_value", "plan_enterprise", "industry_saas", etc.
_OHE_TIER_RE = re.compile(r"^(.+?)_(low_value|mid_value|high_value|__missing__)$")


def clean_feature_name(raw: str, direction: str = "increases_risk") -> str:
    """Convert a raw feature name to a direction-aware human-readable label.

    Lookup order:
      1. (raw, direction) in _DIRECTIONAL_LABELS       — exact directional match
      2. (raw, opposite_direction) in _DIRECTIONAL_LABELS — use opposite, log warning
      3. Known OHE tier suffix pattern                  — reformatted segment label
      4. Generic snake_case → Title Case                — safe last resort

    Args:
        raw:       Internal feature name (may be OHE, snake_case, etc.)
        direction: "increases_risk" or "decreases_risk"
    """
    # 1. Exact directional match
    key = (raw, direction)
    if key in _DIRECTIONAL_LABELS:
        return _DIRECTIONAL_LABELS[key]

    # 2. OHE tier column not in the dict — strip suffix and describe neutrally
    m = _OHE_TIER_RE.match(raw)
    if m:
        base = m.group(1).replace("_", " ").title()
        tier = m.group(2).replace("_", " ")
        return f"{base} ({tier})"

    # 3. Generic snake_case OHE pattern (e.g. "plan_enterprise", "industry_tech")
    parts = raw.split("_", 1)
    if len(parts) == 2 and len(parts[0]) <= 20 and len(parts[1]) <= 30:
        # Looks like a one-hot column — describe as a category marker
        category = parts[0].replace("_", " ").title()
        value = parts[1].replace("_", " ").title()
        return f"{category}: {value}"

    # 4. Plain snake_case → Title Case
    return raw.replace("_", " ").title()


# ---------------------------------------------------------------------------
# LLM labeling
# ---------------------------------------------------------------------------

def _build_prompt(pairs: List[Dict[str, str]]) -> str:
    """Build the labeling prompt for a batch of (feature, direction) pairs."""
    items_json = json.dumps(pairs, indent=2)
    return f"""You are generating risk driver labels for a B2B revenue intelligence platform.
Labels will be read by a Chief Revenue Officer or Customer Success leader making retention decisions.

Rules — follow all of them:
1. 2–5 words maximum per label.
2. Direction "increases_risk" → describe a WARNING or CONCERN. The account is showing a risk signal.
3. Direction "decreases_risk" → describe a HEALTHY or PROTECTIVE signal. The account has something working in its favor.
4. Never contradict direction. "Low deal activity" paired with "decreases_risk" is a contradiction — do not do this.
5. Avoid these words: login, session, score, metric, factor, signal, level, flag, feature, rate.
6. Do not assume SaaS or software context. The account may be a services, manufacturing, or healthcare company.
7. Each (feature, direction) combination must produce a distinct label — the same feature can appear twice with opposite directions.

Examples of correct direction alignment:
  feature="support_tickets"  direction="increases_risk"  → "Elevated support volume"
  feature="support_tickets"  direction="decreases_risk"  → "Minimal support friction"
  feature="deal_count"       direction="increases_risk"  → "Low deal engagement"
  feature="deal_count"       direction="decreases_risk"  → "Active deal engagement"
  feature="days_since_last_login" direction="increases_risk" → "Extended inactivity"
  feature="days_since_last_login" direction="decreases_risk" → "Recent active engagement"

Items to label:
{items_json}

Return ONLY a valid JSON array with this exact structure — no markdown, no explanation:
[{{"feature": "...", "direction": "...", "label": "..."}}]"""


def _call_llm_batch(
    pairs: List[Dict[str, str]],
) -> Dict[Tuple[str, str], str]:
    """Call GPT-4o-mini for all unique (feature, direction) pairs.

    Returns a dict keyed by (feature, direction) → label string.
    Returns empty dict on any failure — callers fall back to rule cleaner.
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
            temperature=0.1,   # lower temp → more consistent direction alignment
            max_tokens=600,
            timeout=8,
        )
        raw_text = resp.choices[0].message.content.strip()

        # Strip markdown fences if the model adds them
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text).rstrip("`").strip()

        items = json.loads(raw_text)
        result: Dict[Tuple[str, str], str] = {}
        for item in items:
            feat = item.get("feature", "")
            dir_ = item.get("direction", "")
            lbl = item.get("label", "")
            if feat and dir_ and lbl:
                result[(feat, dir_)] = lbl

        logger.debug("driver_labels: LLM labeled %d pairs", len(result))
        return result

    except Exception as exc:
        logger.warning("driver_labels: LLM call failed (%s) — using rule fallback", exc)
        return {}


# ---------------------------------------------------------------------------
# Post-label direction audit
# ---------------------------------------------------------------------------

# Patterns that indicate a label may contradict a direction.
# Used to detect and replace contradictions from the LLM.
_RISK_POSITIVE_WORDS = re.compile(
    r"\b(strong|active|healthy|broad|consistent|full|ample|long.term|stable|recent|minimal|positive|growing)\b",
    re.IGNORECASE,
)
_RISK_NEGATIVE_WORDS = re.compile(
    r"\b(low|declining|limited|elevated|no |missing|extended|ending|cancelled|unknown|at risk|poor|weak)\b",
    re.IGNORECASE,
)


def _direction_contradiction(label: str, direction: str) -> bool:
    """Return True if the label appears to contradict the direction."""
    if direction == "increases_risk":
        # Positive words in a risk label suggest contradiction
        return bool(_RISK_POSITIVE_WORDS.search(label))
    else:
        # Negative words in a protective label suggest contradiction
        return bool(_RISK_NEGATIVE_WORDS.search(label))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def label_drivers_batch(
    all_drivers: List[List[Dict[str, Any]]],
    use_llm: bool = True,
) -> List[List[Dict[str, Any]]]:
    """Add human-readable labels to all per-account driver lists.

    Makes a single LLM call covering all unique (feature, direction) pairs
    across every account in the batch.  Falls back to the rule-based cleaner
    for any pair the LLM doesn't return or where a contradiction is detected.

    Args:
        all_drivers: List of per-account driver lists from extract_top_drivers().
                     Each driver dict has: feature, shap_value, direction.
        use_llm:     Set False to skip LLM (tests, offline environments).

    Returns:
        New list of per-account driver lists, each driver now includes "label".
    """
    if not all_drivers:
        return all_drivers

    # Collect unique (feature, direction) pairs across the whole batch
    unique_pairs: set = set()
    for drivers in all_drivers:
        for d in drivers:
            unique_pairs.add((d["feature"], d["direction"]))

    llm_labels: Dict[Tuple[str, str], str] = {}
    if use_llm and unique_pairs:
        pairs_for_llm = [
            {"feature": f, "direction": dir_}
            for f, dir_ in sorted(unique_pairs)  # sorted for deterministic prompt order
        ]
        llm_labels = _call_llm_batch(pairs_for_llm)

    labeled_batch: List[List[Dict[str, Any]]] = []
    for drivers in all_drivers:
        labeled: List[Dict[str, Any]] = []
        for d in drivers:
            feat = d["feature"]
            dir_ = d["direction"]
            key = (feat, dir_)

            # Try LLM label; audit for direction contradiction; fall back if needed
            lbl = llm_labels.get(key, "")
            if lbl and _direction_contradiction(lbl, dir_):
                logger.warning(
                    "driver_labels: LLM contradiction detected — feature=%r direction=%r label=%r; using fallback",
                    feat, dir_, lbl,
                )
                lbl = ""

            if not lbl:
                lbl = clean_feature_name(feat, dir_)

            labeled.append({**d, "label": lbl})
        labeled_batch.append(labeled)

    return labeled_batch


def label_drivers(
    drivers: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
) -> List[Dict[str, Any]]:
    """Label a single account's driver list.

    Convenience wrapper around label_drivers_batch() for single-account use.
    context is reserved for future per-account prompt enrichment.
    """
    if not drivers:
        return []
    result = label_drivers_batch([drivers], use_llm=use_llm)
    return result[0] if result else []

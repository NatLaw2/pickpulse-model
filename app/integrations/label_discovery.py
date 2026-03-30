"""Label source discovery — identifies what field indicates churn/non-renewal
in an arbitrary HubSpot portal without prior knowledge of the schema.

Design principles:
  - No API calls here. Takes pre-fetched metadata so it's fast and testable.
  - Generalizes to any HubSpot portal — no company-specific assumptions.
  - Returns a ranked list of candidates; the auditor makes the final call.

Three scan paths:
  A. Company properties — bool/enumeration with outcome vocabulary
  B. Deal pipelines — renewal/retention pipeline with closed won/lost stages
  C. Lifecycle stages — terminal negative lifecycle stage in company property

Usage:
    props = connector.pull_company_properties()
    pipelines = connector.pull_deal_pipelines()
    candidates = discover_candidates(props, pipelines)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# Terms in a field name/label that indicate a *churned/lost* outcome
CHURN_TERMS: Set[str] = {
    "churn", "churned", "cancel", "cancelled", "canceled", "cancellation",
    "inactive", "lost", "former", "expired", "ended", "closed",
    "non_renewal", "nonrenewal", "non-renewal", "terminated", "termination",
    "offboarded", "off-boarded", "attrition", "departed", "lapsed",
}

# Terms that indicate a *retained/active* outcome
RETAINED_TERMS: Set[str] = {
    "active", "retained", "renewed", "won", "current", "subscribed",
    "customer", "healthy", "live", "engaged",
}

# Terms that suggest a pipeline is about renewals (not new business)
RENEWAL_PIPELINE_TERMS: Set[str] = {
    "renewal", "renew", "retain", "retention", "upsell", "expansion",
    "existing", "re-sign", "resign", "extend", "extension",
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class LabelSourceCandidate:
    type: str                    # "property" | "deal" | "lifecycle"
    raw_field: str               # HubSpot internal field/pipeline name
    display_name: str            # Human-readable label from HubSpot
    positive_values: List[str]   # Values indicating churned/non-renewed (outcome=1)
    negative_values: List[str]   # Values indicating retained/renewed (outcome=0)
    confidence: float            # 0.0–1.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["confidence"] = round(d["confidence"], 3)
        return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Lowercase, replace separators with space for vocabulary matching."""
    return re.sub(r"[_\-\s]+", " ", s.lower()).strip()


def _has_term(text: str, terms: Set[str]) -> bool:
    n = _normalize(text)
    return any(t in n for t in terms)


def _option_values(prop: Dict[str, Any]) -> List[str]:
    """Return all option value strings (lowercase) for an enumeration property."""
    return [
        o.get("value", "").lower()
        for o in prop.get("options", [])
    ]


def _option_labels(prop: Dict[str, Any]) -> List[str]:
    return [
        o.get("label", "").lower()
        for o in prop.get("options", [])
    ]


def _find_matching_options(prop: Dict[str, Any], terms: Set[str]) -> List[str]:
    """Return the raw option values whose value or label matches any term."""
    matches = []
    for opt in prop.get("options", []):
        v = opt.get("value", "").lower()
        lbl = opt.get("label", "").lower()
        if _has_term(v, terms) or _has_term(lbl, terms):
            matches.append(opt.get("value", v))
    return matches


# ---------------------------------------------------------------------------
# Path A: Company property scan
# ---------------------------------------------------------------------------

def scan_company_properties(
    props: List[Dict[str, Any]],
) -> List[LabelSourceCandidate]:
    """Scan company property metadata for fields that might indicate churn outcome.

    Args:
        props: Raw results from GET /crm/v3/properties/companies

    Returns:
        List of LabelSourceCandidate sorted by confidence descending.
    """
    candidates: List[LabelSourceCandidate] = []

    for prop in props:
        name = prop.get("name", "")
        label = prop.get("label", "")
        ptype = prop.get("type", "")

        # Skip PickPulse's own properties and internal HubSpot system fields
        if name.startswith("pickpulse_") or name.startswith("hs_"):
            continue

        name_has_churn = _has_term(name, CHURN_TERMS)
        name_has_retained = _has_term(name, RETAINED_TERMS)
        label_has_churn = _has_term(label, CHURN_TERMS)
        label_has_retained = _has_term(label, RETAINED_TERMS)

        if ptype == "bool":
            # A boolean named "churned" or "is_churned" is the gold standard
            if name_has_churn or label_has_churn:
                # churned=true → positive outcome; churned=false → negative
                confidence = 0.95
                pos_vals = ["true"]
                neg_vals = ["false"]
            elif name_has_retained or label_has_retained:
                # active=true → retained (negative); active=false → churned (positive)
                confidence = 0.85
                pos_vals = ["false"]
                neg_vals = ["true"]
            else:
                continue  # bool with no outcome vocabulary — skip

            candidates.append(LabelSourceCandidate(
                type="property",
                raw_field=name,
                display_name=label or name,
                positive_values=pos_vals,
                negative_values=neg_vals,
                confidence=confidence,
                details={"property_type": "bool"},
            ))

        elif ptype == "enumeration":
            options = prop.get("options", [])
            if not options:
                continue

            pos_options = _find_matching_options(prop, CHURN_TERMS)
            neg_options = _find_matching_options(prop, RETAINED_TERMS)

            if not pos_options and not neg_options:
                continue  # no outcome vocabulary in options

            # Confidence: both pos+neg in options AND name/label signals → highest
            has_both_options = bool(pos_options) and bool(neg_options)
            name_signal = name_has_churn or name_has_retained or label_has_churn or label_has_retained

            if has_both_options and name_signal:
                confidence = 0.90
            elif has_both_options:
                confidence = 0.78
            elif name_signal:
                confidence = 0.65
            else:
                confidence = 0.50

            # If we only found one side, try to infer the other
            if not pos_options and neg_options:
                # Any option not in neg is a potential positive
                all_vals = [o.get("value", "") for o in options]
                pos_options = [v for v in all_vals if v not in neg_options]
                confidence = max(0.0, confidence - 0.15)  # penalise inference
            elif not neg_options and pos_options:
                all_vals = [o.get("value", "") for o in options]
                neg_options = [v for v in all_vals if v not in pos_options]
                confidence = max(0.0, confidence - 0.15)

            if not pos_options or not neg_options:
                continue

            candidates.append(LabelSourceCandidate(
                type="property",
                raw_field=name,
                display_name=label or name,
                positive_values=pos_options,
                negative_values=neg_options,
                confidence=confidence,
                details={
                    "property_type": "enumeration",
                    "total_options": len(options),
                },
            ))

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    logger.debug("label_discovery: property scan found %d candidates", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Path B: Deal pipeline scan
# ---------------------------------------------------------------------------

def scan_deal_pipelines(
    pipelines: List[Dict[str, Any]],
) -> List[LabelSourceCandidate]:
    """Scan deal pipelines for renewal/retention pipelines with outcome stages.

    Args:
        pipelines: Raw results from GET /crm/v3/pipelines/deals

    Returns:
        List of LabelSourceCandidate sorted by confidence descending.
    """
    candidates: List[LabelSourceCandidate] = []

    for pipeline in pipelines:
        pid = pipeline.get("id", "")
        plabel = pipeline.get("label", "")
        stages = pipeline.get("stages", [])

        if not stages:
            continue

        # Score the pipeline name for renewal relevance
        is_renewal_pipeline = _has_term(plabel, RENEWAL_PIPELINE_TERMS)

        # Find closed stages: isClosed="true" in stage metadata
        closed_stages = [
            s for s in stages
            if str(s.get("metadata", {}).get("isClosed", "false")).lower() == "true"
        ]
        if not closed_stages:
            continue

        # Classify closed stages as won (probability=1.0) or lost (probability=0.0)
        won_stages = [
            s for s in closed_stages
            if str(s.get("metadata", {}).get("probability", "")).strip() in ("1", "1.0", "100")
        ]
        lost_stages = [
            s for s in closed_stages
            if str(s.get("metadata", {}).get("probability", "")).strip() in ("0", "0.0", "0%")
        ]

        # Also try to classify by stage label if probability is unclear
        if not lost_stages:
            lost_stages = [
                s for s in closed_stages
                if _has_term(s.get("label", ""), CHURN_TERMS | {"lost"})
            ]
        if not won_stages:
            won_stages = [
                s for s in closed_stages
                if _has_term(s.get("label", ""), RETAINED_TERMS | {"won"})
            ]

        if not lost_stages or not won_stages:
            continue  # Can't distinguish outcome direction — skip

        # Build confidence
        if is_renewal_pipeline:
            confidence = 0.80
        else:
            # Default pipeline — may still contain renewals, lower confidence
            confidence = 0.55

        # Further boost if we have exactly 1 won + 1 lost (clean binary)
        if len(won_stages) == 1 and len(lost_stages) == 1:
            confidence = min(1.0, confidence + 0.10)

        candidates.append(LabelSourceCandidate(
            type="deal",
            raw_field=pid,
            display_name=plabel,
            positive_values=[s["id"] for s in lost_stages],   # lost deal → churn signal
            negative_values=[s["id"] for s in won_stages],    # won deal → retained signal
            confidence=confidence,
            details={
                "pipeline_id": pid,
                "pipeline_label": plabel,
                "lost_stage_labels": [s.get("label", "") for s in lost_stages],
                "won_stage_labels": [s.get("label", "") for s in won_stages],
                "is_renewal_pipeline": is_renewal_pipeline,
            },
        ))

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    logger.debug("label_discovery: deal pipeline scan found %d candidates", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Path C: Lifecycle stage scan
# ---------------------------------------------------------------------------

def scan_lifecycle_stages(
    props: List[Dict[str, Any]],
) -> List[LabelSourceCandidate]:
    """Scan the lifecyclestage company property for terminal negative states.

    Args:
        props: Raw results from GET /crm/v3/properties/companies

    Returns:
        0 or 1 candidates.
    """
    lifecycle_prop = next(
        (p for p in props if p.get("name") == "lifecyclestage"),
        None,
    )
    if not lifecycle_prop:
        return []

    pos_options = _find_matching_options(lifecycle_prop, CHURN_TERMS | {"other"})
    neg_options = _find_matching_options(lifecycle_prop, RETAINED_TERMS | {"customer"})

    if not pos_options or not neg_options:
        return []

    return [LabelSourceCandidate(
        type="lifecycle",
        raw_field="lifecyclestage",
        display_name="Company Lifecycle Stage",
        positive_values=pos_options,
        negative_values=neg_options,
        confidence=0.60,  # lifecycle stages are often poorly maintained
        details={"note": "lifecycle stages are frequently inconsistent — treat with caution"},
    )]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def discover_candidates(
    company_props: List[Dict[str, Any]],
    deal_pipelines: List[Dict[str, Any]],
) -> List[LabelSourceCandidate]:
    """Run all three scan paths and return ranked candidates.

    Args:
        company_props:  From GET /crm/v3/properties/companies
        deal_pipelines: From GET /crm/v3/pipelines/deals

    Returns:
        Combined list sorted by confidence descending. Empty list means
        no viable label source was detected.
    """
    all_candidates: List[LabelSourceCandidate] = []
    all_candidates.extend(scan_company_properties(company_props))
    all_candidates.extend(scan_deal_pipelines(deal_pipelines))
    all_candidates.extend(scan_lifecycle_stages(company_props))

    # Sort by confidence descending, stable (preserves type ordering on tie)
    all_candidates.sort(key=lambda c: c.confidence, reverse=True)

    logger.info(
        "label_discovery: %d total candidates found (top: %s at %.2f)",
        len(all_candidates),
        all_candidates[0].raw_field if all_candidates else "none",
        all_candidates[0].confidence if all_candidates else 0.0,
    )
    return all_candidates

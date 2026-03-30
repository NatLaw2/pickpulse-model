"""Dynamic schema discovery for HubSpot (and future CRM connectors).

Answers: "Which raw property corresponds to 'arr'?" — without hardcoding field names.

Algorithm:
  1. Pull all property metadata from the connected portal.
  2. For each canonical field, score every portal property against its alias list.
  3. Select the highest-confidence match; keep alternates for transparency.
  4. Return a SchemaMapping that the connector uses instead of hardcoded names.

Confidence scores:
  1.0 — exact name match (normalized)
  0.85 — label exact match (case-insensitive)
  0.75 — alias partial / substring match
  0.60 — semantic heuristic match (e.g. label contains keyword)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical field definitions
# ---------------------------------------------------------------------------
# Each entry:
#   aliases      — ordered list of known raw property names (lowercase normalized)
#   label_hints  — keywords that indicate this field from a property label
#   data_type    — "number" | "date" | "string" | "bool"
#   modes        — which business modes use this field: "saas", "services", "both"
#   mrr_scale    — if True and property name suggests MRR, multiply value by 12

CANONICAL_FIELDS: Dict[str, Dict[str, Any]] = {
    "arr": {
        "aliases": [
            "annualrevenue", "arr", "annual_recurring_revenue", "annual_revenue",
            "acv", "annual_contract_value", "contract_value", "deal_value",
        ],
        "mrr_aliases": ["mrr", "monthly_recurring_revenue", "monthly_revenue"],
        "label_hints": ["annual", "revenue", "arr", "contract value", "acv"],
        "data_type": "number",
        "modes": "both",
    },
    "company_size_employees": {
        "aliases": [
            "numberofemployees", "num_employees", "employee_count", "headcount",
            "employees", "staff_count",
        ],
        "label_hints": ["employee", "headcount", "staff", "team size"],
        "data_type": "number",
        "modes": "both",
    },
    "renewal_date": {
        "aliases": [
            "renewal_date", "contract_end_date", "subscription_end_date",
            "contract_renewal_date", "renewal_date__c", "closedate",
            "subscription_end", "contract_expiry",
        ],
        "label_hints": ["renewal", "contract end", "expir", "subscription end"],
        "data_type": "date",
        "modes": "both",
    },
    "industry": {
        "aliases": ["industry", "vertical", "sector", "hs_industry", "industry_type"],
        "label_hints": ["industry", "vertical", "sector"],
        "data_type": "string",
        "modes": "both",
    },
    "plan": {
        "aliases": [
            "plan", "subscription_plan", "tier", "product_tier", "plan_name",
            "subscription_type", "product_line",
        ],
        "label_hints": ["plan", "tier", "subscription type", "product"],
        "data_type": "string",
        "modes": "saas",
    },
    "nps_score": {
        "aliases": ["nps_score", "nps", "net_promoter_score", "csat_score", "satisfaction_score"],
        "label_hints": ["nps", "net promoter", "satisfaction", "csat"],
        "data_type": "number",
        "modes": "saas",
    },
    "monthly_logins": {
        "aliases": [
            "monthly_logins", "login_count", "monthly_active_users", "mau",
            "active_users", "monthly_sessions",
        ],
        "label_hints": ["login", "active user", "session", "mau"],
        "data_type": "number",
        "modes": "saas",
    },
    "support_tickets": {
        "aliases": [
            "support_tickets", "num_tickets", "open_tickets", "ticket_count",
            "num_support_cases", "support_cases",
        ],
        "label_hints": ["ticket", "support case", "issue count"],
        "data_type": "number",
        "modes": "both",
    },
    "last_activity_date": {
        "aliases": [
            "notes_last_activity_date", "last_activity_date", "hs_last_activity_date",
            "last_contacted", "last_contact_date", "last_activity",
        ],
        "label_hints": ["last activity", "last contact", "last touch"],
        "data_type": "date",
        "modes": "both",
    },
    "contact_count": {
        "aliases": [
            "num_associated_contacts", "contact_count", "num_contacts",
            "associated_contacts", "contacts",
        ],
        "label_hints": ["contact count", "number of contacts", "associated contacts"],
        "data_type": "number",
        "modes": "services",
    },
}


# ---------------------------------------------------------------------------
# Result types (plain dicts — avoid circular import with models.py)
# ---------------------------------------------------------------------------

class FieldMapping:
    """Resolved mapping for one canonical field."""

    __slots__ = ("canonical", "raw_name", "label", "confidence", "data_type", "mrr_scale")

    def __init__(
        self,
        canonical: str,
        raw_name: str,
        label: str,
        confidence: float,
        data_type: str,
        mrr_scale: bool = False,
    ) -> None:
        self.canonical = canonical
        self.raw_name = raw_name
        self.label = label
        self.confidence = confidence
        self.data_type = data_type
        self.mrr_scale = mrr_scale

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical": self.canonical,
            "raw_name": self.raw_name,
            "label": self.label,
            "confidence": round(self.confidence, 2),
            "data_type": self.data_type,
            "mrr_scale": self.mrr_scale,
        }


class SchemaMapping:
    """Full mapping result for a portal's property set."""

    def __init__(
        self,
        resolved: Dict[str, FieldMapping],
        alternates: Dict[str, List[FieldMapping]],
        unmapped: List[str],
        notable_unknown: List[str],
    ) -> None:
        self.resolved = resolved
        self.alternates = alternates
        self.unmapped = unmapped
        self.notable_unknown = notable_unknown

    def get(self, canonical: str) -> Optional[str]:
        """Return the raw property name for a canonical field, or None."""
        fm = self.resolved.get(canonical)
        return fm.raw_name if fm else None

    def mrr_scale(self, canonical: str) -> bool:
        """Return True if the resolved field is an MRR field that should be ×12."""
        fm = self.resolved.get(canonical)
        return fm.mrr_scale if fm else False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolved": {k: v.to_dict() for k, v in self.resolved.items()},
            "alternates": {
                k: [m.to_dict() for m in ms]
                for k, ms in self.alternates.items()
                if ms
            },
            "unmapped": self.unmapped,
            "notable_unknown": self.notable_unknown[:20],
            "coverage_pct": round(
                len(self.resolved) / max(len(CANONICAL_FIELDS), 1) * 100, 1
            ),
        }


# ---------------------------------------------------------------------------
# Core discovery logic
# ---------------------------------------------------------------------------

def _normalize_name(s: str) -> str:
    """Lowercase, strip non-alphanumeric to empty, collapse whitespace."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _score(raw_name: str, raw_label: str, canonical: str, field_def: Dict[str, Any]) -> float:
    """Return confidence score [0, 1] for one raw property against one canonical field."""
    n = _normalize_name(raw_name)
    lbl = raw_label.lower().strip()

    # Exact normalized name match
    for alias in field_def["aliases"]:
        if n == _normalize_name(alias):
            return 1.0

    # MRR alias (special — caller sets mrr_scale=True)
    for alias in field_def.get("mrr_aliases", []):
        if n == _normalize_name(alias):
            return 0.95

    # Exact label match
    for hint in field_def.get("label_hints", []):
        if hint.lower() == lbl:
            return 0.85

    # Partial alias match (raw_name contains alias)
    for alias in field_def["aliases"]:
        an = _normalize_name(alias)
        if an and (an in n or n in an):
            return 0.75

    # Label hint substring match
    for hint in field_def.get("label_hints", []):
        if hint.lower() in lbl:
            return 0.60

    return 0.0


def discover(
    properties: List[Dict[str, Any]],
    business_mode: str = "saas",
    min_confidence: float = 0.55,
) -> SchemaMapping:
    """Discover field mappings from a list of HubSpot property metadata dicts.

    Args:
        properties: Raw results from GET /crm/v3/properties/companies
                    (each dict has 'name', 'label', 'type', etc.)
        business_mode: "saas" or "services" — filters which canonical fields
                       to attempt to resolve.
        min_confidence: Properties with score below this threshold are not
                        promoted to resolved (kept in alternates only).

    Returns:
        SchemaMapping with resolved, alternates, unmapped, notable_unknown.
    """
    # Index properties by their normalized name for O(1) lookup later
    prop_index = {_normalize_name(p["name"]): p for p in properties}

    resolved: Dict[str, FieldMapping] = {}
    alternates: Dict[str, List[FieldMapping]] = {}

    for canonical, field_def in CANONICAL_FIELDS.items():
        mode = field_def.get("modes", "both")
        if mode not in ("both", business_mode):
            continue

        candidates: List[tuple[float, FieldMapping]] = []

        for prop in properties:
            raw_name = prop.get("name", "")
            raw_label = prop.get("label", "")
            prop_type = prop.get("type", "string")

            score = _score(raw_name, raw_label, canonical, field_def)
            if score == 0:
                continue

            # Check MRR scale flag
            mrr_scale = any(
                _normalize_name(raw_name) == _normalize_name(a)
                for a in field_def.get("mrr_aliases", [])
            )

            fm = FieldMapping(
                canonical=canonical,
                raw_name=raw_name,
                label=raw_label,
                confidence=score,
                data_type=prop_type,
                mrr_scale=mrr_scale,
            )
            candidates.append((score, fm))

        candidates.sort(key=lambda x: x[0], reverse=True)

        if candidates and candidates[0][0] >= min_confidence:
            resolved[canonical] = candidates[0][1]
            alternates[canonical] = [c[1] for c in candidates[1:4]]  # top 3 runners-up
            if candidates[0][0] < 0.8:
                logger.info(
                    "schema_mapper: low-confidence mapping %s → %s (%.2f) — alternates: %s",
                    canonical,
                    candidates[0][1].raw_name,
                    candidates[0][0],
                    [c[1].raw_name for c in candidates[1:3]],
                )
        else:
            alternates[canonical] = [c[1] for c in candidates[:3]]
            logger.debug("schema_mapper: no mapping found for %s", canonical)

    unmapped = [
        c for c in CANONICAL_FIELDS
        if CANONICAL_FIELDS[c].get("modes", "both") in ("both", business_mode)
        and c not in resolved
    ]

    # Surface unknown properties that might be interesting (custom fields)
    known_raw = {fm.raw_name for fm in resolved.values()}
    notable_unknown = [
        p["name"] for p in properties
        if p["name"] not in known_raw
        and not p["name"].startswith("hs_")
        and not p["name"].startswith("hubspot_")
    ]

    logger.info(
        "schema_mapper: resolved=%d unmapped=%d notable_custom=%d (mode=%s)",
        len(resolved), len(unmapped), len(notable_unknown), business_mode,
    )
    return SchemaMapping(resolved, alternates, unmapped, notable_unknown)

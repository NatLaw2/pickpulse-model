"""
CRM alias pack system — builds the merged alias map, requires-confirmation
index, and churn value vocabulary used by schema_mapping.py.

Architecture
------------
- GLOBAL_PACK provides comprehensive vendor-agnostic aliases (superset of
  the old hardcoded ALIAS_MAP).
- CRM-specific packs add vendor-specific field names on top.
- Aliases are deduplicated; ordering is preserved (first match wins in the
  suggestion engine, so unambiguous aliases come first within each list).
- Aliases marked requires_confirmation=True are tracked in
  REQUIRES_CONFIRMATION_NORMS so the suggestion engine can downgrade their
  confidence to LOW and flag them for explicit user confirmation in the UI.

Public exports
--------------
MERGED_ALIAS_MAP          : Dict[str, List[str]]
REQUIRES_CONFIRMATION_NORMS : Dict[str, FrozenSet[str]]  (normalised alias forms)
CHURN_POSITIVE_VALUES     : FrozenSet[str]
CHURN_NEGATIVE_VALUES     : FrozenSet[str]
ALL_PACKS                 : List[CrmPack]
"""
from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Set

from ._base import CrmPack
from .global_ import GLOBAL_PACK
from .salesforce import SALESFORCE_PACK
from .hubspot import HUBSPOT_PACK
from .dynamics import DYNAMICS_PACK
from .pipedrive import PIPEDRIVE_PACK

# All packs in priority order: global first, then CRM-specific.
# Within each pack, the entry ordering determines alias priority.
ALL_PACKS: List[CrmPack] = [
    GLOBAL_PACK,
    SALESFORCE_PACK,
    HUBSPOT_PACK,
    DYNAMICS_PACK,
    PIPEDRIVE_PACK,
]


def _norm(s: str) -> str:
    """Strip non-alphanumeric characters and lowercase — mirrors schema_mapping._norm."""
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


def _build_merged_alias_map() -> Dict[str, List[str]]:
    """
    Merge all packs into a single {canonical: [alias, ...]} dict.

    Key ordering rules:
    1. Non-requires_confirmation aliases always come before
       requires_confirmation aliases within each canonical bucket.
       This ensures unambiguous direct-flag aliases (e.g. is_lost, Churned__c)
       always take priority over ambiguous stage/status aliases (e.g. status,
       StageName) regardless of which pack they originate from.
    2. Within each RC group, pack order is preserved (global first, then CRMs).
    3. Deduplication is case-sensitive: both "accountid" (global) and
       "AccountId" (Salesforce) are retained so callers can inspect the
       exact alias strings as defined in each pack.  The suggestion engine
       normalises aliases via .lower() before comparison, so duplicates that
       differ only in casing are functionally redundant but harmless.
    """
    merged: Dict[str, List[str]] = {}

    # Two-pass: unambiguous aliases first, then requires_confirmation aliases.
    for rc_pass in (False, True):
        for pack in ALL_PACKS:
            for entry in pack.entries:
                if entry.requires_confirmation != rc_pass:
                    continue
                bucket = merged.setdefault(entry.canonical, [])
                seen = set(bucket)          # exact case-sensitive dedup
                for alias in entry.aliases:
                    if alias not in seen:
                        bucket.append(alias)
                        seen.add(alias)
    return merged


def _build_requires_confirmation_norms() -> Dict[str, FrozenSet[str]]:
    """
    Build {canonical: frozenset(normalised_alias)} for every alias that
    requires user confirmation before being applied.

    The normalised form (_norm) matches what schema_mapping uses when
    comparing aliases against source column names.
    """
    result: Dict[str, Set[str]] = {}
    for pack in ALL_PACKS:
        for entry in pack.entries:
            if entry.requires_confirmation:
                bucket = result.setdefault(entry.canonical, set())
                for alias in entry.aliases:
                    bucket.add(_norm(alias))
    return {k: frozenset(v) for k, v in result.items()}


def _build_churn_vocabularies() -> tuple[FrozenSet[str], FrozenSet[str]]:
    """Merge churn-positive and churn-negative value sets from all packs."""
    positive: Set[str] = set()
    negative: Set[str] = set()
    for pack in ALL_PACKS:
        for v in pack.churn_positive_values:
            positive.add(v.lower().strip())
        for v in pack.churn_negative_values:
            negative.add(v.lower().strip())
    return frozenset(positive), frozenset(negative)


# ---------------------------------------------------------------------------
# Module-level singletons — built once at import time
# ---------------------------------------------------------------------------
MERGED_ALIAS_MAP: Dict[str, List[str]] = _build_merged_alias_map()
REQUIRES_CONFIRMATION_NORMS: Dict[str, FrozenSet[str]] = _build_requires_confirmation_norms()
CHURN_POSITIVE_VALUES: FrozenSet[str]
CHURN_NEGATIVE_VALUES: FrozenSet[str]
CHURN_POSITIVE_VALUES, CHURN_NEGATIVE_VALUES = _build_churn_vocabularies()

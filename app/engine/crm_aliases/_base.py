"""Base dataclasses for CRM alias packs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AliasEntry:
    """
    Maps a canonical field to a set of CRM-specific alias names.

    requires_confirmation=True means the alias is ambiguous in this CRM context.
    The mapping engine will suggest it with LOW confidence and mark it so the
    UI never auto-populates it — the user must explicitly confirm.
    """
    canonical: str
    aliases: List[str]
    requires_confirmation: bool = False
    notes: str = ""


@dataclass
class CrmPack:
    """A single CRM vendor's alias pack."""
    name: str                         # e.g. "salesforce"
    display_name: str                 # e.g. "Salesforce"
    entries: List[AliasEntry] = field(default_factory=list)

    # Churn-positive: column values that mean "this account churned"
    churn_positive_values: List[str] = field(default_factory=list)

    # Churn-negative: column values that mean "this account is retained"
    churn_negative_values: List[str] = field(default_factory=list)

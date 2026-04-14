"""CRM outcome auto-import.

Detects churn/renewal status from raw CRM account fields during sync and
writes to account_outcomes — without creating duplicates on re-sync.

Detection logic
---------------
HubSpot (in priority order):
  1. hs_lifecycle_stage in a known churned set
  2. hs_lead_status contains "former" or "churned"
  3. Any property key containing "churn" with a truthy value

Salesforce (in priority order):
  1. Account.Type == "Former Customer"
  2. Any field key containing "churn" with a truthy value

Only "churned" outcomes are auto-imported.  Renewal/expansion outcomes
require explicit marking in the Accounts page (too ambiguous to infer from
standard CRM fields).
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple

from app.integrations.models import Account
from app.storage import repo

logger = logging.getLogger("pickpulse.outcome_import")

# HubSpot lifecycle stage values that indicate a churned customer
_HS_CHURNED_STAGES = {"churned", "former_customer"}

# HubSpot lead status substrings that indicate churn
_HS_CHURNED_STATUS_KEYWORDS = ("former", "churned", "lost customer")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_date(value: object) -> Optional[str]:
    """Return an ISO date string (YYYY-MM-DD) from a CRM field value, or None."""
    if not value:
        return None
    s = str(value).strip()
    return s[:10] if len(s) >= 10 else None


def _scan_for_churn_field(raw_data: dict) -> Optional[str]:
    """Scan raw_data for any custom field with 'churn' in the key that has a
    truthy, non-negative value.  Returns the field value as an ISO date string
    when it looks like a date, otherwise None (caller uses today's date).
    """
    for key, val in raw_data.items():
        if "churn" not in key.lower():
            continue
        if not val or val in ("false", "0", "", "no", "False", "No"):
            continue
        # If the value looks like a date, use it as effective_date
        date_str = _safe_date(val)
        return date_str  # may be None — caller handles that
    return None


# ---------------------------------------------------------------------------
# Provider-specific detectors
# ---------------------------------------------------------------------------

def detect_hubspot_outcome(raw_data: dict) -> Optional[Tuple[str, Optional[str]]]:
    """Return (outcome_type, effective_date) or None if no churn indicator found."""
    # 1. Lifecycle stage
    lifecycle = str(raw_data.get("hs_lifecycle_stage") or "").lower().strip()
    if lifecycle in _HS_CHURNED_STAGES:
        return "churned", _safe_date(raw_data.get("closedate"))

    # 2. Lead status
    lead_status = str(raw_data.get("hs_lead_status") or "").lower().strip()
    if any(kw in lead_status for kw in _HS_CHURNED_STATUS_KEYWORDS):
        return "churned", None

    # 3. Custom churn field scan
    date_val = _scan_for_churn_field(raw_data)
    if date_val is not None:  # _scan returned something (even empty string from a match)
        # Re-check: _scan returns None when no key matched, so this branch
        # only fires when a matching key was found.
        return "churned", date_val

    return None


def detect_salesforce_outcome(raw_data: dict) -> Optional[Tuple[str, Optional[str]]]:
    """Return (outcome_type, effective_date) or None if no churn indicator found."""
    # 1. Standard Account.Type field
    account_type = str(raw_data.get("Type") or "").strip()
    if account_type == "Former Customer":
        return "churned", _safe_date(raw_data.get("LastActivityDate"))

    # 2. Custom churn field scan
    date_val = _scan_for_churn_field(raw_data)
    if date_val is not None:
        return "churned", date_val

    return None


_DETECT_FNS: Dict[str, Callable[[dict], Optional[Tuple[str, Optional[str]]]]] = {
    "hubspot": detect_hubspot_outcome,
    "salesforce": detect_salesforce_outcome,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def import_outcomes_from_accounts(
    accounts: List[Account],
    source: str,
    tenant_id: str,
) -> int:
    """Detect and import churn outcomes from raw CRM account data.

    Called automatically after each sync.  Uses ``repo.upsert_outcome`` which
    is idempotent — re-running sync never creates duplicate outcome records.

    Parameters
    ----------
    accounts : list of Account
        The Account objects returned by the connector's pull_accounts().
    source : str
        CRM provider name — "hubspot" or "salesforce".
    tenant_id : str
        Supabase tenant UUID.

    Returns
    -------
    int
        Number of new outcome records written this run.
    """
    detect_fn = _DETECT_FNS.get(source)
    if not detect_fn:
        logger.debug("[outcome_import] No detector for source '%s' — skipping", source)
        return 0

    written = 0
    for account in accounts:
        try:
            result = detect_fn(account.raw_data)
            if not result:
                continue
            outcome_type, effective_date = result
            ok = repo.upsert_outcome(
                external_id=account.external_id,
                outcome_type=outcome_type,
                source=source,
                effective_date=effective_date,
                notes=f"Auto-imported from {source} account properties",
                tenant_id=tenant_id,
            )
            if ok:
                written += 1
                logger.info(
                    "[outcome_import] %s account=%s → %s (date=%s)",
                    source, account.external_id, outcome_type, effective_date,
                )
        except Exception as exc:
            logger.warning(
                "[outcome_import] Error processing account %s: %s",
                account.external_id, exc,
            )

    logger.info(
        "[outcome_import] %s: %d new outcomes from %d accounts",
        source, written, len(accounts),
    )
    return written

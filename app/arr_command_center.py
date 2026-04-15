"""ARR Command Center — service layer.

Builds executive-facing revenue risk intelligence from existing prediction data.
Reads from: churn_scores_daily, accounts, account_signals_daily.
No new tables required.

Design notes
------------
- All functions require tenant_id for strict multi-tenant isolation.
- ARR fields are nullable; coverage metadata surfaces gaps to the UI.
- The rule engine maps only to real signal keys with explicit thresholds.
- Driver labels come from top_drivers jsonb (already translated during scoring).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("pickpulse.arr_command_center")

# ---------------------------------------------------------------------------
# Signal thresholds for the rule engine
# ---------------------------------------------------------------------------

_THRESHOLDS = {
    "days_since_last_login_elevated": 30,   # mild concern
    "days_since_last_login_high": 60,       # strong signal
    "monthly_logins_low": 3,
    "support_tickets_elevated": 3,
    "support_tickets_high": 5,
    "days_until_renewal_critical": 30,
    "days_until_renewal_urgent": 60,
    "nps_score_low": 5,
    "nps_score_critical": 3,
}

# How many accounts to include in the ranked table (server-side cap)
_RANKED_TABLE_LIMIT = 50

# Minimum churn_risk_pct to be counted as a "priority account"
_PRIORITY_RISK_THRESHOLD = 25.0


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------

def generate_interventions(
    signals: Dict[str, Any],
    churn_risk_pct: float,
) -> List[Dict[str, Any]]:
    """Generate suggested actions from real signal values.

    Each intervention is tied to at least one explicit signal key.
    No fake impact percentages or projected savings are produced.

    Parameters
    ----------
    signals : dict
        Latest signal snapshot for the account. Keys match account_signals_daily
        signal_key values: monthly_logins, days_since_last_login, support_tickets,
        nps_score, days_until_renewal, auto_renew_flag, etc.
    churn_risk_pct : float
        Churn risk as a percentage (0–100).

    Returns
    -------
    List of intervention dicts (up to 5), each with:
        title, description, owner_role, signals (list of trigger descriptions)
    """
    t = _THRESHOLDS
    interventions: List[Dict[str, Any]] = []
    seen_titles: set = set()

    dsl = _float(signals.get("days_since_last_login"))
    ml = _float(signals.get("monthly_logins"))
    st = _float(signals.get("support_tickets"))
    dur = _float(signals.get("days_until_renewal"))
    nps = _float(signals.get("nps_score"))
    arf = _float(signals.get("auto_renew_flag"))

    def add(title: str, description: str, owner_role: str, trigger_signals: List[str]) -> None:
        if title not in seen_titles:
            seen_titles.add(title)
            interventions.append({
                "title": title,
                "description": description,
                "owner_role": owner_role,
                "signals": trigger_signals,
            })

    # ── Low / declining engagement ───────────────────────────────────────────
    engagement_triggers: List[str] = []
    if dsl is not None and dsl >= t["days_since_last_login_high"]:
        engagement_triggers.append(f"{int(dsl)} days since last login")
    if ml is not None and ml <= t["monthly_logins_low"]:
        engagement_triggers.append(f"{int(ml)} login{'s' if ml != 1 else ''} this month")

    if engagement_triggers:
        add(
            title="Schedule a product re-engagement session",
            description=(
                "Product engagement has dropped significantly. A structured re-engagement "
                "session — covering new features, use case alignment, and adoption blockers "
                "— can restore activity and reinforce the account's perceived value."
            ),
            owner_role="CSM",
            trigger_signals=engagement_triggers,
        )
    elif dsl is not None and dsl >= t["days_since_last_login_elevated"]:
        add(
            title="CSM check-in and value recap",
            description=(
                "Login activity has slowed. A brief outreach to understand current usage "
                "and reaffirm ROI can prevent further disengagement."
            ),
            owner_role="CSM",
            trigger_signals=[f"{int(dsl)} days since last login"],
        )

    # ── High support burden ───────────────────────────────────────────────────
    if st is not None and st >= t["support_tickets_high"]:
        add(
            title="Escalate open support issues to senior engineer",
            description=(
                f"This account has {int(st)} open support tickets, which is significantly "
                "above the healthy baseline. Escalating to a senior engineer and scheduling "
                "a support review call can prevent frustration from becoming a churn decision."
            ),
            owner_role="Support",
            trigger_signals=[f"{int(st)} open support tickets"],
        )
    elif st is not None and st >= t["support_tickets_elevated"]:
        add(
            title="Proactive support review",
            description=(
                f"{int(st)} open tickets signals unresolved friction. A proactive review "
                "can close issues before they compound."
            ),
            owner_role="Support",
            trigger_signals=[f"{int(st)} open support tickets"],
        )

    # ── Renewal timing ───────────────────────────────────────────────────────
    if dur is not None:
        no_auto_renew = arf is None or arf == 0

        if dur <= t["days_until_renewal_critical"] and no_auto_renew:
            add(
                title="Executive sponsor outreach before renewal",
                description=(
                    f"Renewal is {int(dur)} days away and auto-renew is not enabled. "
                    "An executive-to-executive conversation can accelerate the renewal decision "
                    "and surface any strategic concerns that a CSM may not be able to resolve."
                ),
                owner_role="Exec",
                trigger_signals=[f"{int(dur)} days to renewal", "auto-renew not enabled"],
            )
        elif dur <= t["days_until_renewal_urgent"] and no_auto_renew:
            add(
                title="Initiate proactive renewal conversation",
                description=(
                    f"Renewal is {int(dur)} days away with no auto-renew enabled. "
                    "Starting the commercial conversation now avoids a last-minute decision "
                    "under time pressure."
                ),
                owner_role="AE",
                trigger_signals=[f"{int(dur)} days to renewal", "auto-renew not enabled"],
            )
        elif dur <= t["days_until_renewal_critical"]:
            # Auto-renew is on, but renewal is imminent — still worth a health check
            add(
                title="Pre-renewal health check",
                description=(
                    f"Renewal is {int(dur)} days away. Even with auto-renew enabled, "
                    "confirming the account is in good standing and has no unresolved issues "
                    "is a best practice at this stage."
                ),
                owner_role="CSM",
                trigger_signals=[f"{int(dur)} days to renewal"],
            )

    # ── Low NPS / customer satisfaction ──────────────────────────────────────
    if nps is not None and nps <= t["nps_score_critical"]:
        add(
            title="Immediate executive escalation",
            description=(
                f"Customer satisfaction score is {nps:.0f}/10 — a critical signal. "
                "This requires immediate executive visibility and a structured recovery plan. "
                "Delay risks accelerating the churn timeline."
            ),
            owner_role="Exec",
            trigger_signals=[f"NPS score: {nps:.0f}/10"],
        )
    elif nps is not None and nps <= t["nps_score_low"]:
        add(
            title="Customer satisfaction recovery conversation",
            description=(
                f"An NPS of {nps:.0f}/10 indicates meaningful dissatisfaction. A structured "
                "conversation to surface and document specific concerns — and commit to a "
                "resolution plan — can shift sentiment before the renewal window."
            ),
            owner_role="CSM",
            trigger_signals=[f"NPS score: {nps:.0f}/10"],
        )

    # ── Fallback: high risk with limited signal coverage ─────────────────────
    if not interventions and churn_risk_pct >= 50:
        add(
            title="Proactive health check — limited signal data available",
            description=(
                "This account is elevated risk, but detailed usage signals are limited. "
                "A direct outreach to the primary contact or champion can uncover concerns "
                "that are not yet visible in the platform."
            ),
            owner_role="CSM",
            trigger_signals=[],
        )

    return interventions[:5]


# ---------------------------------------------------------------------------
# Driver description helpers
# ---------------------------------------------------------------------------

_DRIVER_DESCRIPTIONS: Dict[str, str] = {
    "days_since_last_login": "Product engagement has dropped — the account has not logged in recently.",
    "monthly_logins": "Monthly login activity is low relative to healthy accounts at this tier.",
    "support_tickets": "Support volume is elevated, indicating unresolved friction with the product.",
    "nps_score": "Customer satisfaction score is below the healthy benchmark.",
    "days_until_renewal": "Renewal is approaching with unresolved risk signals.",
    "auto_renew_flag": "Auto-renew is not enabled, leaving the renewal decision open.",
    "contract_months_remaining": "Limited contract runway is creating urgency.",
    "seats": "Seat utilization may not justify the current contract scope.",
    "arr": "Account contract value is a significant factor in prioritization.",
}

def _driver_description(feature: str, label: str, direction: str) -> str:
    """Return a business-readable description for a risk driver."""
    if feature in _DRIVER_DESCRIPTIONS and direction == "increases_risk":
        return _DRIVER_DESCRIPTIONS[feature]
    # Fall back to label as context
    if direction == "decreases_risk":
        return f"{label} is a positive signal, but other factors are driving elevated risk."
    return f"{label} is contributing to elevated churn risk for this account."


# ---------------------------------------------------------------------------
# Coverage + ranking logic
# ---------------------------------------------------------------------------

def _float(v: Any) -> Optional[float]:
    """Safely cast to float; return None on failure."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _compute_coverage_notes(
    total_scored: int,
    accounts_with_arr: int,
    accounts_with_renewal: int,
) -> List[str]:
    """Build human-readable coverage notes for the summary bar."""
    notes: List[str] = []

    if total_scored == 0:
        return notes

    arr_missing = total_scored - accounts_with_arr
    if arr_missing > 0:
        arr_pct = round(100 * arr_missing / total_scored)
        notes.append(
            f"ARR is missing for {arr_missing} of {total_scored} scored accounts "
            f"({arr_pct}%). ARR at Risk reflects partial coverage only."
        )

    renewal_missing = total_scored - accounts_with_renewal
    if renewal_missing > 0:
        notes.append(
            f"Renewal timing is unavailable for {renewal_missing} account"
            f"{'s' if renewal_missing != 1 else ''}."
        )

    return notes


def build_command_center(
    tenant_id: str,
) -> Dict[str, Any]:
    """Build the full ARR Command Center payload.

    Returns has_predictions=False if no scored accounts exist, so the
    frontend can show a clean empty state.
    """
    from app.storage import repo

    # ── 1. Fetch latest scores (joined with accounts) ────────────────────────
    raw_scores = repo.latest_scores(limit=500, tenant_id=tenant_id)

    if not raw_scores:
        return {
            "has_predictions": False,
            "summary": None,
            "accounts": [],
        }

    # ── 2. Fetch latest signals for all accounts (one query) ─────────────────
    signals_by_uuid: Dict[str, Dict[str, Any]] = repo.bulk_latest_signals(tenant_id)

    # ── 3. Build enriched account list ───────────────────────────────────────
    enriched: List[Dict[str, Any]] = []

    for score in raw_scores:
        account_uuid: str = score.get("account_id", "")
        arr_val = _float(score.get("arr"))
        risk_pct = _float(score.get("churn_risk_pct")) or 0.0

        # Signals for this account
        signals = signals_by_uuid.get(account_uuid, {})
        dur = _float(signals.get("days_until_renewal"))

        # Weighted risk (only when ARR is available)
        weighted = round(arr_val * risk_pct / 100, 2) if arr_val is not None else None

        # Top 3 drivers (already translated labels from scoring pipeline)
        raw_drivers = score.get("top_drivers") or []
        if isinstance(raw_drivers, str):
            import json as _json
            try:
                raw_drivers = _json.loads(raw_drivers)
            except Exception:
                raw_drivers = []

        top_drivers = [
            {
                "label": d.get("label") or _humanize_feature(d.get("feature", "")),
                "direction": d.get("direction", "increases_risk"),
                "feature": d.get("feature", ""),
                "value": _float(d.get("value")),
                "retained_mean": _float(d.get("retained_mean")),
                "churned_mean": _float(d.get("churned_mean")),
            }
            for d in raw_drivers
            if d.get("direction") == "increases_risk"  # show only risk-increasing drivers in table
        ][:3]

        missing: List[str] = []
        if arr_val is None:
            missing.append("arr")
        if dur is None:
            missing.append("renewal_timing")

        enriched.append({
            "account_id": account_uuid,
            "external_id": score.get("external_id", ""),
            "name": score.get("name") or score.get("domain") or "Unnamed Account",
            "arr": arr_val,
            "churn_risk_pct": risk_pct,
            "weighted_risk_value": weighted,
            "days_until_renewal": dur,
            "top_drivers": top_drivers,
            "confidence_level": score.get("confidence_level"),
            "source": score.get("source", ""),
            "has_arr": arr_val is not None,
            "has_renewal": dur is not None,
            "missing_fields": missing,
        })

    # ── 4. Rank accounts ──────────────────────────────────────────────────────
    # Primary: weighted_risk_value DESC (accounts with ARR first)
    # Secondary: churn_risk_pct DESC (accounts without ARR ranked by raw risk)
    enriched.sort(
        key=lambda r: (
            r["weighted_risk_value"] if r["weighted_risk_value"] is not None else -1,
            r["churn_risk_pct"],
        ),
        reverse=True,
    )

    ranked = enriched[:_RANKED_TABLE_LIMIT]

    # ── 5. Compute summary metrics ────────────────────────────────────────────
    total_scored = len(enriched)
    accounts_with_arr = sum(1 for r in enriched if r["has_arr"])
    accounts_with_renewal = sum(1 for r in enriched if r["has_renewal"])

    arr_at_risk = sum(
        r["weighted_risk_value"]
        for r in enriched
        if r["weighted_risk_value"] is not None
    )
    arr_at_risk = round(arr_at_risk, 2)

    priority_accounts = [r for r in enriched if r["churn_risk_pct"] >= _PRIORITY_RISK_THRESHOLD]
    avg_risk = (
        round(sum(r["churn_risk_pct"] for r in enriched) / total_scored, 1)
        if total_scored > 0 else 0.0
    )

    coverage_notes = _compute_coverage_notes(
        total_scored, accounts_with_arr, accounts_with_renewal
    )

    summary = {
        "arr_at_risk": arr_at_risk,
        "arr_at_risk_is_partial": accounts_with_arr < total_scored,
        "total_scored_accounts": total_scored,
        "accounts_with_arr": accounts_with_arr,
        "accounts_with_renewal": accounts_with_renewal,
        "priority_account_count": len(priority_accounts),
        "avg_risk_pct": avg_risk,
        "coverage_notes": coverage_notes,
    }

    return {
        "has_predictions": True,
        "summary": summary,
        "accounts": ranked,
    }


def get_account_details(
    account_id: str,
    tenant_id: str,
) -> Optional[Dict[str, Any]]:
    """Build the full account drawer payload.

    Parameters
    ----------
    account_id : str
        UUID of the account (accounts.id).
    tenant_id : str
        Tenant identifier from JWT.
    """
    from app.storage import repo
    from app.storage.db import get_client
    import json as _json

    sb = get_client()

    # ── Fetch account + latest score ──────────────────────────────────────────
    try:
        score_res = (
            sb.table("churn_scores_daily")
            .select("*, accounts(id, name, domain, arr, source, external_id, metadata)")
            .eq("tenant_id", tenant_id)
            .eq("account_id", account_id)
            .order("score_date", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("[arr_cc] score fetch failed for account %s: %s", account_id, exc)
        return None

    if not score_res.data:
        return None

    score_row = score_res.data[0]
    acct = score_row.get("accounts") or {}
    if isinstance(acct, list):
        acct = acct[0] if acct else {}

    arr_val = _float(acct.get("arr"))
    risk_pct = _float(score_row.get("churn_risk_pct")) or 0.0
    external_id = acct.get("external_id", "")

    # ── Fetch latest signals ──────────────────────────────────────────────────
    signals: Dict[str, Any] = {}
    try:
        sig_res = (
            sb.table("account_signals_daily")
            .select("signal_key, signal_value, signal_text, signal_date")
            .eq("tenant_id", tenant_id)
            .eq("account_id", account_id)
            .order("signal_date", desc=True)
            .limit(200)
            .execute()
        )
        # Pivot: keep only latest value per signal key
        seen_keys: set = set()
        for row in (sig_res.data or []):
            key = row.get("signal_key")
            if key and key not in seen_keys:
                seen_keys.add(key)
                val = row.get("signal_value")
                if val is None:
                    val = row.get("signal_text")
                if val is not None:
                    if key == "extra":
                        try:
                            extra = _json.loads(str(val))
                            for ek, ev in extra.items():
                                signals[ek] = ev
                        except Exception:
                            pass
                    else:
                        signals[key] = val
    except Exception as exc:
        logger.warning("[arr_cc] signal fetch failed for account %s: %s", account_id, exc)

    # ── Parse drivers ─────────────────────────────────────────────────────────
    raw_drivers = score_row.get("top_drivers") or []
    if isinstance(raw_drivers, str):
        try:
            raw_drivers = _json.loads(raw_drivers)
        except Exception:
            raw_drivers = []

    drivers = []
    for d in raw_drivers:
        feature = d.get("feature", "")
        label = d.get("label") or _humanize_feature(feature)
        direction = d.get("direction", "increases_risk")
        description = _driver_description(feature, label, direction)
        drivers.append({
            "label": label,
            "description": description,
            "direction": direction,
            "feature": feature,
            "value": _float(d.get("value")),
            "retained_mean": _float(d.get("retained_mean")),
            "churned_mean": _float(d.get("churned_mean")),
        })

    # ── Generate interventions ────────────────────────────────────────────────
    interventions = generate_interventions(signals, risk_pct)

    # ── Data quality flags ────────────────────────────────────────────────────
    missing_fields: List[str] = []
    data_quality_notes: List[str] = []

    if arr_val is None:
        missing_fields.append("arr")
        data_quality_notes.append("ARR is not available for this account.")

    dur = _float(signals.get("days_until_renewal"))
    if dur is None:
        missing_fields.append("renewal_timing")
        data_quality_notes.append("Renewal timing is not available for this account.")

    if not signals:
        missing_fields.append("signals")
        data_quality_notes.append("Limited product usage history is available for this account.")

    if not drivers:
        data_quality_notes.append(
            "Risk driver detail is not available — the model may not have SHAP data for this account."
        )

    return {
        "account": {
            "account_id": account_id,
            "external_id": external_id,
            "name": acct.get("name") or acct.get("domain") or "Unnamed Account",
            "arr": arr_val,
            "churn_risk_pct": risk_pct,
            "confidence_level": score_row.get("confidence_level"),
            "source": acct.get("source", ""),
            "score_date": str(score_row.get("score_date", "")),
        },
        "drivers": drivers,
        "signals": signals,
        "interventions": interventions,
        "missing_fields": missing_fields,
        "data_quality_notes": data_quality_notes,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FEATURE_HUMANIZE: Dict[str, str] = {
    "days_since_last_login": "Engagement Recency",
    "monthly_logins": "Monthly Engagement",
    "support_tickets": "Support Volume",
    "nps_score": "Customer Satisfaction",
    "days_until_renewal": "Renewal Proximity",
    "auto_renew_flag": "Auto-Renew Status",
    "contract_months_remaining": "Contract Duration",
    "seats": "Seat Utilization",
    "arr": "Account Value",
    "contact_count": "Stakeholder Coverage",
    "deal_count": "Deal Engagement",
    "days_since_last_activity": "Recent Activity",
}


def _humanize_feature(feature: str) -> str:
    if feature in _FEATURE_HUMANIZE:
        return _FEATURE_HUMANIZE[feature]
    return feature.replace("extra_", "").replace("_", " ").title()

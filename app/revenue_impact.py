"""
Revenue Impact Tracker — platform-level calculation logic.

Pure functions with no heavy ML dependencies so they can be tested in isolation.
"""
from __future__ import annotations

# Modeled save rate applied to the at-risk renewal pipeline (illustrative).
# Represents the share of arr_at_risk estimated to be retained through
# model-driven CSM intervention on accounts renewing within 90 days.
_ILLUSTRATIVE_RENEWAL_RETENTION_RATE = 0.35

# Modeled risk reduction rate applied to medium-risk accounts outside the
# renewal window (churn_risk_pct 40–70, not renewing within 90 days).
# Represents partial exposure reduction from earlier, model-prompted outreach.
_ILLUSTRATIVE_RISK_REDUCTION_RATE = 0.20

# churn_risk_pct thresholds — kept consistent with UI tier definitions.
_HIGH_RISK_THRESHOLD = 70   # churn_risk_pct >= 70  → High Risk
_MED_RISK_LOWER = 40        # churn_risk_pct >= 40  → Medium Risk (lower bound)
_MED_RISK_UPPER = 70        # churn_risk_pct < 70   → Medium Risk (upper bound)

# Renewal window labels that indicate an account renews within 90 days.
_RENEWAL_WINDOW_LABELS = {"<30d", "30-90d"}


def compute_revenue_impact(predictions: list, account_statuses: dict, is_demo: bool) -> dict:
    """
    Compute platform-level revenue impact from available prediction state.

    Phase 1 logic:
      - Confirmed Saves: accounts explicitly marked "renewed" or "archived_renewed" by a CSM.
        Sum their ARR from the current prediction snapshot.
      - Risk Reduction: accounts whose arr_at_risk decreased (requires historical snapshots).
        Phase 1 has no persistent history, so this is 0 for real tenants.
      - Demo/Illustrative mode: when is_demo=True and no real saves exist, compute an
        illustrative estimate grounded entirely in arr_at_risk exposure. Clearly flagged.

    Illustrative demo formulas (all derived from arr_at_risk, not broad ARR):

      Estimated Renewal Retention:
        Pool: accounts with churn_risk_pct >= 40 AND renewal_window_label in {"<30d", "30-90d"}
        Formula: sum(arr_at_risk) × 0.35
        Rationale: 35% of the at-risk renewal pipeline is estimated to be retained through
        model-driven CSM intervention — a conservative modeled save rate.

      Estimated Risk Reduction:
        Pool: accounts with 40 <= churn_risk_pct < 70, NOT in the renewal window pool above
        Formula: sum(arr_at_risk) × 0.20
        Rationale: 20% arr_at_risk reduction from earlier, model-prompted outreach on
        medium-risk accounts before they enter the urgent renewal window.
        Only positive arr_at_risk values are counted (negative changes are ignored).
    """
    SAVE_STATUSES = {"renewed", "archived_renewed"}

    # Build arr_at_risk and ARR lookups keyed by account_id.
    arr_by_customer: dict[str, float] = {}
    for p in predictions:
        cid = p.get("account_id")
        if cid:
            arr_by_customer[cid] = float(p.get("arr", 0) or 0)

    # --- Confirmed Saves (real data from CSM status updates) ---
    confirmed_saves = 0.0
    confirmed_ids: set[str] = set()
    for cid, status in account_statuses.items():
        if status in SAVE_STATUSES:
            confirmed_saves += arr_by_customer.get(cid, 0)
            confirmed_ids.add(cid)

    # --- Risk Reduction (Phase 1: no historical snapshots → 0 for real tenants) ---
    risk_reduction = 0.0
    risk_reduced_ids: set[str] = set()

    illustrative = False

    # --- Demo illustrative fallback ---
    # Activates only when: is_demo=True, no real saves exist, and predictions are loaded.
    if is_demo and (confirmed_saves + risk_reduction == 0) and len(predictions) > 0:
        illustrative = True

        # Pool 1 — at-risk accounts renewing within 90 days (highest-leverage window).
        # churn_risk_pct >= 40 ensures only genuinely flagged accounts are counted.
        renewal_pool_ids: set[str] = set()
        for p in predictions:
            churn_risk_pct = p.get("churn_risk_pct") or 0
            renewal_label = p.get("renewal_window_label", "")
            arr_risk = float(p.get("arr_at_risk", 0) or 0)
            cid = p.get("account_id")

            if (
                churn_risk_pct >= _MED_RISK_LOWER
                and renewal_label in _RENEWAL_WINDOW_LABELS
                and arr_risk > 0
                and cid
            ):
                confirmed_saves += arr_risk * _ILLUSTRATIVE_RENEWAL_RETENTION_RATE
                confirmed_ids.add(cid)
                renewal_pool_ids.add(cid)

        # Pool 2 — medium-risk accounts (40 <= churn_risk_pct < 70) NOT in the renewal window.
        # Represents partial risk reduction from earlier model-prompted outreach.
        for p in predictions:
            churn_risk_pct = p.get("churn_risk_pct") or 0
            arr_risk = float(p.get("arr_at_risk", 0) or 0)
            cid = p.get("account_id")

            if (
                _MED_RISK_LOWER <= churn_risk_pct < _MED_RISK_UPPER
                and cid not in renewal_pool_ids
                and arr_risk > 0  # ignore zero/negative arr_at_risk (per spec)
                and cid
            ):
                risk_reduction += arr_risk * _ILLUSTRATIVE_RISK_REDUCTION_RATE
                risk_reduced_ids.add(cid)

    total_revenue_impact = confirmed_saves + risk_reduction
    accounts_impacted = len(confirmed_ids | risk_reduced_ids)

    # pending_history: real tenant with predictions loaded but no confirmed saves or
    # risk reduction yet. Distinct from illustrative (demo) and from having no predictions
    # at all. The frontend renders an explanatory empty state rather than a metric card.
    pending_history = (
        not is_demo
        and not illustrative
        and confirmed_saves == 0.0
        and risk_reduction == 0.0
        and len(predictions) > 0
    )

    if illustrative:
        label = "Estimated ARR Protected"
        subtext = "Based on synthetic data and model-driven assumptions"
    else:
        label = "Confirmed ARR Retained"
        subtext = "Accounts marked renewed by your team, confirmed against prediction data"

    return {
        "total_revenue_impact": round(total_revenue_impact, 2),
        "confirmed_saves": round(confirmed_saves, 2),
        "risk_reduction": round(risk_reduction, 2),
        "accounts_impacted": accounts_impacted,
        "is_demo": is_demo,
        "illustrative": illustrative,
        "pending_history": pending_history,
        "label": label,
        "subtext": subtext,
    }

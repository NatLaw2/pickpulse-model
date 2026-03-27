"""ARR Trajectory Engine.

Answers: "What will our ARR be in ~90 days, and which accounts will
determine whether we hit or miss?"

Design principles applied here:
  - No fake precision: only accounts with a real renewal date enter the forecast.
  - Trust > sophistication: expected-value math + Bernoulli variance band.
  - Transparent assumptions: every response carries an assumptions[] array.
  - Tie everything to ARR: all outputs are in dollars.

────────────────────────────────────────────────────────────────────────────
current_arr definition (canonical)
────────────────────────────────────────────────────────────────────────────
Sum of `arr` for every account where:
  - status = 'active'
  - arr IS NOT NULL

Accounts without a churn score are included (they're still generating revenue).
Accounts without a renewal date are included in current_arr but excluded from
the forecast (their future is unknown, not assumed zero).

────────────────────────────────────────────────────────────────────────────
Renewal date resolution (strict priority)
────────────────────────────────────────────────────────────────────────────
1. days_until_renewal   (exact: today + N days)
2. contract_months_remaining  (month-level only: first day of Nth future month)
3. No other source used. renewal_window label from churn_scores_daily is NOT
   used to derive a date — it's too coarse to assign a calendar position.

────────────────────────────────────────────────────────────────────────────
Forecast math
────────────────────────────────────────────────────────────────────────────
For each account renewing within the horizon that has a churn score and arr:

  expected_arr_lost_i     = arr_i × churn_probability_i
  expected_arr_retained_i = arr_i × (1 − churn_probability_i)

Base forecast:
  forecast_base = current_arr − Σ(expected_arr_lost_i)
                              + expansion_arr  (if expansion_rate > 0)

Expansion (applied only to low-risk renewing accounts, churn_prob < 0.30):
  expansion_arr = Σ(arr_i × expansion_rate  for accounts where churn_prob < 0.30)

Model uncertainty range (Bernoulli, independent accounts — see assumptions):
  variance_i   = churn_probability_i × (1 − churn_probability_i) × arr_i²
  total_std_dev = sqrt(Σ variance_i)
  lower_1sd    = forecast_base − total_std_dev
  upper_1sd    = forecast_base + total_std_dev

────────────────────────────────────────────────────────────────────────────
Expansion note
────────────────────────────────────────────────────────────────────────────
Expansion is applied only to accounts with churn_probability < 0.30.
Rationale: high-risk accounts are unlikely to expand; applying a flat rate
across all renewing accounts would overstate upside in a stressed portfolio.
"""
from __future__ import annotations

import calendar
import logging
import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Expansion is only applied to accounts below this churn probability threshold.
EXPANSION_LOW_RISK_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Date helpers (no external deps)
# ---------------------------------------------------------------------------

def _add_months(d: date, n: int) -> date:
    """Return the date that is n calendar months after d.

    Uses the same day of month where possible; clamps to the last day of the
    target month for months shorter than the source month.
    """
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Renewal date resolution
# ---------------------------------------------------------------------------

def _resolve_renewal_date(
    signals: Dict[str, Any],
    today: date,
) -> Tuple[Optional[date], Optional[str]]:
    """Derive a renewal date from account signals.

    Returns (renewal_date, precision) where precision is one of:
      "exact"          — from days_until_renewal
      "month_estimate" — from contract_months_remaining (day set to 1st of month)
      None             — no usable signal; account excluded from forecast

    Does NOT use renewal_window label — too coarse for calendar placement.
    """
    dur = signals.get("days_until_renewal")
    if dur is not None:
        try:
            days = int(float(dur))
            if days >= 0:
                return today + timedelta(days=days), "exact"
        except (ValueError, TypeError):
            pass

    cmr = signals.get("contract_months_remaining")
    if cmr is not None:
        try:
            months = int(float(cmr))
            if months >= 0:
                # Rough estimate: first day of that calendar month.
                renewal = _add_months(today, months).replace(day=1)
                return renewal, "month_estimate"
        except (ValueError, TypeError):
            pass

    return None, None


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_arr_forecast(
    tenant_id: str,
    horizon_days: int = 90,
    expansion_rate: float = 0.0,
) -> Dict[str, Any]:
    """Compute the ARR trajectory forecast for a tenant.

    Args:
        tenant_id:      Tenant to compute for.
        horizon_days:   Look-ahead window in days (default 90).
        expansion_rate: Fractional uplift applied to low-risk renewing accounts
                        (churn_prob < 0.30). Default 0.0 (no expansion assumed).

    Returns a dict ready for JSON serialization. See module docstring for
    field definitions and assumptions.
    """
    from app.storage.repo import latest_scores, list_accounts, bulk_latest_signals

    today = date.today()
    horizon_date = today + timedelta(days=horizon_days)

    # ------------------------------------------------------------------
    # 1. current_arr — all active accounts with non-null arr
    # ------------------------------------------------------------------
    all_accounts = list_accounts(limit=5000, tenant_id=tenant_id)
    current_arr: float = sum(
        float(a["arr"])
        for a in all_accounts
        if a.get("status") == "active" and a.get("arr") is not None
    )
    total_active_accounts = sum(
        1 for a in all_accounts if a.get("status") == "active"
    )

    # ------------------------------------------------------------------
    # 2. Scored accounts — churn_probability + arr per account
    # ------------------------------------------------------------------
    scores = latest_scores(limit=5000, tenant_id=tenant_id)

    # Most recent score date across all scored accounts (for the assumptions note).
    scored_as_of: Optional[str] = None
    for s in scores:
        d = s.get("score_date")
        if d and (scored_as_of is None or str(d) > scored_as_of):
            scored_as_of = str(d)

    # Index by account_id for signal lookup.
    score_by_account: Dict[str, Dict[str, Any]] = {
        s["account_id"]: s for s in scores if s.get("account_id")
    }

    # ------------------------------------------------------------------
    # 3. Signals — renewal dates
    # ------------------------------------------------------------------
    signals_by_account = bulk_latest_signals(tenant_id=tenant_id)

    # ------------------------------------------------------------------
    # 4. Build forecast dataset
    #    Only accounts that have:
    #      - a renewal date falling within [today, horizon_date]
    #      - a churn score
    #      - a non-null arr > 0
    # ------------------------------------------------------------------
    forecast_accounts: List[Dict[str, Any]] = []
    n_no_renewal_date = 0
    n_no_score = 0
    n_no_arr = 0

    # Work from scored accounts — they're the ones we can forecast.
    for account_id, score in score_by_account.items():
        arr = score.get("arr")
        if arr is None or float(arr) <= 0:
            n_no_arr += 1
            continue

        arr_f = float(arr)
        churn_prob = float(score.get("churn_probability", 0))
        signals = signals_by_account.get(account_id, {})

        renewal_date, precision = _resolve_renewal_date(signals, today)

        if renewal_date is None:
            n_no_renewal_date += 1
            continue

        if not (today <= renewal_date <= horizon_date):
            # Renewal exists but outside this forecast window.
            continue

        n_no_score = n_no_score  # already have a score — no-op placeholder

        forecast_accounts.append({
            "account_id": account_id,
            "name": score.get("name"),
            "arr": arr_f,
            "churn_probability": churn_prob,
            "renewal_date": renewal_date.isoformat(),
            "renewal_month": _month_key(renewal_date),
            "renewal_date_precision": precision,
            "expected_arr_lost": arr_f * churn_prob,
            "expected_arr_retained": arr_f * (1.0 - churn_prob),
        })

    # ------------------------------------------------------------------
    # 5. Compute base forecast
    # ------------------------------------------------------------------
    total_arr_renewing = sum(a["arr"] for a in forecast_accounts)
    total_expected_lost = sum(a["expected_arr_lost"] for a in forecast_accounts)

    # Expansion: only low-risk accounts (churn_prob < threshold)
    expansion_arr: float = 0.0
    if expansion_rate > 0.0:
        expansion_arr = sum(
            a["arr"] * expansion_rate
            for a in forecast_accounts
            if a["churn_probability"] < EXPANSION_LOW_RISK_THRESHOLD
        )

    forecast_base = current_arr - total_expected_lost + expansion_arr

    # ------------------------------------------------------------------
    # 6. Model uncertainty range (Bernoulli, independent accounts)
    # ------------------------------------------------------------------
    total_variance = sum(
        a["churn_probability"] * (1.0 - a["churn_probability"]) * (a["arr"] ** 2)
        for a in forecast_accounts
    )
    std_dev = math.sqrt(total_variance) if total_variance > 0 else 0.0
    lower_1sd = forecast_base - std_dev
    upper_1sd = forecast_base + std_dev

    # ------------------------------------------------------------------
    # 7. Renewal calendar — group by month
    # ------------------------------------------------------------------
    calendar_buckets: Dict[str, Dict[str, Any]] = {}
    for a in forecast_accounts:
        m = a["renewal_month"]
        if m not in calendar_buckets:
            calendar_buckets[m] = {
                "month": m,
                "arr_renewing": 0.0,
                "expected_arr_lost": 0.0,
                "expected_arr_retained": 0.0,
                "account_count": 0,
                # True if any account in this month used a month-level estimate
                # rather than an exact days_until_renewal signal.
                "has_month_estimates": False,
            }
        b = calendar_buckets[m]
        b["arr_renewing"] += a["arr"]
        b["expected_arr_lost"] += a["expected_arr_lost"]
        b["expected_arr_retained"] += a["expected_arr_retained"]
        b["account_count"] += 1
        if a["renewal_date_precision"] == "month_estimate":
            b["has_month_estimates"] = True

    renewal_calendar = sorted(calendar_buckets.values(), key=lambda x: x["month"])

    # ------------------------------------------------------------------
    # 8. Top at-risk accounts (by expected_arr_lost descending)
    # ------------------------------------------------------------------
    top_at_risk = sorted(
        forecast_accounts,
        key=lambda a: a["expected_arr_lost"],
        reverse=True,
    )[:10]

    # Strip internal fields not needed in response
    top_at_risk_out = [
        {
            "account_id": a["account_id"],
            "name": a["name"],
            "arr": a["arr"],
            "churn_probability": a["churn_probability"],
            "expected_arr_at_risk": round(a["expected_arr_lost"], 2),
            "renewal_date": a["renewal_date"],
            "renewal_date_precision": a["renewal_date_precision"],
        }
        for a in top_at_risk
    ]

    # ------------------------------------------------------------------
    # 9. Coverage stats
    # ------------------------------------------------------------------
    arr_in_forecast = total_arr_renewing
    arr_excluded = current_arr - arr_in_forecast  # ARR with unknown future
    arr_coverage_pct = (arr_in_forecast / current_arr * 100) if current_arr > 0 else 0.0

    n_month_estimates = sum(
        1 for a in forecast_accounts if a["renewal_date_precision"] == "month_estimate"
    )

    coverage = {
        "total_active_accounts": total_active_accounts,
        "accounts_in_forecast": len(forecast_accounts),
        "accounts_scored_no_renewal_date": n_no_renewal_date,
        "accounts_scored_no_arr": n_no_arr,
        # How many accounts in the forecast used a month-level estimate rather
        # than an exact days_until_renewal signal. Surfaces date quality to UI.
        "n_month_estimates": n_month_estimates,
        "arr_in_forecast": round(arr_in_forecast, 2),
        "arr_excluded": round(arr_excluded, 2),
        "arr_coverage_pct": round(arr_coverage_pct, 1),
    }

    # ------------------------------------------------------------------
    # 10. Assumptions array — transparent and auditable
    # ------------------------------------------------------------------
    assumptions = [
        (
            "current_arr is the sum of arr for all active accounts with a non-null arr value. "
            "It includes accounts without churn scores and accounts without renewal dates."
        ),
        (
            f"Forecast covers accounts whose renewal date falls within the next "
            f"{horizon_days} days (by {horizon_date.isoformat()}). "
            f"Accounts without a scoreable renewal date are excluded from the forecast "
            f"but are included in current_arr."
        ),
        (
            "Renewal dates are derived from days_until_renewal (exact) or "
            "contract_months_remaining (month-level estimate only, day set to 1st of month). "
            "No other source is used. Accounts with neither signal are excluded."
        ),
        (
            "Model uncertainty range (lower_1sd / upper_1sd) is computed as ±1 standard "
            "deviation using a per-account Bernoulli model assuming independent churn events. "
            "This is a statistical forecast range, not a guaranteed confidence interval. "
            "Correlated events such as a macro downturn or product incident are not modeled "
            "and can produce outcomes outside this range."
        ),
        (
            f"Expansion rate {expansion_rate:.1%} is applied only to accounts with "
            f"churn_probability < {EXPANSION_LOW_RISK_THRESHOLD:.0%} (low-risk accounts "
            f"likely to renew and grow). Expansion is set to 0.0 by default."
        )
        if expansion_rate > 0.0
        else (
            "No expansion is assumed (expansion_rate = 0.0). "
            "Set expansion_rate > 0.0 to model upsell on low-risk renewing accounts."
        ),
        f"Churn scores as of: {scored_as_of or 'unknown — no accounts scored yet'}.",
    ]

    return {
        "as_of": today.isoformat(),
        "horizon_days": horizon_days,
        "horizon_date": horizon_date.isoformat(),
        "current_arr": round(current_arr, 2),
        "forecast": {
            "base": round(forecast_base, 2),
            "lower_1sd": round(lower_1sd, 2),
            "upper_1sd": round(upper_1sd, 2),
            "std_dev": round(std_dev, 2),
        },
        "arr_at_risk": round(total_expected_lost, 2),
        "arr_renewing": round(total_arr_renewing, 2),
        "expansion_arr": round(expansion_arr, 2),
        "expansion_rate": expansion_rate,
        "renewal_calendar": renewal_calendar,
        "top_at_risk": top_at_risk_out,
        "coverage": coverage,
        "arr_coverage_pct": round(arr_coverage_pct, 1),
        "assumptions": assumptions,
    }

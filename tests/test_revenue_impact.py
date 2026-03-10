"""Tests for the Revenue Impact Tracker calculation logic."""
import sys
import os
import pytest

# Allow importing app module from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.revenue_impact import compute_revenue_impact as _compute_revenue_impact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_prediction(
    customer_id: str,
    arr: float,
    churn_risk_pct: float,
    arr_at_risk: float | None = None,
    renewal_window_label: str = ">90d",
) -> dict:
    if arr_at_risk is None:
        arr_at_risk = arr * (churn_risk_pct / 100)
    return {
        "customer_id": customer_id,
        "arr": arr,
        "churn_risk_pct": churn_risk_pct,
        "arr_at_risk": arr_at_risk,
        "renewal_window_label": renewal_window_label,
    }


# ---------------------------------------------------------------------------
# Confirmed Saves (real data)
# ---------------------------------------------------------------------------

def test_confirmed_save_renewed_status():
    """Accounts with status 'renewed' contribute their ARR to confirmed_saves."""
    predictions = [make_prediction("acct-1", arr=100_000, churn_risk_pct=75)]
    account_statuses = {"acct-1": "renewed"}

    result = _compute_revenue_impact(predictions, account_statuses, is_demo=False)

    assert result["confirmed_saves"] == 100_000.0
    assert result["risk_reduction"] == 0.0
    assert result["total_revenue_impact"] == 100_000.0
    assert result["accounts_impacted"] == 1


def test_confirmed_save_archived_renewed_status():
    """Accounts with status 'archived_renewed' also count as confirmed saves."""
    predictions = [make_prediction("acct-2", arr=50_000, churn_risk_pct=80)]
    account_statuses = {"acct-2": "archived_renewed"}

    result = _compute_revenue_impact(predictions, account_statuses, is_demo=False)

    assert result["confirmed_saves"] == 50_000.0
    assert result["accounts_impacted"] == 1


def test_multiple_confirmed_saves_summed():
    """Multiple renewed accounts are summed together."""
    predictions = [
        make_prediction("a1", arr=200_000, churn_risk_pct=70),
        make_prediction("a2", arr=150_000, churn_risk_pct=65),
        make_prediction("a3", arr=80_000, churn_risk_pct=50),
    ]
    account_statuses = {"a1": "renewed", "a2": "renewed"}

    result = _compute_revenue_impact(predictions, account_statuses, is_demo=False)

    assert result["confirmed_saves"] == 350_000.0
    assert result["accounts_impacted"] == 2


def test_non_renewed_statuses_excluded():
    """Accounts with 'active', 'churned', etc. do NOT count as confirmed saves."""
    predictions = [
        make_prediction("a1", arr=100_000, churn_risk_pct=80),
        make_prediction("a2", arr=60_000, churn_risk_pct=45),
    ]
    account_statuses = {"a1": "active", "a2": "churned"}

    result = _compute_revenue_impact(predictions, account_statuses, is_demo=False)

    assert result["confirmed_saves"] == 0.0
    assert result["total_revenue_impact"] == 0.0


def test_account_without_prediction_contributes_zero_arr():
    """A renewed account not present in predictions contributes $0 ARR (no ARR to look up)."""
    predictions = [make_prediction("acct-known", arr=100_000, churn_risk_pct=70)]
    account_statuses = {"acct-unknown": "renewed"}

    result = _compute_revenue_impact(predictions, account_statuses, is_demo=False)

    assert result["confirmed_saves"] == 0.0


# ---------------------------------------------------------------------------
# Risk Reduction (Phase 1 — always 0 for real tenants without history)
# ---------------------------------------------------------------------------

def test_risk_reduction_zero_without_history():
    """Phase 1: no historical snapshots means risk_reduction is 0 for real tenants."""
    predictions = [
        make_prediction("a1", arr=500_000, churn_risk_pct=60, arr_at_risk=300_000),
        make_prediction("a2", arr=200_000, churn_risk_pct=45, arr_at_risk=90_000),
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=False)

    assert result["risk_reduction"] == 0.0


# ---------------------------------------------------------------------------
# Demo / Illustrative mode — new arr_at_risk-grounded formulas
# ---------------------------------------------------------------------------

def test_illustrative_uses_only_arr_at_risk_not_low_risk_arr():
    """
    Illustrative calculation must NOT count low-risk (churn_risk_pct < 40) ARR.
    Only at-risk accounts (churn_risk_pct >= 40) contribute to illustrative estimates.
    """
    predictions = [
        # Low-risk — should contribute nothing
        make_prediction("low-1", arr=500_000, churn_risk_pct=15, arr_at_risk=75_000),
        # At-risk, renewing → renewal retention pool
        make_prediction("high-1", arr=100_000, churn_risk_pct=75, arr_at_risk=75_000,
                        renewal_window_label="<30d"),
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=True)

    assert result["illustrative"] is True
    # Only high-1's arr_at_risk contributes: $75k × 0.35 = $26,250
    assert result["confirmed_saves"] == pytest.approx(26_250.0)
    # low-1 is excluded entirely
    assert result["risk_reduction"] == 0.0


def test_demo_mode_renewal_retention_pool():
    """
    Estimated Renewal Retention: churn_risk_pct >= 40 AND renewal_window_label in {<30d, 30-90d}.
    Formula: arr_at_risk × 0.35
    """
    predictions = [
        make_prediction("r1", arr=200_000, churn_risk_pct=75, arr_at_risk=150_000,
                        renewal_window_label="<30d"),
        make_prediction("r2", arr=100_000, churn_risk_pct=55, arr_at_risk=55_000,
                        renewal_window_label="30-90d"),
        make_prediction("r3", arr=80_000,  churn_risk_pct=85, arr_at_risk=68_000,
                        renewal_window_label=">90d"),   # not in renewal window → excluded from pool 1
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=True)

    # r1 + r2 are in the renewal window pool: (150k + 55k) × 0.35 = 71,750
    assert result["confirmed_saves"] == pytest.approx(71_750.0)


def test_demo_mode_risk_reduction_pool():
    """
    Estimated Risk Reduction: 40 <= churn_risk_pct < 70, NOT in renewal window.
    Formula: arr_at_risk × 0.20
    """
    predictions = [
        make_prediction("m1", arr=200_000, churn_risk_pct=55, arr_at_risk=110_000,
                        renewal_window_label=">90d"),   # medium, not renewing → risk reduction pool
        make_prediction("m2", arr=150_000, churn_risk_pct=45, arr_at_risk=67_500,
                        renewal_window_label=">90d"),
        make_prediction("h1", arr=300_000, churn_risk_pct=80, arr_at_risk=240_000,
                        renewal_window_label=">90d"),   # high risk (>=70) → excluded from pool 2
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=True)

    # m1 + m2 qualify: (110k + 67.5k) × 0.20 = 35,500
    assert result["risk_reduction"] == pytest.approx(35_500.0)
    # h1 does not qualify for pool 2 (churn_risk_pct >= 70)
    # confirmed_saves is 0 (no renewal window accounts)
    assert result["confirmed_saves"] == 0.0


def test_demo_mode_renewal_window_account_excluded_from_risk_reduction_pool():
    """
    An account in the renewal window pool (Pool 1) must NOT also appear in Pool 2.
    """
    predictions = [
        make_prediction("m1", arr=100_000, churn_risk_pct=55, arr_at_risk=55_000,
                        renewal_window_label="30-90d"),   # medium AND renewing → Pool 1 only
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=True)

    # Pool 1: 55k × 0.35 = 19,250
    assert result["confirmed_saves"] == pytest.approx(19_250.0)
    # Pool 2: excluded (already in renewal pool)
    assert result["risk_reduction"] == 0.0
    assert result["accounts_impacted"] == 1


def test_demo_mode_activates_illustrative_when_no_real_saves():
    """With is_demo=True and no real saves, illustrative flag is set and totals are non-zero."""
    predictions = [
        make_prediction("r1", arr=200_000, churn_risk_pct=75, arr_at_risk=150_000,
                        renewal_window_label="<30d"),
        make_prediction("m1", arr=100_000, churn_risk_pct=50, arr_at_risk=50_000,
                        renewal_window_label=">90d"),
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=True)

    assert result["illustrative"] is True
    assert result["is_demo"] is True
    # r1 → Pool 1: 150k × 0.35 = 52,500
    assert result["confirmed_saves"] == pytest.approx(52_500.0)
    # m1 → Pool 2: 50k × 0.20 = 10,000
    assert result["risk_reduction"] == pytest.approx(10_000.0)
    assert result["total_revenue_impact"] == pytest.approx(62_500.0)
    assert result["accounts_impacted"] == 2


def test_demo_mode_does_not_activate_if_real_saves_exist():
    """If there are real confirmed saves, illustrative mode stays off even in demo."""
    predictions = [make_prediction("a1", arr=100_000, churn_risk_pct=75)]
    account_statuses = {"a1": "renewed"}

    result = _compute_revenue_impact(predictions, account_statuses, is_demo=True)

    assert result["illustrative"] is False
    assert result["confirmed_saves"] == 100_000.0


def test_demo_mode_no_predictions_stays_zero():
    """Demo mode with empty predictions produces zero impact (no data to estimate from)."""
    result = _compute_revenue_impact([], {}, is_demo=True)

    assert result["total_revenue_impact"] == 0.0
    assert result["illustrative"] is False


# ---------------------------------------------------------------------------
# Negative / zero arr_at_risk ignored (per spec)
# ---------------------------------------------------------------------------

def test_negative_arr_at_risk_ignored_in_illustrative():
    """Accounts with zero or negative arr_at_risk are not counted in either pool."""
    predictions = [
        make_prediction("m1", arr=100_000, churn_risk_pct=50, arr_at_risk=0,
                        renewal_window_label="<30d"),
        make_prediction("m2", arr=80_000,  churn_risk_pct=55, arr_at_risk=-5_000,
                        renewal_window_label=">90d"),
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=True)

    assert result["confirmed_saves"] == 0.0
    assert result["risk_reduction"] == 0.0
    assert result["total_revenue_impact"] == 0.0


# ---------------------------------------------------------------------------
# Response shape and labels
# ---------------------------------------------------------------------------

def test_response_has_all_required_fields():
    """Response always includes all required keys."""
    result = _compute_revenue_impact([], {}, is_demo=False)

    required_keys = {
        "total_revenue_impact", "confirmed_saves", "risk_reduction",
        "accounts_impacted", "is_demo", "illustrative", "label", "subtext",
    }
    assert required_keys.issubset(result.keys())


def test_real_mode_label_and_subtext():
    """Non-illustrative mode returns correct label and subtext."""
    result = _compute_revenue_impact([], {}, is_demo=False)

    assert result["label"] == "Revenue Impact"
    assert "confirmed renewals" in result["subtext"]


def test_illustrative_mode_label_is_estimated_arr_protected():
    """Illustrative mode main label must be 'Estimated ARR Protected'."""
    predictions = [
        make_prediction("r1", arr=100_000, churn_risk_pct=70, arr_at_risk=70_000,
                        renewal_window_label="<30d"),
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=True)

    assert result["label"] == "Estimated ARR Protected"


def test_illustrative_mode_subtext_references_assumptions():
    """Illustrative subtext must reference synthetic data and model-driven assumptions."""
    predictions = [
        make_prediction("r1", arr=100_000, churn_risk_pct=70, arr_at_risk=70_000,
                        renewal_window_label="<30d"),
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=True)

    assert "synthetic" in result["subtext"].lower()
    assert "assumption" in result["subtext"].lower()


def test_accounts_impacted_deduped():
    """An account in Pool 1 is not double-counted in Pool 2."""
    predictions = [
        make_prediction("a1", arr=100_000, churn_risk_pct=55, arr_at_risk=55_000,
                        renewal_window_label="30-90d"),
    ]
    result = _compute_revenue_impact(predictions, {}, is_demo=True)

    assert result["accounts_impacted"] == 1

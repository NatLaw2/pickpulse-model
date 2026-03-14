"""Tests for the schema mapping alias engine."""
import pandas as pd
import pytest

from app.engine.schema_mapping import suggest_mapping, HIGH, MEDIUM, LOW, NONE


def _df(**kwargs) -> pd.DataFrame:
    """Create a minimal DataFrame with the given column names."""
    n = max(len(v) for v in kwargs.values()) if kwargs else 3
    return pd.DataFrame({k: ([None] * n if not v else v) for k, v in kwargs.items()})


# ---------------------------------------------------------------------------
# Tier 1a — exact match
# ---------------------------------------------------------------------------

def test_exact_match_account_id():
    df = _df(account_id=["A1", "A2"])
    s = suggest_mapping(df)
    assert s.suggested["account_id"] == "account_id"
    assert s.confidence["account_id"] == HIGH


def test_exact_match_case_insensitive():
    df = _df(Account_ID=["A1", "A2"])
    s = suggest_mapping(df)
    assert s.suggested["account_id"] == "Account_ID"
    assert s.confidence["account_id"] in (HIGH, MEDIUM)


# ---------------------------------------------------------------------------
# Tier 1b / 2 — alias matches
# ---------------------------------------------------------------------------

def test_alias_customer_id():
    df = _df(customer_id=["C1", "C2"])
    s = suggest_mapping(df)
    assert s.suggested["account_id"] == "customer_id"


def test_alias_canceled_maps_to_churned():
    df = _df(account_id=["A"], canceled=[1])
    s = suggest_mapping(df)
    assert s.suggested["churned"] == "canceled"
    assert s.confidence["churned"] in (MEDIUM, HIGH)


def test_alias_cancelled_maps_to_churned():
    df = _df(account_id=["A"], cancelled=[1])
    s = suggest_mapping(df)
    assert s.suggested["churned"] == "cancelled"


def test_alias_arr_usd():
    df = _df(account_id=["A"], arr_usd=[1000])
    s = suggest_mapping(df)
    assert s.suggested["arr"] == "arr_usd"


def test_alias_contract_end_maps_to_renewal_date():
    df = _df(account_id=["A"], contract_end=["2025-01-01"])
    s = suggest_mapping(df)
    assert s.suggested["renewal_date"] == "contract_end"


def test_alias_monthly_logins_maps_to_login_days_30d():
    df = _df(account_id=["A"], monthly_logins=[10])
    s = suggest_mapping(df)
    assert s.suggested["login_days_30d"] == "monthly_logins"


def test_alias_active_users_30d():
    df = _df(account_id=["A"], active_users_30d=[5])
    s = suggest_mapping(df)
    assert s.suggested["seats_active_30d"] == "active_users_30d"


def test_alias_mau():
    df = _df(account_id=["A"], mau=[42])
    s = suggest_mapping(df)
    assert s.suggested["seats_active_30d"] == "mau"


def test_alias_plan_maps_to_plan_type():
    df = _df(account_id=["A"], plan=["Pro"])
    s = suggest_mapping(df)
    assert s.suggested["plan_type"] == "plan"


def test_alias_account_name_maps_to_company_name():
    df = _df(account_id=["A"], account_name=["Acme"])
    s = suggest_mapping(df)
    assert s.suggested["company_name"] == "account_name"


# ---------------------------------------------------------------------------
# Multiple fields together
# ---------------------------------------------------------------------------

def test_realistic_salesforce_export():
    """Column names typical of a Salesforce Accounts export."""
    df = _df(
        AccountId=["A1", "A2"],
        ReportDate=["2024-01-01", "2024-01-01"],
        IsCanceled=[0, 1],
        AnnualRevenue=[50000, 120000],
        ContractEndDate=["2025-06-01", "2025-03-01"],
        MonthlyLogins=[20, 5],
        AccountName=["Acme", "BetaCo"],
    )
    s = suggest_mapping(df)
    assert s.suggested["account_id"] == "AccountId"
    assert s.suggested["snapshot_date"] == "ReportDate"
    assert s.suggested["churned"] == "IsCanceled"
    assert s.suggested["arr"] == "AnnualRevenue"
    assert s.suggested["renewal_date"] == "ContractEndDate"
    assert s.suggested["login_days_30d"] == "MonthlyLogins"
    assert s.suggested["company_name"] == "AccountName"


def test_hubbspot_style_export():
    df = _df(
        customerid=["C1"],
        record_date=["2024-06-01"],
        churned=["no"],
        mrr_usd=[500],
        expiration_date=["2025-01-01"],
        tickets=[3],
        tier=["Pro"],
        csm=["Jane"],
    )
    s = suggest_mapping(df)
    assert s.suggested["account_id"] == "customerid"
    assert s.suggested["snapshot_date"] == "record_date"
    assert s.suggested["churned"] == "churned"
    assert s.suggested["mrr"] == "mrr_usd"
    assert s.suggested["renewal_date"] == "expiration_date"
    assert s.suggested["support_tickets_30d"] == "tickets"
    assert s.suggested["plan_type"] == "tier"
    assert s.suggested["csm_owner"] == "csm"


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------

def test_missing_required_when_churned_absent():
    df = _df(account_id=["A"], snapshot_date=["2024-01-01"])
    s = suggest_mapping(df)
    assert "churned" in s.missing_required_for_training


def test_missing_required_when_account_id_absent():
    df = _df(date=["2024-01-01"], churned=[0])
    s = suggest_mapping(df)
    assert "account_id" in s.missing_required_for_training
    assert "account_id" in s.missing_required_for_analysis


# ---------------------------------------------------------------------------
# Tier 3 — heuristic detection
# ---------------------------------------------------------------------------

def test_heuristic_binary_column_detected_as_churned():
    df = _df(account_id=["A1", "A2", "A3"], outcome=["yes", "no", "yes"])
    s = suggest_mapping(df)
    assert s.suggested["churned"] == "outcome"
    assert s.confidence["churned"] == LOW


def test_heuristic_does_not_fire_for_high_cardinality():
    """A high-cardinality string column should not be confused with churned."""
    df = _df(
        account_id=["A1", "A2", "A3"],
        notes=["Meeting scheduled", "Contract renewed", "No response yet"],
    )
    s = suggest_mapping(df)
    assert s.suggested["churned"] is None


# ---------------------------------------------------------------------------
# No double-mapping
# ---------------------------------------------------------------------------

def test_no_double_mapping_single_column():
    """A single source column should only be claimed by one canonical field."""
    df = _df(customer_id=["A1"])  # matches account_id alias
    s = suggest_mapping(df)
    claimed = [v for v in s.suggested.values() if v == "customer_id"]
    assert len(claimed) == 1


# ---------------------------------------------------------------------------
# Unmapped source columns
# ---------------------------------------------------------------------------

def test_unmapped_columns_reported():
    df = _df(account_id=["A"], random_field_xyz=[1])
    s = suggest_mapping(df)
    assert "random_field_xyz" in s.unmapped_source_cols

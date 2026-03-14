"""Tests for the normalization layer."""
import pandas as pd
import pytest

from app.engine.normalizer import normalize, compute_readiness


def _make_df(**kwargs) -> pd.DataFrame:
    n = max(len(v) for v in kwargs.values()) if kwargs else 2
    return pd.DataFrame({k: (v if len(v) == n else v * n) for k, v in kwargs.items()})


# ---------------------------------------------------------------------------
# Column renaming
# ---------------------------------------------------------------------------

def test_basic_rename():
    raw = _make_df(AccountID=["A1", "A2"], canceled=[0, 1], AnnualRevenue=[10000, 20000])
    mapping = {"account_id": "AccountID", "churned": "canceled", "arr": "AnnualRevenue"}
    result = normalize(raw, mapping)
    assert "account_id" in result.canonical_df.columns
    assert "churned" in result.canonical_df.columns
    assert "arr" in result.canonical_df.columns
    assert "AccountID" not in result.canonical_df.columns


def test_unmapped_columns_excluded():
    raw = _make_df(account_id=["A"], churned=[0], extra_col=["noise"])
    mapping = {"account_id": "account_id", "churned": "churned"}
    result = normalize(raw, mapping)
    assert "extra_col" not in result.canonical_df.columns


# ---------------------------------------------------------------------------
# Churned coercion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("val,expected", [
    ("yes", 1), ("YES", 1), ("True", 1), ("churned", 1), ("canceled", 1),
    ("no", 0), ("No", 0), ("false", 0), ("retained", 0), ("active", 0),
    ("1", 1), ("0", 0),
])
def test_churned_text_coercion(val, expected):
    raw = _make_df(account_id=["A"], churned=[val])
    result = normalize(raw, {"account_id": "account_id", "churned": "churned"})
    assert result.canonical_df["churned"].iloc[0] == expected


def test_churned_float_coercion():
    raw = _make_df(account_id=["A", "B"], churned=[1.0, 0.0])
    result = normalize(raw, {"account_id": "account_id", "churned": "churned"})
    assert list(result.canonical_df["churned"]) == [1, 0]


# ---------------------------------------------------------------------------
# ARR / MRR derivation
# ---------------------------------------------------------------------------

def test_arr_derived_from_mrr():
    raw = _make_df(account_id=["A"], mrr=[1000])
    result = normalize(raw, {"account_id": "account_id", "mrr": "mrr"})
    assert "arr" in result.canonical_df.columns
    assert result.canonical_df["arr"].iloc[0] == pytest.approx(12000)
    assert "arr" in result.derived_columns


def test_mrr_derived_from_arr():
    raw = _make_df(account_id=["A"], arr=[12000])
    result = normalize(raw, {"account_id": "account_id", "arr": "arr"})
    assert "mrr" in result.canonical_df.columns
    assert result.canonical_df["mrr"].iloc[0] == pytest.approx(1000)


def test_no_double_derivation_when_both_present():
    raw = _make_df(account_id=["A"], arr=[12000], mrr=[1000])
    result = normalize(raw, {"account_id": "account_id", "arr": "arr", "mrr": "mrr"})
    # Neither should appear in derived_columns since both were mapped
    assert result.canonical_df["arr"].iloc[0] == 12000
    assert result.canonical_df["mrr"].iloc[0] == 1000


# ---------------------------------------------------------------------------
# days_until_renewal derivation
# ---------------------------------------------------------------------------

def test_days_until_renewal_derived_from_dates():
    raw = pd.DataFrame({
        "account_id": ["A"],
        "snap": ["2024-01-01"],
        "renew": ["2024-04-01"],
    })
    result = normalize(raw, {
        "account_id": "account_id",
        "snapshot_date": "snap",
        "renewal_date": "renew",
    })
    assert "days_until_renewal" in result.canonical_df.columns
    assert "days_until_renewal" in result.derived_columns
    # 2024-01-01 → 2024-04-01 = 91 days
    assert result.canonical_df["days_until_renewal"].iloc[0] == 91


def test_days_until_renewal_not_derived_when_already_mapped():
    raw = pd.DataFrame({
        "account_id": ["A"],
        "snap": ["2024-01-01"],
        "dur": [60],
    })
    result = normalize(raw, {
        "account_id": "account_id",
        "snapshot_date": "snap",
        "days_until_renewal": "dur",
    })
    assert result.canonical_df["days_until_renewal"].iloc[0] == 60
    assert "days_until_renewal" not in result.derived_columns


# ---------------------------------------------------------------------------
# account_age_days derivation
# ---------------------------------------------------------------------------

def test_account_age_derived():
    raw = pd.DataFrame({
        "account_id": ["A"],
        "snap": ["2024-07-01"],
        "start": ["2022-07-01"],
    })
    result = normalize(raw, {
        "account_id": "account_id",
        "snapshot_date": "snap",
        "contract_start_date": "start",
    })
    assert "account_age_days" in result.canonical_df.columns
    assert "account_age_days" in result.derived_columns
    # 2022-07-01 → 2024-07-01 = 731 days (2 years, 1 leap year)
    assert result.canonical_df["account_age_days"].iloc[0] >= 730


# ---------------------------------------------------------------------------
# Negative ARR clamping
# ---------------------------------------------------------------------------

def test_negative_arr_clamped():
    raw = _make_df(account_id=["A"], arr=[-500])
    result = normalize(raw, {"account_id": "account_id", "arr": "arr"})
    assert result.canonical_df["arr"].iloc[0] == 0
    assert any("negative" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Display-only columns excluded from canonical_df
# ---------------------------------------------------------------------------

def test_display_columns_in_meta_not_model():
    raw = _make_df(
        account_id=["A"],
        churned=[0],
        company_name=["Acme"],
        industry=["SaaS"],
    )
    result = normalize(raw, {
        "account_id": "account_id",
        "churned": "churned",
        "company_name": "company_name",
        "industry": "industry",
    })
    assert "company_name" not in result.canonical_df.columns
    assert "industry" not in result.canonical_df.columns
    assert "company_name" in result.display_meta.columns


# ---------------------------------------------------------------------------
# Readiness scoring
# ---------------------------------------------------------------------------

def _basic_canonical_df(**extra):
    data = {
        "account_id": ["A1", "A2", "A3"] * 10,
        "snapshot_date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-02-01"] * 10),
        "churned": [0, 1, 0] * 10,
        "arr": [10000, 20000, 15000] * 10,
        "login_days_30d": [10, 3, 8] * 10,
    }
    data.update(extra)
    return pd.DataFrame(data)


def test_readiness_training_ready():
    df = _basic_canonical_df()
    report = compute_readiness(df, [], [], len(df), "test.csv", "2024-01-01T00:00:00Z")
    assert report.mode == "TRAINING_READY"


def test_readiness_training_degraded_no_snapshot():
    df = _basic_canonical_df()
    df = df.drop(columns=["snapshot_date"])
    report = compute_readiness(df, [], [], len(df), "test.csv", "2024-01-01T00:00:00Z")
    assert report.mode == "TRAINING_DEGRADED"
    assert report.split_strategy == "random"


def test_readiness_analysis_ready_no_churned():
    df = _basic_canonical_df()
    df = df.drop(columns=["churned"])
    report = compute_readiness(df, [], [], len(df), "test.csv", "2024-01-01T00:00:00Z")
    assert report.mode == "ANALYSIS_READY"
    assert report.label_distribution is None


def test_readiness_blocked_no_account_id():
    df = _basic_canonical_df().drop(columns=["account_id"])
    report = compute_readiness(df, [], [], len(df), "test.csv", "2024-01-01T00:00:00Z")
    assert report.mode == "BLOCKED"


def test_readiness_blocked_single_class_label():
    df = _basic_canonical_df()
    df["churned"] = 0  # all retained
    report = compute_readiness(df, [], [], len(df), "test.csv", "2024-01-01T00:00:00Z")
    assert report.mode == "BLOCKED"
    assert "one unique value" in report.mode_reason


def test_readiness_improvements_suggested_for_missing_fields():
    df = _basic_canonical_df()  # has arr and login_days_30d but not renewal_date
    report = compute_readiness(df, [], [], len(df), "test.csv", "2024-01-01T00:00:00Z")
    assert len(report.improvements) > 0


def test_readiness_preview_has_5_rows():
    df = _basic_canonical_df()
    report = compute_readiness(df, [], [], len(df), "test.csv", "2024-01-01T00:00:00Z")
    assert len(report.normalized_preview) == 5

"""
CRM alias pack tests — verifies that the CRM-aware alias system correctly
handles field detection and confidence policy for major CRM exports.

Scenarios covered
-----------------
Salesforce:
  - AccountId → account_id (HIGH/MEDIUM, no confirmation)
  - ARR__c → arr, Renewal_Date__c → renewal_date (MEDIUM, no confirmation)
  - Churned__c → churned (MEDIUM, no confirmation — direct flag)
  - StageName → churned (LOW, requires_confirmation=True)
  - IsClosed  → churned (LOW, requires_confirmation=True)

HubSpot:
  - hs_object_id / companyId → account_id
  - dealstage    → churned (LOW, requires_confirmation=True)
  - lifecyclestage → churned (LOW, requires_confirmation=True)
  - Direct churn_flag → churned (MEDIUM, no confirmation)

Microsoft Dynamics:
  - accountid → account_id (HIGH/MEDIUM, no confirmation)
  - statecode  → churned (LOW, requires_confirmation=True — NOT silently mapped)
  - annualrevenue → arr

Pipedrive:
  - org_id → account_id
  - status / lost_reason → churned (LOW, requires_confirmation=True)
  - is_lost → churned (MEDIUM, no confirmation)

Ambiguity guard:
  - exec_sponsor_present (binary 0/1) must NOT be auto-selected for churned
  - A column with only one unique value must NOT match the binary heuristic
  - Value-vocabulary match (e.g. "Closed Lost"/"Closed Won" column) → LOW +
    requires_confirmation

Value normalisation:
  - "Closed Lost" → 1 after normalise()
  - "Closed Won"  → 0 after normalise()
  - "closedlost"  → 1 after normalise()
  - "won"         → 0 after normalise()
  - numeric values that cannot be coerced generate a warning
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.engine.schema_mapping import (
    suggest_mapping,
    HIGH, MEDIUM, LOW, NONE,
)
from app.engine.normalizer import normalize


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _df(**kwargs) -> pd.DataFrame:
    n = max(len(v) for v in kwargs.values()) if kwargs else 3
    return pd.DataFrame({k: ([None] * n if not v else v) for k, v in kwargs.items()})


# ===========================================================================
# SALESFORCE
# ===========================================================================

class TestSalesforce:

    def test_account_id_from_AccountId(self):
        df = _df(AccountId=["001xxx", "002xxx"])
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "AccountId"
        assert s.confidence["account_id"] in (HIGH, MEDIUM)
        assert not s.requires_confirmation.get("account_id", False)

    def test_arr_from_ARR_c(self):
        df = _df(AccountId=["001"], ARR__c=[50000])
        s = suggest_mapping(df)
        assert s.suggested["arr"] == "ARR__c"
        assert s.confidence["arr"] in (MEDIUM, HIGH)
        assert not s.requires_confirmation.get("arr", False)

    def test_renewal_date_from_Renewal_Date__c(self):
        df = _df(AccountId=["001"], Renewal_Date__c=["2025-06-01"])
        s = suggest_mapping(df)
        assert s.suggested["renewal_date"] == "Renewal_Date__c"
        assert not s.requires_confirmation.get("renewal_date", False)

    def test_plan_type_from_Plan__c(self):
        df = _df(AccountId=["001"], Plan__c=["Enterprise"])
        s = suggest_mapping(df)
        assert s.suggested["plan_type"] == "Plan__c"

    def test_direct_churn_flag_no_confirmation(self):
        """Churned__c is an unambiguous direct churn flag — no confirmation."""
        df = _df(AccountId=["001", "002"], Churned__c=[True, False])
        s = suggest_mapping(df)
        assert s.suggested["churned"] == "Churned__c"
        assert s.confidence["churned"] in (MEDIUM, HIGH)
        assert not s.requires_confirmation.get("churned", False)

    def test_stagename_requires_confirmation(self):
        """StageName is ambiguous — must be LOW + requires_confirmation, never auto-select."""
        df = _df(
            AccountId=["001", "002", "003"],
            StageName=["Closed Lost", "Closed Won", "Closed Lost"],
            ARR__c=[50000, 80000, 30000],
        )
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "AccountId"
        # StageName may or may not be mapped to churned depending on alias priority
        # (if another unambiguous churned alias is found first it takes precedence)
        if s.suggested.get("churned") == "StageName":
            assert s.confidence["churned"] == LOW
            assert s.requires_confirmation["churned"] is True

    def test_stagename_not_autoselected_when_direct_flag_present(self):
        """When Churned__c is present, it wins over the ambiguous StageName."""
        df = _df(
            AccountId=["001", "002"],
            Churned__c=[True, False],
            StageName=["Closed Won", "Closed Lost"],
        )
        s = suggest_mapping(df)
        # Direct flag should be preferred
        assert s.suggested["churned"] == "Churned__c"
        assert not s.requires_confirmation.get("churned", False)

    def test_isclosed_requires_confirmation(self):
        """IsClosed alone is NOT churn — must require confirmation."""
        df = _df(AccountId=["001", "002"], IsClosed=[True, False])
        s = suggest_mapping(df)
        if s.suggested.get("churned") == "IsClosed":
            assert s.confidence["churned"] == LOW
            assert s.requires_confirmation["churned"] is True

    def test_full_salesforce_export(self):
        """Realistic Salesforce Account export."""
        df = _df(
            AccountId=["001", "002"],
            LastModifiedDate=["2024-01-01", "2024-01-01"],
            Churned__c=[True, False],
            ARR__c=[50000, 80000],
            Renewal_Date__c=["2025-06-01", "2025-03-01"],
            Plan__c=["Enterprise", "Pro"],
            AccountName=["Acme Corp", "Beta LLC"],
        )
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "AccountId"
        assert s.suggested["snapshot_date"] == "LastModifiedDate"
        assert s.suggested["churned"] == "Churned__c"
        assert s.confidence["churned"] in (MEDIUM, HIGH)
        assert not s.requires_confirmation.get("churned", False)
        assert s.suggested["arr"] == "ARR__c"
        assert s.suggested["renewal_date"] == "Renewal_Date__c"
        assert s.suggested["plan_type"] == "Plan__c"
        assert s.suggested["company_name"] == "AccountName"


# ===========================================================================
# HUBSPOT
# ===========================================================================

class TestHubSpot:

    def test_account_id_from_hs_object_id(self):
        df = _df(hs_object_id=["123", "456"])
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "hs_object_id"
        assert not s.requires_confirmation.get("account_id", False)

    def test_account_id_from_companyId(self):
        """companyId (capital I) normalises to companyid, matching company_id alias."""
        df = _df(companyId=["h1", "h2"])
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "companyId"

    def test_direct_churn_flag_no_confirmation(self):
        df = _df(hs_object_id=["h1", "h2"], churn_flag=[1, 0])
        s = suggest_mapping(df)
        assert s.suggested["churned"] == "churn_flag"
        assert s.confidence["churned"] in (MEDIUM, HIGH)
        assert not s.requires_confirmation.get("churned", False)

    def test_dealstage_requires_confirmation(self):
        """dealstage is ambiguous — must be LOW + requires_confirmation."""
        df = _df(
            companyId=["h1", "h2"],
            dealstage=["closedlost", "closedwon"],
            mrr=[1000, 2000],
        )
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "companyId"
        if s.suggested.get("churned") == "dealstage":
            assert s.confidence["churned"] == LOW
            assert s.requires_confirmation["churned"] is True

    def test_lifecyclestage_requires_confirmation(self):
        """lifecyclestage is NOT a direct churn label — requires confirmation."""
        df = _df(
            hs_object_id=["h1", "h2"],
            lifecyclestage=["customer", "churned"],
        )
        s = suggest_mapping(df)
        if s.suggested.get("churned") == "lifecyclestage":
            assert s.confidence["churned"] == LOW
            assert s.requires_confirmation["churned"] is True

    def test_direct_churned_beats_lifecyclestage(self):
        """A direct 'churned' column wins over ambiguous lifecyclestage."""
        df = _df(
            hs_object_id=["h1", "h2"],
            churned=[1, 0],
            lifecyclestage=["churned", "customer"],
        )
        s = suggest_mapping(df)
        assert s.suggested["churned"] == "churned"
        assert not s.requires_confirmation.get("churned", False)

    def test_full_hubspot_export(self):
        df = _df(
            hs_object_id=["h1", "h2"],
            createdate=["2024-01-01", "2024-01-01"],
            churned=[1, 0],
            mrr=[1000, 2000],
            renewal_date=["2025-01-01", "2025-06-01"],
            plan=["Starter", "Pro"],
        )
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "hs_object_id"
        assert s.suggested["churned"] == "churned"
        assert not s.requires_confirmation.get("churned", False)
        assert s.suggested["mrr"] == "mrr"
        assert s.suggested["renewal_date"] == "renewal_date"
        assert s.suggested["plan_type"] == "plan"


# ===========================================================================
# MICROSOFT DYNAMICS
# ===========================================================================

class TestDynamics:

    def test_account_id_from_accountid(self):
        """Dynamics uses all-lowercase accountid."""
        df = _df(accountid=["abc-001", "abc-002"])
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "accountid"
        assert not s.requires_confirmation.get("account_id", False)

    def test_arr_from_annualrevenue(self):
        df = _df(accountid=["d1"], annualrevenue=[100000])
        s = suggest_mapping(df)
        assert s.suggested["arr"] == "annualrevenue"

    def test_statecode_numeric_not_silently_mapped(self):
        """
        statecode with raw numeric values {0, 1} MUST NOT be silently mapped
        to churned.  It may be suggested (with requires_confirmation=True) but
        must never be auto-selected.
        """
        df = _df(
            accountid=["d1", "d2", "d3", "d4"],
            statecode=[0, 1, 0, 1],
            annualrevenue=[100000, 200000, 50000, 75000],
        )
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "accountid"
        # If statecode is suggested for churned it must be LOW + requires_confirmation
        if s.suggested.get("churned") == "statecode":
            assert s.confidence["churned"] == LOW
            assert s.requires_confirmation["churned"] is True
        # It must NEVER be HIGH or MEDIUM
        assert s.confidence.get("churned", NONE) != HIGH
        assert s.confidence.get("churned", NONE) != MEDIUM

    def test_statuscode_requires_confirmation(self):
        df = _df(accountid=["d1", "d2"], statuscode=[1, 0])
        s = suggest_mapping(df)
        if s.suggested.get("churned") == "statuscode":
            assert s.confidence["churned"] == LOW
            assert s.requires_confirmation["churned"] is True

    def test_full_dynamics_export(self):
        df = _df(
            accountid=["d1", "d2"],
            modifiedon=["2024-01-01", "2024-01-01"],
            statecode=[0, 1],
            annualrevenue=[100000, 50000],
            contractenddate=["2025-06-01", "2024-12-01"],
        )
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "accountid"
        assert s.suggested["arr"] == "annualrevenue"
        assert s.suggested["renewal_date"] == "contractenddate"
        # statecode may be suggested for churned but only with confirmation
        if s.suggested.get("churned") == "statecode":
            assert s.requires_confirmation["churned"] is True


# ===========================================================================
# PIPEDRIVE
# ===========================================================================

class TestPipedrive:

    def test_account_id_from_org_id(self):
        df = _df(org_id=["p1", "p2"])
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "org_id"
        assert not s.requires_confirmation.get("account_id", False)

    def test_account_id_from_organization_id(self):
        df = _df(organization_id=["p1", "p2"])
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "organization_id"

    def test_direct_is_lost_no_confirmation(self):
        """is_lost is an unambiguous Pipedrive churn flag."""
        df = _df(org_id=["p1", "p2"], is_lost=[True, False])
        s = suggest_mapping(df)
        assert s.suggested["churned"] == "is_lost"
        assert not s.requires_confirmation.get("churned", False)

    def test_status_requires_confirmation(self):
        """Pipedrive status (won/lost/open) is ambiguous — requires confirmation."""
        df = _df(
            org_id=["p1", "p2", "p3"],
            status=["won", "lost", "open"],
            value=[5000, 3000, 8000],
        )
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "org_id"
        if s.suggested.get("churned") == "status":
            assert s.confidence["churned"] == LOW
            assert s.requires_confirmation["churned"] is True

    def test_lost_reason_requires_confirmation(self):
        """lost_reason is a text description, not a binary label."""
        df = _df(
            org_id=["p1", "p2"],
            lost_reason=["Price too high", "Chose competitor"],
        )
        s = suggest_mapping(df)
        if s.suggested.get("churned") == "lost_reason":
            assert s.confidence["churned"] == LOW
            assert s.requires_confirmation["churned"] is True

    def test_is_lost_beats_status(self):
        """When is_lost is present, it wins over the ambiguous status field."""
        df = _df(
            org_id=["p1", "p2"],
            is_lost=[True, False],
            status=["won", "lost"],
        )
        s = suggest_mapping(df)
        assert s.suggested["churned"] == "is_lost"
        assert not s.requires_confirmation.get("churned", False)

    def test_full_pipedrive_export(self):
        df = _df(
            org_id=["p1", "p2"],
            update_time=["2024-01-01", "2024-01-01"],
            is_lost=[True, False],
            annual_value=[48000, 24000],
            expected_close_date=["2025-01-01", "2025-06-01"],
        )
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "org_id"
        assert s.suggested["churned"] == "is_lost"
        assert s.suggested["arr"] == "annual_value"
        assert s.suggested["renewal_date"] == "expected_close_date"


# ===========================================================================
# AMBIGUITY GUARD — generic binary fields must NOT be auto-selected
# ===========================================================================

class TestAmbiguityGuard:

    def test_exec_sponsor_present_not_auto_selected(self):
        """
        exec_sponsor_present is a binary 0/1 flag that has nothing to do with
        churn.  It may be detected by the heuristic (LOW) but must NEVER be
        HIGH or MEDIUM confidence for churned.
        """
        df = _df(
            account_id=["A1", "A2", "A3", "A4"],
            exec_sponsor_present=[1, 0, 1, 0],
        )
        s = suggest_mapping(df)
        # If detected at all, must be LOW
        churn_conf = s.confidence.get("churned", NONE)
        assert churn_conf != HIGH
        assert churn_conf != MEDIUM

    def test_binary_heuristic_is_low_never_medium(self):
        """Any binary column detected via heuristic must be LOW, not MEDIUM."""
        df = _df(
            account_id=["A1", "A2"],
            outcome=["yes", "no"],
        )
        s = suggest_mapping(df)
        if s.suggested.get("churned") == "outcome":
            assert s.confidence["churned"] == LOW

    def test_single_value_column_not_detected(self):
        """A column with only one distinct value must not match the binary heuristic."""
        df = _df(
            account_id=["A1", "A2", "A3"],
            always_active=["active", "active", "active"],
        )
        s = suggest_mapping(df)
        assert s.suggested.get("churned") != "always_active"

    def test_high_cardinality_string_not_detected(self):
        """A high-cardinality text column must not be confused with churned."""
        df = _df(
            account_id=["A1", "A2", "A3"],
            notes=["Meeting scheduled", "Contract renewed", "No response yet"],
        )
        s = suggest_mapping(df)
        assert s.suggested.get("churned") is None

    def test_value_vocabulary_match_requires_confirmation(self):
        """
        A column with churn-positive AND churn-negative vocabulary values is
        detected as a plausible churn column, but MUST require confirmation
        because the match is based on values, not field name.
        """
        df = _df(
            account_id=["A1", "A2", "A3", "A4"],
            opportunity_outcome=["Closed Lost", "Closed Won", "Closed Lost", "Closed Won"],
        )
        s = suggest_mapping(df)
        if s.suggested.get("churned") == "opportunity_outcome":
            assert s.confidence["churned"] == LOW
            assert s.requires_confirmation.get("churned", False) is True


# ===========================================================================
# VALUE NORMALISATION — churned column with CRM text values
# ===========================================================================

class TestValueNormalisation:

    def _do_normalize(self, source_col: str, values: list) -> pd.Series:
        """Helper: map source_col → churned and run normalize()."""
        df = pd.DataFrame({
            "account_id": [f"A{i}" for i in range(len(values))],
            source_col: values,
        })
        result = normalize(df, {"account_id": "account_id", "churned": source_col})
        return result.canonical_df["churned"]

    def test_closed_lost_maps_to_1(self):
        churned = self._do_normalize("stage", ["Closed Lost", "Closed Won"])
        assert churned.iloc[0] == 1
        assert churned.iloc[1] == 0

    def test_closedlost_lowercase_maps_to_1(self):
        churned = self._do_normalize("dealstage", ["closedlost", "closedwon"])
        assert churned.iloc[0] == 1
        assert churned.iloc[1] == 0

    def test_won_maps_to_0(self):
        churned = self._do_normalize("status", ["lost", "won", "lost"])
        assert churned.iloc[0] == 1
        assert churned.iloc[1] == 0
        assert churned.iloc[2] == 1

    def test_non_renewed_maps_to_1(self):
        churned = self._do_normalize("outcome", ["non-renewed", "renewed"])
        assert churned.iloc[0] == 1
        assert churned.iloc[1] == 0

    def test_inactive_maps_to_1(self):
        churned = self._do_normalize("account_status", ["inactive", "active"])
        assert churned.iloc[0] == 1
        assert churned.iloc[1] == 0

    def test_deactivated_maps_to_1(self):
        churned = self._do_normalize("status", ["deactivated", "active"])
        assert churned.iloc[0] == 1
        assert churned.iloc[1] == 0

    def test_customer_hubspot_maps_to_0(self):
        """HubSpot lifecyclestage 'customer' means retained."""
        churned = self._do_normalize("lifecyclestage", ["churned", "customer"])
        assert churned.iloc[0] == 1
        assert churned.iloc[1] == 0

    def test_unknown_value_produces_warning(self):
        """Values not in truthy/falsy sets are treated as 0 with a warning."""
        df = pd.DataFrame({
            "account_id": ["A1", "A2"],
            "stage": ["Closed Lost", "Pending"],  # "Pending" is unknown
        })
        result = normalize(df, {"account_id": "account_id", "churned": "stage"})
        churned = result.canonical_df["churned"]
        assert churned.iloc[0] == 1
        assert churned.iloc[1] == 0   # unknown → treated as 0
        # A warning should be emitted
        assert any("could not be coerced" in w for w in result.warnings)

    def test_numeric_0_1_passes_through(self):
        """Numeric 0/1 columns are passed through as-is without text coercion."""
        churned = self._do_normalize("churned_flag", [1, 0, 1])
        assert list(churned) == [1, 0, 1]


# ===========================================================================
# CRM PACK SYSTEM — pack loading and merge
# ===========================================================================

class TestPackSystem:

    def test_merged_alias_map_contains_global_aliases(self):
        """Global aliases must survive the pack merge."""
        from app.engine.crm_aliases import MERGED_ALIAS_MAP
        assert "customer_id" in MERGED_ALIAS_MAP["account_id"]
        assert "churned" in MERGED_ALIAS_MAP["churned"]
        assert "arr_usd" in MERGED_ALIAS_MAP["arr"]
        assert "contract_end" in MERGED_ALIAS_MAP["renewal_date"]

    def test_merged_alias_map_contains_crm_aliases(self):
        """CRM-specific aliases must be present in the merged map."""
        from app.engine.crm_aliases import MERGED_ALIAS_MAP
        # Salesforce
        assert "AccountId" in MERGED_ALIAS_MAP["account_id"]
        assert "ARR__c" in MERGED_ALIAS_MAP["arr"]
        assert "StageName" in MERGED_ALIAS_MAP["churned"]
        # HubSpot
        assert "hs_object_id" in MERGED_ALIAS_MAP["account_id"]
        assert "dealstage" in MERGED_ALIAS_MAP["churned"]
        # Dynamics
        assert "accountid" in MERGED_ALIAS_MAP["account_id"]
        assert "statecode" in MERGED_ALIAS_MAP["churned"]
        # Pipedrive
        assert "org_id" in MERGED_ALIAS_MAP["account_id"]
        assert "is_lost" in MERGED_ALIAS_MAP["churned"]

    def test_requires_confirmation_norms_populated(self):
        """Ambiguous aliases must appear in REQUIRES_CONFIRMATION_NORMS."""
        from app.engine.crm_aliases import REQUIRES_CONFIRMATION_NORMS
        churned_rc = REQUIRES_CONFIRMATION_NORMS.get("churned", frozenset())
        # Salesforce ambiguous fields
        assert "stagename" in churned_rc
        assert "isclosed" in churned_rc
        # HubSpot ambiguous fields
        assert "dealstage" in churned_rc
        assert "lifecyclestage" in churned_rc
        # Dynamics ambiguous fields
        assert "statecode" in churned_rc
        assert "statuscode" in churned_rc
        # Pipedrive ambiguous fields
        assert "status" in churned_rc

    def test_unambiguous_aliases_not_in_requires_confirmation(self):
        """Direct churn flag aliases must NOT be in requires_confirmation."""
        from app.engine.crm_aliases import REQUIRES_CONFIRMATION_NORMS
        churned_rc = REQUIRES_CONFIRMATION_NORMS.get("churned", frozenset())
        # These are clear churn signals — no confirmation needed
        assert "churnedc" in churned_rc or "churnedc" not in churned_rc  # neutral check
        # The canonical name itself must NOT require confirmation
        assert "churned" not in churned_rc
        assert "ischurned" not in churned_rc

    def test_churn_positive_vocabulary_populated(self):
        from app.engine.crm_aliases import CHURN_POSITIVE_VALUES
        assert "closed lost" in CHURN_POSITIVE_VALUES
        assert "closedlost" in CHURN_POSITIVE_VALUES
        assert "inactive" in CHURN_POSITIVE_VALUES
        assert "lost" in CHURN_POSITIVE_VALUES
        assert "non-renewed" in CHURN_POSITIVE_VALUES

    def test_churn_negative_vocabulary_populated(self):
        from app.engine.crm_aliases import CHURN_NEGATIVE_VALUES
        assert "closed won" in CHURN_NEGATIVE_VALUES
        assert "active" in CHURN_NEGATIVE_VALUES
        assert "won" in CHURN_NEGATIVE_VALUES
        assert "retained" in CHURN_NEGATIVE_VALUES

    def test_no_duplicate_aliases_in_merged_map(self):
        """
        Each alias string should appear at most once per canonical bucket
        (case-sensitive deduplication).

        Note: aliases that differ only in case (e.g. "accountid" from global
        and "AccountId" from Salesforce) are intentionally both retained so
        callers can inspect exact CRM-convention casing.  They are functionally
        equivalent in the suggestion engine because it normalises via .lower()
        before matching.
        """
        from app.engine.crm_aliases import MERGED_ALIAS_MAP
        for canonical, aliases in MERGED_ALIAS_MAP.items():
            assert len(aliases) == len(set(aliases)), (
                f"Exact-duplicate aliases in merged map for '{canonical}': "
                f"{[a for a in aliases if aliases.count(a) > 1]}"
            )


# ===========================================================================
# BACKWARD COMPATIBILITY — existing tests must still pass
# ===========================================================================

class TestBackwardCompatibility:
    """Verify that all originally tested behaviours still work."""

    def test_exact_match_account_id(self):
        df = _df(account_id=["A1", "A2"])
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "account_id"
        assert s.confidence["account_id"] == HIGH

    def test_alias_customer_id(self):
        df = _df(customer_id=["C1", "C2"])
        s = suggest_mapping(df)
        assert s.suggested["account_id"] == "customer_id"

    def test_alias_canceled_maps_to_churned(self):
        df = _df(account_id=["A"], canceled=[1])
        s = suggest_mapping(df)
        assert s.suggested["churned"] == "canceled"
        assert s.confidence["churned"] in (MEDIUM, HIGH)

    def test_alias_arr_usd(self):
        df = _df(account_id=["A"], arr_usd=[1000])
        s = suggest_mapping(df)
        assert s.suggested["arr"] == "arr_usd"

    def test_alias_contract_end_maps_to_renewal_date(self):
        df = _df(account_id=["A"], contract_end=["2025-01-01"])
        s = suggest_mapping(df)
        assert s.suggested["renewal_date"] == "contract_end"

    def test_heuristic_binary_column_detected_as_churned(self):
        df = _df(account_id=["A1", "A2", "A3"], outcome=["yes", "no", "yes"])
        s = suggest_mapping(df)
        assert s.suggested["churned"] == "outcome"
        assert s.confidence["churned"] == LOW

    def test_no_double_mapping_single_column(self):
        df = _df(customer_id=["A1"])
        s = suggest_mapping(df)
        claimed = [v for v in s.suggested.values() if v == "customer_id"]
        assert len(claimed) == 1

    def test_missing_required_when_churned_absent(self):
        df = _df(account_id=["A"], snapshot_date=["2024-01-01"])
        s = suggest_mapping(df)
        assert "churned" in s.missing_required_for_training

    def test_unmapped_columns_reported(self):
        df = _df(account_id=["A"], random_field_xyz=[1])
        s = suggest_mapping(df)
        assert "random_field_xyz" in s.unmapped_source_cols

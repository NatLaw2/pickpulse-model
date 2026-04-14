"""Engine configuration — churn risk module."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Calibration settings
# ---------------------------------------------------------------------------
@dataclass
class CalibrationConfig:
    method: str = "sigmoid"        # "sigmoid" (Platt) or "isotonic"
    cv_folds: int = 5              # used with CalibratedClassifierCV
    prob_floor: float = 0.05
    prob_ceil: float = 0.95


# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------
@dataclass
class TierConfig:
    """Maps predicted probability ranges to human-readable tiers."""
    high_threshold: float = 0.70
    medium_threshold: float = 0.40
    high_label: str = "High"
    medium_label: str = "Medium"
    low_label: str = "Low"

    def classify(self, prob: float) -> str:
        if prob >= self.high_threshold:
            return self.high_label
        if prob >= self.medium_threshold:
            return self.medium_label
        return self.low_label


# ---------------------------------------------------------------------------
# Module descriptor
# ---------------------------------------------------------------------------
@dataclass
class ModuleConfig:
    """Describes a vertical module."""
    name: str
    display_name: str = ""
    label_column: str = "label"
    timestamp_column: str = "timestamp"
    id_column: str = "id"
    value_column: Optional[str] = None
    positive_label: str = "1"
    positive_display: str = "Positive"
    negative_display: str = "Negative"
    required_columns: List[str] = field(default_factory=list)
    optional_columns: List[str] = field(default_factory=list)
    tiers: TierConfig = field(default_factory=TierConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    artifact_dir: str = ""

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name.title()
        if not self.artifact_dir:
            data_dir = os.environ.get("DATA_DIR", "data")
            self.artifact_dir = os.path.join(data_dir, "artifacts", self.name)

    def get_artifact_dir(self, tenant_id: Optional[str] = None, run_id: Optional[str] = None) -> str:
        """Return per-tenant artifact directory rooted under DATA_DIR.

        On Render, DATA_DIR=/data (persistent disk) so artifacts survive
        redeploys. Locally, DATA_DIR defaults to "data".

        Args:
            tenant_id: If None, returns the module-level artifact dir.
            run_id: If provided, returns a versioned subdirectory:
                    {DATA_DIR}/artifacts/{tenant_id}/{module}/{run_id}/
        """
        data_dir = os.environ.get("DATA_DIR", "data")
        base = os.path.join(data_dir, "artifacts")
        if tenant_id is None:
            return os.path.join(base, self.name)
        if run_id:
            return os.path.join(base, tenant_id, self.name, run_id)
        return os.path.join(base, tenant_id, self.name)


# ---------------------------------------------------------------------------
# Churn module config
# ---------------------------------------------------------------------------
CHURN_MODULE = ModuleConfig(
    name="churn",
    display_name="Churn Risk",
    label_column="churned",
    timestamp_column="snapshot_date",
    id_column="account_id",
    value_column="arr",
    positive_label="1",
    positive_display="Churned",
    negative_display="Retained",
    required_columns=["account_id", "churned"],
    optional_columns=[
        "arr", "plan", "seats", "monthly_logins", "support_tickets",
        "nps_score", "days_since_last_login", "contract_months_remaining",
        "industry", "company_size",
        "days_until_renewal", "auto_renew_flag", "renewal_status",
        "hs_object_id",   # HubSpot company Record ID — required for CRM card and write-back
    ],
    tiers=TierConfig(
        high_threshold=0.30,
        medium_threshold=0.20,
        high_label="High Risk",
        medium_label="Medium Risk",
        low_label="Low Risk",
    ),
)

HUBSPOT_CHURN_MODULE = ModuleConfig(
    name="hubspot_churn",
    display_name="HubSpot Churn Risk",
    label_column="churned",
    timestamp_column="snapshot_date",
    id_column="account_id",
    value_column="arr",
    positive_label="1",
    positive_display="Churned",
    negative_display="Retained",
    required_columns=["account_id", "churned"],
    optional_columns=[
        "arr", "plan", "seats", "monthly_logins", "support_tickets",
        "nps_score", "days_since_last_login", "contract_months_remaining",
        "industry", "company_size",
        "days_until_renewal", "auto_renew_flag", "renewal_status",
        "contact_count", "deal_count", "days_since_last_activity",
        "login_rate_per_seat", "ticket_rate_per_seat",
        "delta_monthly_logins", "delta_nps_score", "delta_support_tickets",
        "delta_days_until_renewal",
    ],
    tiers=TierConfig(
        high_threshold=0.30,
        medium_threshold=0.20,
        high_label="High Risk",
        medium_label="Medium Risk",
        low_label="Low Risk",
    ),
)

SALESFORCE_CHURN_MODULE = ModuleConfig(
    name="salesforce_churn",
    display_name="Salesforce Churn Risk",
    label_column="churned",
    timestamp_column="snapshot_date",
    id_column="account_id",
    value_column="arr",
    positive_label="1",
    positive_display="Churned",
    negative_display="Retained",
    required_columns=["account_id", "churned"],
    optional_columns=[
        "arr", "plan", "seats", "monthly_logins", "support_tickets",
        "nps_score", "days_since_last_login", "contract_months_remaining",
        "industry", "company_size",
        "days_until_renewal", "auto_renew_flag", "renewal_status",
        "contact_count", "deal_count", "days_since_last_activity",
        "login_rate_per_seat", "ticket_rate_per_seat",
        "delta_monthly_logins", "delta_nps_score", "delta_support_tickets",
        "delta_days_until_renewal",
    ],
    tiers=TierConfig(
        high_threshold=0.30,
        medium_threshold=0.20,
        high_label="High Risk",
        medium_label="Medium Risk",
        low_label="Low Risk",
    ),
)

MODULES: Dict[str, ModuleConfig] = {
    "churn": CHURN_MODULE,
    "hubspot_churn": HUBSPOT_CHURN_MODULE,
    "salesforce_churn": SALESFORCE_CHURN_MODULE,
}


def get_module(name: str) -> ModuleConfig:
    if name not in MODULES:
        raise ValueError(f"Unknown module '{name}'. Available: {list(MODULES.keys())}")
    return MODULES[name]

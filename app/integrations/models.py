"""Pydantic models for the integration layer."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BusinessMode(str, Enum):
    saas = "saas"
    services = "services"


# ---------------------------------------------------------------------------
# Connector config / status
# ---------------------------------------------------------------------------

class ConnectorStatus(str, Enum):
    not_configured = "not_configured"
    configured = "configured"
    syncing = "syncing"
    healthy = "healthy"
    error = "error"


class ConnectorConfig(BaseModel):
    name: str
    display_name: str
    api_key: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False
    business_mode: BusinessMode = BusinessMode.saas


class ConnectorInfo(BaseModel):
    name: str
    display_name: str
    status: ConnectorStatus = ConnectorStatus.not_configured
    enabled: bool = False
    last_synced_at: Optional[datetime] = None
    account_count: int = 0
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Normalized account
# ---------------------------------------------------------------------------

class Account(BaseModel):
    external_id: str
    source: str  # "hubspot", "stripe", "csv"
    name: str
    email: Optional[str] = None
    plan: Optional[str] = None
    arr: Optional[float] = None
    seats: Optional[int] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    created_at: Optional[datetime] = None
    synced_at: datetime = Field(default_factory=datetime.utcnow)
    raw_data: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Daily signals (usage / engagement snapshot)
# ---------------------------------------------------------------------------

class AccountSignal(BaseModel):
    external_id: str
    signal_date: str  # YYYY-MM-DD
    monthly_logins: Optional[int] = None
    support_tickets: Optional[int] = None
    nps_score: Optional[float] = None
    days_since_last_login: Optional[int] = None
    contract_months_remaining: Optional[float] = None
    days_until_renewal: Optional[float] = None
    auto_renew_flag: Optional[int] = None
    renewal_status: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Churn score
# ---------------------------------------------------------------------------

class ChurnScore(BaseModel):
    external_id: str
    scored_at: datetime = Field(default_factory=datetime.utcnow)
    churn_probability: float
    tier: str  # "High Risk", "Medium Risk", "Low Risk"
    arr_at_risk: Optional[float] = None
    urgency_score: Optional[float] = None
    recommended_action: Optional[str] = None
    renewal_window_label: Optional[str] = None
    confidence_level: Optional[str] = None  # "high" | "medium" | "low"
    scored_features: int = 0  # how many model features had real data


# ---------------------------------------------------------------------------
# Preflight / schema / data quality
# ---------------------------------------------------------------------------

class PreflightResult(BaseModel):
    connected: bool
    portal_id: Optional[str] = None
    companies_count: int = 0
    contacts_count: int = 0
    deals_count: int = 0
    tickets_count: int = 0
    properties_retrieved: bool = False
    schema_coverage_pct: float = 0.0
    unmapped_fields: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    checked_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Sync result
# ---------------------------------------------------------------------------

class SyncResult(BaseModel):
    connector: str
    accounts_synced: int = 0
    signals_synced: int = 0
    errors: List[str] = Field(default_factory=list)
    duration_seconds: float = 0.0

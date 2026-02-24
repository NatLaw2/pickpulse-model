"""Churn vertical adapter — customer churn risk prediction."""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from app.engine.config import CHURN_MODULE, ModuleConfig


def get_config() -> ModuleConfig:
    return CHURN_MODULE


COLUMN_ALIASES: Dict[str, List[str]] = {
    "customer_id": ["customer_id", "account_id", "client_id", "user_id", "id"],
    "snapshot_date": ["snapshot_date", "date", "observation_date", "period", "month"],
    "churned": ["churned", "churn", "is_churned", "label", "outcome", "status"],
    "arr": ["arr", "annual_revenue", "mrr", "revenue", "acv", "contract_value"],
    "plan": ["plan", "tier", "subscription", "plan_name", "product"],
    "seats": ["seats", "licenses", "users", "user_count"],
    "monthly_logins": ["monthly_logins", "logins", "login_count", "sessions"],
    "support_tickets": ["support_tickets", "tickets", "ticket_count", "cases"],
    "nps_score": ["nps_score", "nps", "satisfaction", "csat"],
    "days_since_last_login": ["days_since_last_login", "days_inactive", "last_active_days"],
    "contract_months_remaining": ["contract_months_remaining", "months_remaining", "contract_end_months"],
    "industry": ["industry", "vertical", "sector"],
    "company_size": ["company_size", "employees", "size", "employee_count"],
    "days_until_renewal": ["days_until_renewal", "renewal_days", "days_to_renewal"],
    "auto_renew_flag": ["auto_renew_flag", "auto_renew", "autorenew", "auto_renewal"],
    "renewal_status": ["renewal_status", "renewal_state", "contract_status"],
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map common column names to our standard schema."""
    rename_map = {}
    lower_cols = {c.lower().strip(): c for c in df.columns}

    for standard, aliases in COLUMN_ALIASES.items():
        if standard in df.columns:
            continue
        for alias in aliases:
            if alias.lower() in lower_cols:
                rename_map[lower_cols[alias.lower()]] = standard
                break

    if rename_map:
        df = df.rename(columns=rename_map)

    # Normalize 'churned' column if it's text
    if "churned" in df.columns:
        col = df["churned"]
        if col.dtype == object:
            mapping = {
                "churned": 1, "yes": 1, "true": 1, "1": 1, "churn": 1,
                "retained": 0, "active": 0, "no": 0, "false": 0, "0": 0,
            }
            df["churned"] = col.str.lower().str.strip().map(mapping).fillna(0).astype(int)

    # Normalize auto_renew_flag to int
    if "auto_renew_flag" in df.columns:
        col = df["auto_renew_flag"]
        if col.dtype == object:
            mapping = {"yes": 1, "true": 1, "1": 1, "no": 0, "false": 0, "0": 0}
            df["auto_renew_flag"] = col.str.lower().str.strip().map(mapping).fillna(0).astype(int)

    return df


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add churn-specific derived features."""
    work = df.copy()

    # ARR risk tier
    if "arr" in work.columns:
        q = work["arr"].quantile([0.25, 0.75])
        work["arr_tier"] = pd.cut(
            work["arr"],
            bins=[-1, q[0.25], q[0.75], float("inf")],
            labels=["low_value", "mid_value", "high_value"],
        ).astype(str)

    # Engagement score (composite)
    engagement_cols = ["monthly_logins", "seats"]
    present = [c for c in engagement_cols if c in work.columns]
    if present:
        for c in present:
            work[c] = work[c].fillna(0)
        normed = work[present].copy()
        for c in present:
            mx = normed[c].max()
            if mx > 0:
                normed[c] = normed[c] / mx
        work["engagement_score"] = normed.mean(axis=1)

    # Contract urgency
    if "contract_months_remaining" in work.columns:
        work["contract_urgency"] = pd.cut(
            work["contract_months_remaining"].fillna(12),
            bins=[-1, 2, 6, 12, float("inf")],
            labels=["critical", "soon", "upcoming", "safe"],
        ).astype(str)

    # Renewal window flags
    if "days_until_renewal" in work.columns:
        dur = work["days_until_renewal"].fillna(999)
        work["renewal_window_90d"] = (dur <= 90).astype(int)
        work["renewal_window_30d"] = (dur <= 30).astype(int)

        # Renewal risk multiplier: higher when close to renewal and not auto-renew
        auto = work.get("auto_renew_flag", pd.Series(0, index=work.index)).fillna(0)
        # Base multiplier from days
        multiplier = np.where(dur <= 30, 2.0, np.where(dur <= 90, 1.5, 1.0))
        # Reduce if auto-renew
        multiplier = np.where(auto == 1, multiplier * 0.5, multiplier)
        work["renewal_risk_multiplier"] = np.round(multiplier, 2)

    return work


def compute_urgency_score(prob: float, days_until_renewal: float) -> float:
    """Compute urgency score (0-100) from churn probability and renewal timing."""
    if pd.isna(days_until_renewal) or days_until_renewal > 365:
        urgency_factor = 1.0
    elif days_until_renewal <= 0:
        urgency_factor = 3.0
    elif days_until_renewal <= 30:
        urgency_factor = 2.5
    elif days_until_renewal <= 90:
        urgency_factor = 1.8
    else:
        urgency_factor = 1.0 + max(0, (180 - days_until_renewal)) / 180.0

    raw = prob * urgency_factor * 100
    return round(min(100.0, max(0.0, raw)), 1)


def compute_renewal_window_label(days_until_renewal: float) -> str:
    """Return human-readable renewal window label."""
    if pd.isna(days_until_renewal):
        return "unknown"
    if days_until_renewal <= 30:
        return "<30d"
    if days_until_renewal <= 90:
        return "30-90d"
    return ">90d"


def compute_recommended_action(
    churn_risk_pct: float,
    renewal_window_label: str,
    days_since_last_login: float,
) -> str:
    """Deterministic action recommendation based on risk and context."""
    if churn_risk_pct >= 70 and renewal_window_label in ("<30d", "30-90d"):
        return "Executive save plan + renewal call this week"
    if churn_risk_pct >= 70 and not pd.isna(days_since_last_login) and days_since_last_login > 30:
        return "Re-engagement campaign + training session"
    if churn_risk_pct >= 70:
        return "Executive save plan + renewal call this week"
    if churn_risk_pct >= 40:
        return "CSM check-in + usage review"
    return "Monitor"


def compute_account_status(
    churned: int,
    renewal_status: str,
    days_until_renewal: float,
) -> str:
    """Determine account lifecycle status for archiving."""
    if churned == 1 or renewal_status == "cancelled":
        return "archived_cancelled"
    if renewal_status == "renewed" or (
        not pd.isna(days_until_renewal) and days_until_renewal < 0 and churned == 0
    ):
        return "archived_renewed"
    return "active"

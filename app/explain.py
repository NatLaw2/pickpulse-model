"""Per-account risk drivers and playbook actions."""
from __future__ import annotations

import logging
import os
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

from .auth import get_tenant_id

logger = logging.getLogger("pickpulse.explain")

router = APIRouter(prefix="/api/predictions", tags=["explain"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class ExplainResponse(BaseModel):
    customer_id: str
    churn_risk_pct: float
    arr: float
    arr_at_risk: float
    days_until_renewal: int
    renewal_window_label: str
    tier: str
    recommended_action: str
    risk_drivers: List[str]
    risk_driver_summary: str


# ---------------------------------------------------------------------------
# Heuristic risk driver generation
# ---------------------------------------------------------------------------
def generate_risk_drivers(row: dict) -> list[str]:
    """Generate human-readable risk driver bullets from a prediction row.

    Uses raw feature values already present in the scored data to produce
    3–5 concrete, actionable driver strings.
    """
    drivers: list[str] = []

    # 1. Login activity
    days_inactive = row.get("days_since_last_login")
    if days_inactive is not None and not pd.isna(days_inactive):
        days_inactive = float(days_inactive)
        if days_inactive > 60:
            drivers.append(f"No login activity in {int(days_inactive)} days")
        elif days_inactive > 30:
            drivers.append(f"Last login was {int(days_inactive)} days ago")

    monthly_logins = row.get("monthly_logins")
    if monthly_logins is not None and not pd.isna(monthly_logins):
        monthly_logins = float(monthly_logins)
        if monthly_logins <= 2:
            drivers.append(f"Only {int(monthly_logins)} logins this month")
        elif monthly_logins <= 5:
            drivers.append(f"Low login frequency ({int(monthly_logins)}/month)")

    # 2. Support tickets
    tickets = row.get("support_tickets")
    if tickets is not None and not pd.isna(tickets):
        tickets = int(float(tickets))
        if tickets >= 5:
            drivers.append(f"{tickets} support tickets — potential frustration signal")
        elif tickets >= 3:
            drivers.append(f"{tickets} open support tickets")

    # 3. NPS / satisfaction
    nps = row.get("nps_score")
    if nps is not None and not pd.isna(nps):
        nps = float(nps)
        if nps <= 5:
            drivers.append(f"NPS score is {nps:.0f} (detractor range)")
        elif nps <= 7:
            drivers.append(f"NPS score is {nps:.0f} (passive range)")

    # 4. Renewal proximity
    days_renewal = row.get("days_until_renewal")
    if days_renewal is not None and not pd.isna(days_renewal):
        days_renewal = int(float(days_renewal))
        if days_renewal <= 30:
            drivers.append(f"Renewal in {days_renewal} days — immediate window")
        elif days_renewal <= 90:
            drivers.append(f"Renewal in {days_renewal} days")

    # 5. Seat utilization / engagement
    seats = row.get("seats")
    if seats is not None and not pd.isna(seats):
        seats = int(float(seats))
        if seats <= 2:
            drivers.append(f"Only {seats} active seats — low adoption")

    # 6. Contract urgency
    months_remaining = row.get("contract_months_remaining")
    if months_remaining is not None and not pd.isna(months_remaining):
        months_remaining = float(months_remaining)
        if months_remaining <= 2:
            drivers.append(f"Contract expires in {months_remaining:.0f} months")

    # 7. Auto-renew off
    auto_renew = row.get("auto_renew_flag")
    if auto_renew is not None and not pd.isna(auto_renew) and int(float(auto_renew)) == 0:
        drivers.append("Auto-renewal is OFF — manual renewal required")

    # 8. High churn probability itself as context
    risk_pct = row.get("churn_risk_pct", 0)
    if risk_pct and float(risk_pct) >= 70 and len(drivers) < 2:
        drivers.append("Model identifies multiple weak engagement signals")

    # Limit to 5 drivers
    return drivers[:5] if drivers else ["Composite risk from multiple engagement signals"]


def build_risk_driver_summary(drivers: list[str]) -> str:
    """Build a single summary string (max 500 chars) from driver bullets."""
    summary = "; ".join(drivers)
    if len(summary) > 500:
        summary = summary[:497] + "..."
    return summary


# ---------------------------------------------------------------------------
# Explain endpoint
# ---------------------------------------------------------------------------
@router.get("/{customer_id}/explain", response_model=ExplainResponse)
def explain_account(
    customer_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """Return risk details and heuristic drivers for a single account."""
    # Import here to avoid circular imports
    from .console_api import _get_state

    state = _get_state(tenant_id)
    predictions = state["predictions"].get("churn", [])

    # Find the prediction row
    row = None
    for p in predictions:
        if p.get("customer_id") == customer_id:
            row = p
            break

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No prediction found for account '{customer_id}'. Run predictions first.",
        )

    # Also try to get the full scored CSV for richer feature data
    scored_path = os.path.join("outputs", "churn_scored.csv")
    full_row = dict(row)  # start with the prediction dict
    if os.path.exists(scored_path):
        try:
            scored_df = pd.read_csv(scored_path)
            match = scored_df[scored_df["customer_id"] == customer_id]
            if not match.empty:
                full_row = match.iloc[0].to_dict()
                # Merge in any prediction-only fields
                full_row.update({k: v for k, v in row.items() if k not in full_row})
        except Exception:
            pass  # Fall back to prediction dict

    drivers = generate_risk_drivers(full_row)
    summary = build_risk_driver_summary(drivers)

    return ExplainResponse(
        customer_id=customer_id,
        churn_risk_pct=float(row.get("churn_risk_pct", 0)),
        arr=float(row.get("arr", 0)),
        arr_at_risk=float(row.get("arr_at_risk", 0)),
        days_until_renewal=int(row.get("days_until_renewal", 0)),
        renewal_window_label=str(row.get("renewal_window_label", "unknown")),
        tier=str(row.get("tier", "Unknown")),
        recommended_action=str(row.get("recommended_action", "Monitor")),
        risk_drivers=drivers,
        risk_driver_summary=summary,
    )


# ---------------------------------------------------------------------------
# ICS calendar invite for Success Review
# ---------------------------------------------------------------------------
def generate_ics(customer_name: str, start_dt: datetime) -> str:
    """Generate a minimal .ics file for a 30-minute Success Review."""
    end_dt = start_dt + timedelta(minutes=30)
    now = datetime.now(timezone.utc)

    def fmt(dt: datetime) -> str:
        return dt.strftime("%Y%m%dT%H%M%SZ")

    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//PickPulse Intelligence//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART:{fmt(start_dt)}\r\n"
        f"DTEND:{fmt(end_dt)}\r\n"
        f"DTSTAMP:{fmt(now)}\r\n"
        f"SUMMARY:Success Review — {customer_name}\r\n"
        f"DESCRIPTION:Quarterly success review with {customer_name}. "
        f"Discuss product value, usage trends, and upcoming renewal.\r\n"
        "STATUS:TENTATIVE\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def _next_business_day_10am_utc() -> datetime:
    """Return next weekday at 10:00 UTC."""
    today = date.today()
    d = today + timedelta(days=1)
    while d.weekday() >= 5:  # skip Saturday (5) and Sunday (6)
        d += timedelta(days=1)
    return datetime.combine(d, time(10, 0), tzinfo=timezone.utc)


@router.get("/{customer_id}/ics")
def download_ics(
    customer_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """Download an .ics calendar invite for a Success Review meeting."""
    start = _next_business_day_10am_utc()
    ics_content = generate_ics(customer_id, start)

    logger.info(
        "playbook_action_executed",
        extra={
            "user_id": tenant_id,
            "customer_id": customer_id,
            "action_type": "schedule_success_review",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="success_review_{customer_id}.ics"',
        },
    )


# ---------------------------------------------------------------------------
# Playbook action logging endpoint
# ---------------------------------------------------------------------------
class PlaybookActionRequest(BaseModel):
    customer_id: str
    action_type: str  # "generate_outreach" | "send_feature_training" | "escalate_to_sales"


@router.post("/playbook/log")
def log_playbook_action(
    req: PlaybookActionRequest,
    user_id: str = Depends(get_tenant_id),
):
    """Log a playbook action execution."""
    logger.info(
        "playbook_action_executed",
        extra={
            "user_id": user_id,
            "customer_id": req.customer_id,
            "action_type": req.action_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"status": "logged", "action": req.action_type}

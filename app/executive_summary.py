"""Executive Summary — branded ARR Risk Brief generation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import get_tenant_id

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# -----------------------------------------------------------------------
# Per-tenant notification settings (in-memory)
# -----------------------------------------------------------------------
_notification_settings: Dict[str, List[str]] = {}


def clear_tenant_settings(tenant_id: str) -> None:
    """Remove notification settings for a tenant (used by demo reset)."""
    _notification_settings.pop(tenant_id, None)


class NotificationSettings(BaseModel):
    recipients: List[str]


class ExecutiveSummaryRequest(BaseModel):
    recipients: List[str] = []
    total_arr_at_risk: float
    projected_recoverable_arr: float
    save_rate: float
    high_risk_in_window: int
    renewing_90d: int
    top_accounts: List[Dict[str, Any]]
    tier_counts: Dict[str, int] = {}
    risk_drivers: List[str] = []


class ExecutiveSummaryResponse(BaseModel):
    status: str
    recipients: List[str]
    subject: str
    html_body: str
    generated_at: str


# -----------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------
@router.post("/executive-summary", response_model=ExecutiveSummaryResponse)
def send_executive_summary(
    req: ExecutiveSummaryRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """Generate a branded Executive ARR Risk Brief."""
    # Resolve recipients: use request list, fall back to tenant settings
    recipients = req.recipients or _notification_settings.get(tenant_id, [])

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"PickPulse Executive ARR Risk Brief — {datetime.now(timezone.utc).strftime('%b %d, %Y')}"

    html_body = _build_html(
        total_arr_at_risk=req.total_arr_at_risk,
        projected_recoverable_arr=req.projected_recoverable_arr,
        save_rate=req.save_rate,
        high_risk_in_window=req.high_risk_in_window,
        renewing_90d=req.renewing_90d,
        top_accounts=req.top_accounts[:5],
        tier_counts=req.tier_counts,
        risk_drivers=req.risk_drivers[:5],
        generated_at=generated_at,
    )

    return ExecutiveSummaryResponse(
        status="sent",
        recipients=recipients,
        subject=subject,
        html_body=html_body,
        generated_at=generated_at,
    )


@router.get("/settings", response_model=NotificationSettings)
def get_notification_settings(tenant_id: str = Depends(get_tenant_id)):
    """Get configured notification recipients."""
    return NotificationSettings(
        recipients=_notification_settings.get(tenant_id, [])
    )


@router.put("/settings", response_model=NotificationSettings)
def update_notification_settings(
    body: NotificationSettings,
    tenant_id: str = Depends(get_tenant_id),
):
    """Update notification recipients."""
    cleaned = [r.strip() for r in body.recipients if r.strip()]
    _notification_settings[tenant_id] = cleaned
    return NotificationSettings(recipients=cleaned)


# -----------------------------------------------------------------------
# HTML template
# -----------------------------------------------------------------------
def _fmt_currency(val: float) -> str:
    if val >= 1_000_000:
        return f"${val / 1_000_000:,.1f}M"
    if val >= 1_000:
        return f"${val / 1_000:,.0f}K"
    return f"${val:,.0f}"


def _build_html(
    total_arr_at_risk: float,
    projected_recoverable_arr: float,
    save_rate: float,
    high_risk_in_window: int,
    renewing_90d: int,
    top_accounts: List[Dict[str, Any]],
    tier_counts: Dict[str, int],
    risk_drivers: List[str],
    generated_at: str,
) -> str:
    # Top accounts table rows
    acct_rows = ""
    for i, acct in enumerate(top_accounts):
        bg = "#f9fafb" if i % 2 == 1 else "#ffffff"
        risk_pct = acct.get("churn_risk_pct", 0)
        risk_color = "#ef4444" if risk_pct >= 70 else "#f59e0b" if risk_pct >= 40 else "#10b981"
        acct_rows += f"""
        <tr style="background:{bg}">
          <td style="padding:10px 14px;font-size:13px;font-weight:600;border-bottom:1px solid #e5e7eb">{acct.get("customer_id", "—")}</td>
          <td style="padding:10px 14px;font-size:13px;text-align:right;border-bottom:1px solid #e5e7eb">
            <span style="color:{risk_color};font-weight:700">{risk_pct}%</span>
          </td>
          <td style="padding:10px 14px;font-size:13px;text-align:right;border-bottom:1px solid #e5e7eb">{_fmt_currency(acct.get("arr", 0))}</td>
          <td style="padding:10px 14px;font-size:13px;text-align:right;font-weight:700;color:#ef4444;border-bottom:1px solid #e5e7eb">{_fmt_currency(acct.get("arr_at_risk", 0))}</td>
          <td style="padding:10px 14px;font-size:13px;text-align:right;border-bottom:1px solid #e5e7eb">{acct.get("days_until_renewal", "—")}d</td>
        </tr>"""

    # Risk drivers list
    driver_items = ""
    for d in risk_drivers:
        driver_items += f'<li style="margin-bottom:6px;font-size:13px;color:#374151">{d}</li>'

    # Tier summary
    tier_badges = ""
    tier_colors = {"High Risk": "#ef4444", "Medium Risk": "#f59e0b", "Low Risk": "#10b981"}
    for tier, count in tier_counts.items():
        color = tier_colors.get(tier, "#6b7280")
        tier_badges += f'<span style="display:inline-block;margin-right:16px;font-size:13px"><span style="color:{color};font-weight:700">{count}</span> {tier}</span>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <div style="max-width:640px;margin:0 auto;padding:24px 16px">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#7B61FF 0%,#6B4EFF 50%,#5A3DE8 100%);border-radius:16px 16px 0 0;padding:32px 28px;text-align:center">
      <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.7);margin-bottom:8px;font-weight:600">PickPulse Intelligence</div>
      <h1 style="margin:0;font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.3px">Executive ARR Risk Brief</h1>
      <div style="font-size:12px;color:rgba(255,255,255,0.6);margin-top:8px">{generated_at}</div>
    </div>

    <!-- Body -->
    <div style="background:#ffffff;padding:28px;border-radius:0 0 16px 16px;border:1px solid #e5e7eb;border-top:0">

      <!-- KPI Cards -->
      <div style="display:flex;gap:12px;margin-bottom:24px">
        <div style="flex:1;background:#fef2f2;border:1px solid #fecaca;border-radius:12px;padding:16px;text-align:center">
          <div style="font-size:11px;color:#991b1b;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px">ARR at Risk</div>
          <div style="font-size:26px;font-weight:800;color:#ef4444">{_fmt_currency(total_arr_at_risk)}</div>
        </div>
        <div style="flex:1;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;padding:16px;text-align:center">
          <div style="font-size:11px;color:#166534;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px">Projected Recoverable</div>
          <div style="font-size:26px;font-weight:800;color:#10b981">{_fmt_currency(projected_recoverable_arr)}</div>
          <div style="font-size:11px;color:#6b7280;margin-top:2px">at {round(save_rate * 100)}% save rate</div>
        </div>
      </div>

      <!-- Secondary KPIs -->
      <div style="display:flex;gap:12px;margin-bottom:24px">
        <div style="flex:1;background:#fefce8;border:1px solid #fde68a;border-radius:12px;padding:14px;text-align:center">
          <div style="font-size:11px;color:#92400e;text-transform:uppercase;letter-spacing:1px;font-weight:600">Urgent Accounts</div>
          <div style="font-size:22px;font-weight:800;color:#f59e0b;margin-top:2px">{high_risk_in_window}</div>
          <div style="font-size:11px;color:#6b7280">High risk + renewing soon</div>
        </div>
        <div style="flex:1;background:#f8f9fb;border:1px solid #e5e7eb;border-radius:12px;padding:14px;text-align:center">
          <div style="font-size:11px;color:#374151;text-transform:uppercase;letter-spacing:1px;font-weight:600">Renewing in 90d</div>
          <div style="font-size:22px;font-weight:800;color:#374151;margin-top:2px">{renewing_90d}</div>
          <div style="font-size:11px;color:#6b7280">Accounts in window</div>
        </div>
      </div>

      <!-- Tier Distribution -->
      {f'<div style="margin-bottom:24px;padding:12px 16px;background:#f8f9fb;border-radius:10px">{tier_badges}</div>' if tier_badges else ''}

      <!-- Top Accounts Table -->
      {f"""<div style="margin-bottom:24px">
        <h3 style="font-size:14px;font-weight:700;color:#1a1d26;margin:0 0 12px">Top Accounts Requiring Attention</h3>
        <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden">
          <thead>
            <tr style="background:#f8f9fb">
              <th style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;text-align:left;border-bottom:1px solid #e5e7eb">Account</th>
              <th style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;text-align:right;border-bottom:1px solid #e5e7eb">Risk</th>
              <th style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;text-align:right;border-bottom:1px solid #e5e7eb">ARR</th>
              <th style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;text-align:right;border-bottom:1px solid #e5e7eb">ARR at Risk</th>
              <th style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;text-align:right;border-bottom:1px solid #e5e7eb">Renewal</th>
            </tr>
          </thead>
          <tbody>{acct_rows}</tbody>
        </table>
      </div>""" if top_accounts else ''}

      <!-- Risk Drivers -->
      {f"""<div style="margin-bottom:24px">
        <h3 style="font-size:14px;font-weight:700;color:#1a1d26;margin:0 0 12px">Top Risk Drivers</h3>
        <ul style="margin:0;padding-left:20px;list-style-type:disc">{driver_items}</ul>
      </div>""" if driver_items else ''}

      <!-- Footer -->
      <div style="border-top:1px solid #e5e7eb;padding-top:16px;text-align:center">
        <div style="font-size:11px;color:#9ca0b0">Generated by PickPulse Intelligence &middot; {generated_at}</div>
        <div style="font-size:11px;color:#9ca0b0;margin-top:4px">This is an automated executive summary. Log in to PickPulse for full account details and playbook actions.</div>
      </div>
    </div>
  </div>
</body>
</html>"""

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
        renewal_days = acct.get("days_until_renewal", "—")
        renewal_label = f"{renewal_days}d" if isinstance(renewal_days, (int, float)) else renewal_days
        acct_rows += f"""<tr>
              <td style="padding:10px 14px;font-size:13px;font-weight:600;color:#1a1d26;border-bottom:1px solid #e5e7eb" bgcolor="{bg}">{acct.get("name") or acct.get("account_id") or acct.get("customer_id") or "—"}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;border-bottom:1px solid #e5e7eb" bgcolor="{bg}"><span style="color:{risk_color};font-weight:700">{risk_pct}%</span></td>
              <td align="right" style="padding:10px 14px;font-size:13px;color:#374151;border-bottom:1px solid #e5e7eb" bgcolor="{bg}">{_fmt_currency(acct.get("arr", 0))}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;font-weight:700;color:#ef4444;border-bottom:1px solid #e5e7eb" bgcolor="{bg}">{_fmt_currency(acct.get("arr_at_risk", 0))}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;color:#374151;border-bottom:1px solid #e5e7eb" bgcolor="{bg}">{renewal_label}</td>
            </tr>"""

    # Tier distribution rows
    tier_colors = {"High Risk": "#ef4444", "Medium Risk": "#f59e0b", "Low Risk": "#10b981"}
    tier_rows = ""
    for tier, count in tier_counts.items():
        color = tier_colors.get(tier, "#6b7280")
        tier_rows += f"""<tr>
              <td style="padding:8px 14px;font-size:13px;border-bottom:1px solid #e5e7eb">
                <span style="display:inline-block;width:10px;height:10px;background:{color};border-radius:2px;margin-right:8px;vertical-align:middle"></span>{tier}
              </td>
              <td align="right" style="padding:8px 14px;font-size:13px;font-weight:700;color:{color};border-bottom:1px solid #e5e7eb">{count}</td>
            </tr>"""

    # Risk drivers rows
    driver_rows = ""
    for d in risk_drivers:
        driver_rows += f"""<tr>
              <td style="padding:6px 14px;font-size:13px;color:#374151;border-bottom:1px solid #f3f4f6">&bull;&nbsp; {d}</td>
            </tr>"""

    # Conditional sections
    tier_section = ""
    if tier_rows:
        tier_section = f"""
        <!-- Risk Distribution -->
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">
              <tr>
                <td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:#1a1d26">Risk Distribution</td>
              </tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;font-family:Arial,sans-serif">
                    <tr bgcolor="#f8f9fb">
                      <th align="left" style="padding:8px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600">Tier</th>
                      <th align="right" style="padding:8px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600">Accounts</th>
                    </tr>
                    {tier_rows}
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    accounts_section = ""
    if top_accounts:
        accounts_section = f"""
        <!-- Top Accounts -->
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">
              <tr>
                <td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:#1a1d26">Top Accounts Requiring Attention</td>
              </tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;font-family:Arial,sans-serif">
                    <tr bgcolor="#f8f9fb">
                      <th align="left" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600">Account</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600">Risk %</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600">ARR</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600">ARR at Risk</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600">Renewal</th>
                    </tr>
                    {acct_rows}
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    drivers_section = ""
    if driver_rows:
        drivers_section = f"""
        <!-- Risk Drivers -->
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">
              <tr>
                <td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:#1a1d26">Top Risk Drivers</td>
              </tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">
                    {driver_rows}
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;font-family:Arial,sans-serif;background-color:#f5f6f8" bgcolor="#f5f6f8">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f5f6f8" style="background-color:#f5f6f8">
    <tr>
      <td align="center" style="padding:24px 16px">
        <table width="600" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif;max-width:600px">

          <!-- Header -->
          <tr>
            <td align="center" bgcolor="#7B61FF" style="background-color:#7B61FF;padding:32px 28px">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#c4b5fd;font-weight:600;padding-bottom:8px;font-family:Arial,sans-serif">PickPulse Intelligence</td>
                </tr>
                <tr>
                  <td align="center" style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.3px;font-family:Arial,sans-serif">Executive ARR Risk Brief</td>
                </tr>
                <tr>
                  <td align="center" style="font-size:12px;color:#c4b5fd;padding-top:8px;font-family:Arial,sans-serif">{generated_at}</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td bgcolor="#ffffff" style="background-color:#ffffff;padding:28px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;border-bottom:1px solid #e5e7eb">
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">

                <!-- Portfolio Summary -->
                <tr>
                  <td style="padding:0 0 24px 0">
                    <table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">
                      <tr>
                        <td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:#1a1d26">Portfolio Summary</td>
                      </tr>
                      <tr>
                        <td>
                          <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;font-family:Arial,sans-serif">
                            <tr bgcolor="#fef2f2">
                              <td style="padding:14px;font-size:12px;color:#991b1b;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid #e5e7eb;width:50%">ARR at Risk</td>
                              <td align="right" style="padding:14px;font-size:20px;font-weight:800;color:#ef4444;border-bottom:1px solid #e5e7eb">{_fmt_currency(total_arr_at_risk)}</td>
                            </tr>
                            <tr bgcolor="#f0fdf4">
                              <td style="padding:14px;font-size:12px;color:#166534;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid #e5e7eb">Projected Recoverable</td>
                              <td align="right" style="padding:14px;border-bottom:1px solid #e5e7eb"><span style="font-size:20px;font-weight:800;color:#10b981">{_fmt_currency(projected_recoverable_arr)}</span><br><span style="font-size:11px;color:#6b7280">at {round(save_rate * 100)}% save rate</span></td>
                            </tr>
                            <tr>
                              <td style="padding:14px;font-size:12px;color:#92400e;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid #e5e7eb">Urgent Accounts</td>
                              <td align="right" style="padding:14px;border-bottom:1px solid #e5e7eb"><span style="font-size:20px;font-weight:800;color:#f59e0b">{high_risk_in_window}</span><br><span style="font-size:11px;color:#6b7280">High risk + renewing soon</span></td>
                            </tr>
                            <tr>
                              <td style="padding:14px;font-size:12px;color:#374151;text-transform:uppercase;letter-spacing:0.5px;font-weight:600">Renewing in 90 Days</td>
                              <td align="right" style="padding:14px"><span style="font-size:20px;font-weight:800;color:#374151">{renewing_90d}</span></td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                {tier_section}
                {accounts_section}
                {drivers_section}

                <!-- Footer -->
                <tr>
                  <td style="border-top:1px solid #e5e7eb;padding-top:20px">
                    <table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">
                      <tr>
                        <td align="center" style="font-size:11px;color:#9ca0b0;padding-bottom:4px">Generated by PickPulse Intelligence &middot; {generated_at}</td>
                      </tr>
                      <tr>
                        <td align="center" style="font-size:11px;color:#9ca0b0">This is an automated executive summary. Log in to PickPulse for full account details and playbook actions.</td>
                      </tr>
                    </table>
                  </td>
                </tr>

              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

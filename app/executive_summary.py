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
    top_priority_accounts: List[Dict[str, Any]] = []
    tier_counts: Dict[str, int] = {}
    risk_drivers: List[str] = []


class ExecutiveSummaryResponse(BaseModel):
    status: str
    recipients: List[str]
    subject: str
    html_body: str
    text_body: str
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
        top_priority_accounts=req.top_priority_accounts[:3],
        tier_counts=req.tier_counts,
        risk_drivers=req.risk_drivers[:5],
        generated_at=generated_at,
    )

    text_body = _build_text(
        total_arr_at_risk=req.total_arr_at_risk,
        projected_recoverable_arr=req.projected_recoverable_arr,
        save_rate=req.save_rate,
        high_risk_in_window=req.high_risk_in_window,
        renewing_90d=req.renewing_90d,
        top_accounts=req.top_accounts[:5],
        top_priority_accounts=req.top_priority_accounts[:3],
        risk_drivers=req.risk_drivers[:5],
        generated_at=generated_at,
    )

    return ExecutiveSummaryResponse(
        status="sent",
        recipients=recipients,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
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
# Plain-text template (for mailto: body)
# -----------------------------------------------------------------------
def _build_text(
    total_arr_at_risk: float,
    projected_recoverable_arr: float,
    save_rate: float,
    high_risk_in_window: int,
    renewing_90d: int,
    top_accounts: List[Dict[str, Any]],
    risk_drivers: List[str],
    generated_at: str,
    top_priority_accounts: Optional[List[Dict[str, Any]]] = None,
) -> str:
    lines = [
        "PickPulse Executive ARR Risk Brief",
        generated_at,
        "",
        "PORTFOLIO SUMMARY",
        f"  ARR at Risk:           {_fmt_currency_simple(total_arr_at_risk)}",
        f"  Projected Recoverable: {_fmt_currency_simple(projected_recoverable_arr)} (at {round(save_rate * 100)}% save rate)",
        f"  Urgent Accounts:       {high_risk_in_window} (high risk + renewing within 30 days)",
        f"  Renewing in 90 Days:   {renewing_90d}",
    ]

    if top_priority_accounts:
        lines += ["", "TOP PRIORITY ACCOUNTS (renewing soon + high risk)"]
        for acct in top_priority_accounts:
            name = acct.get("name") or acct.get("account_id") or "—"
            risk = acct.get("churn_risk_pct", 0)
            dur = acct.get("days_until_renewal")
            renewal_str = f"{int(dur)}d" if dur is not None else "unknown"
            arr_risk = _fmt_currency_simple(acct.get("arr_at_risk", 0))
            lines.append(f"  {name}: {risk}% risk  |  Renewal in {renewal_str}  |  At risk {arr_risk}")

    if top_accounts:
        lines += ["", "TOP ACCOUNTS REQUIRING ATTENTION"]
        for acct in top_accounts:
            name = acct.get("name") or acct.get("account_id") or "—"
            risk = acct.get("churn_risk_pct", 0)
            arr = _fmt_currency_simple(acct.get("arr", 0))
            arr_risk = _fmt_currency_simple(acct.get("arr_at_risk", 0))
            lines.append(f"  {name}: {risk}% risk  |  ARR {arr}  |  At risk {arr_risk}")

    if risk_drivers:
        lines += ["", "TOP RISK DRIVERS"]
        for d in risk_drivers:
            lines.append(f"  • {d}")

    lines += ["", "—", "Generated by PickPulse Intelligence. Log in for full details."]
    return "\n".join(lines)


def _fmt_currency_simple(val: float) -> str:
    """Plain-text currency formatter (no HTML)."""
    try:
        val = float(val)
    except (TypeError, ValueError):
        return "$0"
    if val >= 1_000_000:
        return f"${val / 1_000_000:,.1f}M"
    if val >= 1_000:
        return f"${val / 1_000:,.0f}K"
    return f"${val:,.0f}"


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
    top_priority_accounts: Optional[List[Dict[str, Any]]] = None,
) -> str:
    # Top accounts table rows
    acct_rows = ""
    for i, acct in enumerate(top_accounts):
        bg = "#f9fafb" if i % 2 == 1 else "#ffffff"
        risk_pct = acct.get("churn_risk_pct", 0)
        risk_color = "#ef4444" if risk_pct >= 30 else "#f59e0b" if risk_pct >= 20 else "#10b981"
        renewal_days = acct.get("days_until_renewal", "—")
        renewal_label = f"{renewal_days}d" if isinstance(renewal_days, (int, float)) else renewal_days
        acct_rows += f"""<tr>
              <td style="padding:10px 14px;font-size:13px;font-weight:600;color:#1a1d26;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif" bgcolor="{bg}">{acct.get("name") or acct.get("account_id") or acct.get("customer_id") or "—"}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif" bgcolor="{bg}"><span style="color:{risk_color};font-weight:700;font-family:Arial,sans-serif">{risk_pct}%</span></td>
              <td align="right" style="padding:10px 14px;font-size:13px;color:#374151;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif" bgcolor="{bg}">{_fmt_currency(acct.get("arr", 0))}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;font-weight:700;color:#ef4444;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif" bgcolor="{bg}">{_fmt_currency(acct.get("arr_at_risk", 0))}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;color:#374151;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif" bgcolor="{bg}">{renewal_label}</td>
            </tr>"""

    # Tier distribution rows — use Unicode filled square (&#9632;) instead of
    # display:inline-block, which Outlook's Word renderer does not support.
    tier_colors = {"High Risk": "#ef4444", "Medium Risk": "#f59e0b", "Low Risk": "#10b981"}
    tier_rows = ""
    for tier, count in tier_counts.items():
        color = tier_colors.get(tier, "#6b7280")
        tier_rows += f"""<tr>
              <td style="padding:8px 14px;font-size:13px;color:#374151;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif">
                <span style="color:{color};font-size:13px;margin-right:6px;font-family:Arial,sans-serif">&#9632;</span>{tier}
              </td>
              <td align="right" style="padding:8px 14px;font-size:13px;font-weight:700;color:{color};border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif">{count}</td>
            </tr>"""

    # Risk drivers rows
    driver_rows = ""
    for d in risk_drivers:
        driver_rows += f"""<tr>
              <td style="padding:6px 14px;font-size:13px;color:#374151;border-bottom:1px solid #f3f4f6;font-family:Arial,sans-serif">&#8226;&nbsp; {d}</td>
            </tr>"""

    # Top priority accounts rows
    priority_rows = ""
    for i, acct in enumerate(top_priority_accounts or []):
        bg = "#f9fafb" if i % 2 == 1 else "#ffffff"
        risk_pct = acct.get("churn_risk_pct", 0)
        dur = acct.get("days_until_renewal")
        renewal_label = f"{int(dur)}d" if dur is not None else "—"
        arr_risk = _fmt_currency(acct.get("arr_at_risk", 0))
        priority_rows += f"""<tr>
              <td style="padding:10px 14px;font-size:13px;font-weight:600;color:#1a1d26;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif" bgcolor="{bg}">{acct.get("name") or acct.get("account_id") or "—"}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif" bgcolor="{bg}"><span style="color:#ef4444;font-weight:700;font-family:Arial,sans-serif">{risk_pct}%</span></td>
              <td align="right" style="padding:10px 14px;font-size:13px;color:#f59e0b;font-weight:700;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif" bgcolor="{bg}">{renewal_label}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;font-weight:700;color:#ef4444;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif" bgcolor="{bg}">{arr_risk}</td>
            </tr>"""

    # Conditional sections
    priority_section = ""
    if priority_rows:
        priority_section = f"""
        <!-- Top Priority Accounts -->
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr>
                <td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:#1a1d26;font-family:Arial,sans-serif">Top Priority Accounts <span style="font-size:12px;color:#f59e0b;font-weight:600;font-family:Arial,sans-serif">(renewing within 30 days)</span></td>
              </tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #fde68a;font-family:Arial,sans-serif">
                    <tr bgcolor="#fffbeb">
                      <th align="left" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#92400e;border-bottom:1px solid #fde68a;font-weight:600;font-family:Arial,sans-serif">Account</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#92400e;border-bottom:1px solid #fde68a;font-weight:600;font-family:Arial,sans-serif">Risk %</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#92400e;border-bottom:1px solid #fde68a;font-weight:600;font-family:Arial,sans-serif">Renewal</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#92400e;border-bottom:1px solid #fde68a;font-weight:600;font-family:Arial,sans-serif">ARR at Risk</th>
                    </tr>
                    {priority_rows}
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    tier_section = ""
    if tier_rows:
        tier_section = f"""
        <!-- Risk Distribution -->
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr>
                <td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:#1a1d26;font-family:Arial,sans-serif">Risk Distribution</td>
              </tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #e5e7eb;font-family:Arial,sans-serif">
                    <tr bgcolor="#f8f9fb">
                      <th align="left" style="padding:8px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600;font-family:Arial,sans-serif">Tier</th>
                      <th align="right" style="padding:8px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600;font-family:Arial,sans-serif">Accounts</th>
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
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr>
                <td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:#1a1d26;font-family:Arial,sans-serif">Top Accounts Requiring Attention</td>
              </tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #e5e7eb;font-family:Arial,sans-serif">
                    <tr bgcolor="#f8f9fb">
                      <th align="left" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600;font-family:Arial,sans-serif">Account</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600;font-family:Arial,sans-serif">Risk %</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600;font-family:Arial,sans-serif">ARR</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600;font-family:Arial,sans-serif">ARR at Risk</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;border-bottom:1px solid #e5e7eb;font-weight:600;font-family:Arial,sans-serif">Renewal</th>
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
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr>
                <td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:#1a1d26;font-family:Arial,sans-serif">Top Risk Drivers</td>
              </tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;font-family:Arial,sans-serif">
                    {driver_rows}
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="format-detection" content="telephone=no,date=no,address=no,email=no,url=no">
  <title>PickPulse Executive ARR Risk Brief</title>
</head>
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
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
                      <tr>
                        <td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:#1a1d26;font-family:Arial,sans-serif">Portfolio Summary</td>
                      </tr>
                      <tr>
                        <td>
                          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #e5e7eb;font-family:Arial,sans-serif">
                            <tr bgcolor="#fef2f2">
                              <td style="padding:14px;font-size:12px;color:#991b1b;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid #e5e7eb;width:50%;font-family:Arial,sans-serif">ARR at Risk</td>
                              <td align="right" style="padding:14px;font-size:20px;font-weight:800;color:#ef4444;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif">{_fmt_currency(total_arr_at_risk)}</td>
                            </tr>
                            <tr bgcolor="#f0fdf4">
                              <td style="padding:14px;font-size:12px;color:#166534;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif">Projected Recoverable</td>
                              <td align="right" style="padding:14px;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif">
                                <span style="display:block;font-size:20px;font-weight:800;color:#10b981;font-family:Arial,sans-serif">{_fmt_currency(projected_recoverable_arr)}</span>
                                <span style="display:block;font-size:11px;color:#6b7280;font-family:Arial,sans-serif">at {round(save_rate * 100)}% save rate</span>
                              </td>
                            </tr>
                            <tr>
                              <td style="padding:14px;font-size:12px;color:#92400e;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif">Urgent Accounts</td>
                              <td align="right" style="padding:14px;border-bottom:1px solid #e5e7eb;font-family:Arial,sans-serif">
                                <span style="display:block;font-size:20px;font-weight:800;color:#f59e0b;font-family:Arial,sans-serif">{high_risk_in_window}</span>
                                <span style="display:block;font-size:11px;color:#6b7280;font-family:Arial,sans-serif">High risk + renewing within 30 days</span>
                              </td>
                            </tr>
                            <tr>
                              <td style="padding:14px;font-size:12px;color:#374151;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;font-family:Arial,sans-serif">Renewing in 90 Days</td>
                              <td align="right" style="padding:14px;font-size:20px;font-weight:800;color:#374151;font-family:Arial,sans-serif">{renewing_90d}</td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                {priority_section}
                {tier_section}
                {accounts_section}
                {drivers_section}

                <!-- Footer -->
                <tr>
                  <td style="border-top:1px solid #e5e7eb;padding-top:20px">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
                      <tr>
                        <td align="center" style="font-size:11px;color:#9ca0b0;padding-bottom:4px;font-family:Arial,sans-serif">Generated by PickPulse Intelligence &middot; {generated_at}</td>
                      </tr>
                      <tr>
                        <td align="center" style="font-size:11px;color:#9ca0b0;font-family:Arial,sans-serif">This is an automated executive summary. Log in to PickPulse for full account details and playbook actions.</td>
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

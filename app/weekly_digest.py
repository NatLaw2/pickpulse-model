"""Weekly Revenue Digest — CRO-ready forwarded email.

Generates a structured weekly email a CRO can forward to their board.
Content is derived entirely from live data; no manual input required.

Section order (cause → effect):
  Key Insight          — one-sentence summary
  1. Top downside accounts  — the accounts driving risk
  2. Forecast snapshot      — what the aggregate numbers say
  3. Improving health       — accounts moving in the right direction
  4. Coverage note          — data quality disclosure (conditional)
  Footer: key assumptions

────────────────────────────────────────────────────────────────────────────
Week-over-week comparison
────────────────────────────────────────────────────────────────────────────
Uses a stored snapshot (JSON on disk) rather than historical recompute.
The snapshot is written each time a digest is generated. If no prior
snapshot exists, WoW fields are null and the digest says "first run."
Stored at: {DATA_DIR}/outputs/{tenant_id}/weekly_digest_snapshot.json

────────────────────────────────────────────────────────────────────────────
Growth signal drivers
────────────────────────────────────────────────────────────────────────────
Accounts are flagged as "improving" when their churn score dropped >= 5 pp
vs the score from 7 days ago. The driver label is derived from whichever
health signal changed most favorably: monthly_logins ↑, nps_score ↑,
days_since_last_login ↓, or support_tickets ↓. Falls back to the risk
score delta if no signal comparison is available.

────────────────────────────────────────────────────────────────────────────
Scheduling
────────────────────────────────────────────────────────────────────────────
generate_weekly_digest(tenant_id, send=False) is the primary entry point.
Passing send=True will attempt email delivery (SMTP, if configured).
This function can be called directly by a cron trigger without any changes.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Minimum score improvement (in probability units) to qualify as a growth signal.
IMPROVEMENT_THRESHOLD = 0.05   # 5 percentage points

# Maximum accounts shown in the downside table.
MAX_DOWNSIDE_ACCOUNTS = 3

# Maximum accounts shown in the improving health table.
MAX_GROWTH_ACCOUNTS = 5

# WoW movement is "material" above this fractional threshold.
MATERIAL_MOVE_PCT = 0.02  # 2%


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _snapshot_path(tenant_id: str) -> str:
    data_dir = os.environ.get("DATA_DIR", "data")
    out_dir = os.path.join(data_dir, "outputs", tenant_id)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, "weekly_digest_snapshot.json")


def _load_snapshot(tenant_id: str) -> Optional[Dict[str, Any]]:
    path = _snapshot_path(tenant_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("weekly_digest: snapshot read failed (%s)", exc)
        return None


def _save_snapshot(tenant_id: str, snapshot: Dict[str, Any]) -> None:
    path = _snapshot_path(tenant_id)
    try:
        with open(path, "w") as f:
            json.dump(snapshot, f, indent=2)
    except Exception as exc:
        logger.warning("weekly_digest: snapshot write failed (%s)", exc)


# ---------------------------------------------------------------------------
# Score delta helpers (for growth signals)
# ---------------------------------------------------------------------------

def _fetch_recent_scores_by_account(
    tenant_id: str,
    days_back: int = 14,
) -> Dict[str, List[Tuple[str, float]]]:
    """Fetch all scores from the last `days_back` days.

    Returns {account_id: [(score_date_str, churn_probability_0_to_1), ...]}
    sorted ascending by date per account.
    """
    from app.storage.db import get_client
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    try:
        sb = get_client()
        res = (
            sb.table("churn_scores_daily")
            .select("account_id, score_date, churn_risk_pct")
            .eq("tenant_id", tenant_id)
            .gte("score_date", cutoff)
            .order("score_date", desc=False)
            .limit(20000)
            .execute()
        )
        result: Dict[str, List[Tuple[str, float]]] = {}
        for row in (res.data or []):
            aid = row["account_id"]
            prob = float(row["churn_risk_pct"]) / 100.0
            result.setdefault(aid, []).append((str(row["score_date"]), prob))
        return result
    except Exception as exc:
        logger.warning("weekly_digest: _fetch_recent_scores_by_account failed (%s)", exc)
        return {}


def _compute_score_deltas(
    recent_by_account: Dict[str, List[Tuple[str, float]]],
    today: date,
) -> Dict[str, float]:
    """Return {account_id: delta} where delta = today_prob - week_ago_prob.

    Negative delta = improvement (lower churn risk).
    Only computed for accounts that have both a recent score and a score
    from approximately 7 days ago (within ±3-day tolerance).
    """
    window_lo = (today - timedelta(days=10)).isoformat()
    window_hi = (today - timedelta(days=4)).isoformat()
    today_str = today.isoformat()
    today_minus1 = (today - timedelta(days=1)).isoformat()

    deltas: Dict[str, float] = {}

    for account_id, entries in recent_by_account.items():
        # Today's score: latest entry at or after today - 1 (allow 1 day lag)
        today_score: Optional[float] = None
        for d_str, prob in reversed(entries):
            if d_str >= today_minus1:
                today_score = prob
                break

        # Week-ago score: latest entry within the ±3-day window around 7 days ago
        week_ago_score: Optional[float] = None
        for d_str, prob in reversed(entries):
            if window_lo <= d_str <= window_hi:
                week_ago_score = prob
                break

        if today_score is not None and week_ago_score is not None:
            deltas[account_id] = today_score - week_ago_score  # negative = improving

    return deltas


# ---------------------------------------------------------------------------
# Signal driver helpers (for growth signal account labels)
# ---------------------------------------------------------------------------

def _fetch_signals_for_accounts(
    account_ids: List[str],
    tenant_id: str,
    days_back: int = 14,
) -> Dict[str, Dict[str, Any]]:
    """Fetch the most recent signals for a specific set of accounts within
    the last `days_back` days.

    Returns {account_id: {signal_key: (current_value, week_ago_value)}}
    where week_ago_value may be None if not available.
    """
    if not account_ids:
        return {}

    from app.storage.db import get_client
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    today_str = date.today().isoformat()
    week_ago_lo = (date.today() - timedelta(days=10)).isoformat()
    week_ago_hi = (date.today() - timedelta(days=4)).isoformat()

    try:
        sb = get_client()
        res = (
            sb.table("account_signals_daily")
            .select("account_id, signal_key, signal_value, signal_date")
            .eq("tenant_id", tenant_id)
            .in_("account_id", account_ids)
            .gte("signal_date", cutoff)
            .order("signal_date", desc=True)
            .limit(5000)
            .execute()
        )
        if not res.data:
            return {}

        # Build per-account, per-signal: {aid: {key: {"current": v, "week_ago": v}}}
        result: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
        for row in res.data:
            if row["signal_value"] is None:
                continue
            aid = row["account_id"]
            key = row["signal_key"]
            d_str = str(row["signal_date"])
            val = float(row["signal_value"])

            result.setdefault(aid, {}).setdefault(key, {"current": None, "week_ago": None})
            cell = result[aid][key]

            # Current: most recent (date desc, first occurrence wins)
            if cell["current"] is None and d_str <= today_str:
                cell["current"] = val

            # Week-ago: most recent within the window
            if cell["week_ago"] is None and week_ago_lo <= d_str <= week_ago_hi:
                cell["week_ago"] = val

        return result
    except Exception as exc:
        logger.warning("weekly_digest: _fetch_signals_for_accounts failed (%s)", exc)
        return {}


def _determine_health_driver(
    signal_comparisons: Dict[str, Dict[str, Optional[float]]],
    score_delta: float,
) -> str:
    """Return a short human-readable driver string for an improving account.

    Checks which health signal changed most favorably.
    Falls back to the score delta if no signal comparison is available.
    """
    # Signal: (label, higher_is_better)
    candidates = [
        ("monthly_logins",       "Usage ↑",              True),
        ("nps_score",            "NPS improved",          True),
        ("days_since_last_login","Login activity ↑",      False),  # lower = better
        ("support_tickets",      "Support volume ↓",      False),  # lower = better
    ]

    best_label: Optional[str] = None
    best_delta = 0.0

    for key, label, higher_is_better in candidates:
        if key not in signal_comparisons:
            continue
        cell = signal_comparisons[key]
        curr, prev = cell.get("current"), cell.get("week_ago")
        if curr is None or prev is None or prev == 0:
            continue
        pct_change = (curr - prev) / abs(prev)
        # Normalize: positive = good
        signed = pct_change if higher_is_better else -pct_change
        if signed > best_delta:
            best_delta = signed
            best_label = label

    if best_label:
        return best_label

    # Fallback: use score delta
    improvement_pp = round(abs(score_delta) * 100)
    return f"Risk score ↓ {improvement_pp}pp"


# ---------------------------------------------------------------------------
# Key insight + WoW driver generation (template-based)
# ---------------------------------------------------------------------------

def _generate_key_insight(
    forecast_base: float,
    arr_at_risk: float,
    prior_snapshot: Optional[Dict[str, Any]],
    n_downside: int,
    n_growth: int,
    wow_delta: Optional[float],
    arr_coverage_pct: float,
) -> str:
    """Generate a one-sentence key insight from digest data."""
    if arr_at_risk == 0:
        return "No ARR at risk from accounts renewing in the next 90 days."

    if prior_snapshot is None:
        # First run — no WoW comparison available
        return (
            f"Model projects {_fmt(arr_at_risk)} ARR at risk across "
            f"{n_downside} high-priority accounts renewing in the next 90 days."
        )

    if wow_delta is None:
        return (
            f"{_fmt(arr_at_risk)} ARR at risk this week across "
            f"{n_downside} high-priority renewing accounts."
        )

    delta_pct = abs(wow_delta) / prior_snapshot["forecast_base"] if prior_snapshot.get("forecast_base") else 0

    if wow_delta < 0 and delta_pct >= MATERIAL_MOVE_PCT:
        return (
            f"Forecast declined {_fmt(abs(wow_delta))} vs last week — "
            f"{n_downside} accounts represent the primary downside risk."
        )
    elif wow_delta > 0 and delta_pct >= MATERIAL_MOVE_PCT:
        return (
            f"Forecast improved {_fmt(wow_delta)} vs last week, "
            f"driven by {n_growth} account{'s' if n_growth != 1 else ''} showing better health signals."
        )
    else:
        return (
            f"Forecast stable week-over-week. {_fmt(arr_at_risk)} ARR at risk "
            f"from {n_downside} accounts renewing in the next 90 days."
        )


def _generate_wow_drivers(
    prior_snapshot: Optional[Dict[str, Any]],
    current_top_downside: List[Dict[str, Any]],
    wow_delta: Optional[float],
) -> List[str]:
    """Generate 1-2 directional bullets explaining WoW movement.

    Does not over-attribute. Returns empty list if no prior snapshot
    or if the movement is not material.
    """
    if prior_snapshot is None or wow_delta is None:
        return []

    prior_base = prior_snapshot.get("forecast_base", 0)
    if prior_base == 0:
        return []

    delta_pct = abs(wow_delta) / prior_base
    if delta_pct < MATERIAL_MOVE_PCT:
        return []

    prior_ids = {a["account_id"] for a in prior_snapshot.get("top_downside", [])}
    current_ids = {a["account_id"] for a in current_top_downside}

    bullets: List[str] = []

    # New accounts entering the top-downside list
    new_entries = [a for a in current_top_downside if a["account_id"] not in prior_ids]
    if new_entries:
        names = ", ".join(a["name"] or "unknown" for a in new_entries[:2])
        suffix = f" and {len(new_entries) - 2} others" if len(new_entries) > 2 else ""
        bullets.append(f"{names}{suffix} newly entered the high-risk window")

    # Accounts that left (possibly renewed or improved)
    exited = prior_ids - current_ids
    if exited and len(bullets) < 2:
        bullets.append(
            f"{len(exited)} account{'s' if len(exited) != 1 else ''} "
            f"exited the high-risk window (renewed or risk improved)"
        )

    # If no structural change, it's score drift on existing accounts
    if not bullets and wow_delta < 0:
        if current_top_downside:
            name = current_top_downside[0].get("name") or "Top account"
            bullets.append(
                f"Risk scores deteriorated on existing accounts, led by {name}"
            )

    return bullets[:2]


# ---------------------------------------------------------------------------
# Currency formatter (shared)
# ---------------------------------------------------------------------------

def _fmt(val: float) -> str:
    """Short currency formatter for prose (no HTML)."""
    try:
        val = float(val)
    except (TypeError, ValueError):
        return "$0"
    if val >= 1_000_000:
        return f"${val / 1_000_000:,.1f}M"
    if val >= 1_000:
        return f"${val / 1_000:,.0f}K"
    return f"${val:,.0f}"


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

_RED   = "#ef4444"
_AMBER = "#f59e0b"
_GREEN = "#10b981"
_PURPLE = "#7B61FF"
_DARK  = "#1a1d26"
_MUTED = "#6b7280"
_BORDER = "#e5e7eb"


def _risk_color(prob: float) -> str:
    if prob >= 0.50:
        return _RED
    if prob >= 0.30:
        return _AMBER
    return _GREEN


def _build_html(digest_data: Dict[str, Any]) -> str:
    date_str     = digest_data["as_of"]
    insight      = digest_data["key_insight"]
    downside     = digest_data["top_downside"]
    growth       = digest_data["growth_signals"]
    forecast     = digest_data["forecast_snapshot"]
    wow_drivers  = digest_data["wow_drivers"]
    coverage     = digest_data["coverage"]
    concentration = digest_data.get("arr_concentration")

    # ---- Key insight box ----
    insight_html = f"""
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="background-color:#f8f9fb;border-left:3px solid {_PURPLE};padding:14px 18px;font-size:14px;color:{_DARK};font-style:italic;font-family:Arial,sans-serif;border-radius:0 4px 4px 0">
                  {insight}
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    # ---- Section 1: Top downside accounts ----
    downside_rows = ""
    for i, acct in enumerate(downside):
        bg = "#f9fafb" if i % 2 else "#ffffff"
        prob = acct.get("churn_probability", 0)
        renewal = acct.get("renewal_date", "—")
        if acct.get("renewal_date_precision") == "month_estimate":
            renewal_label = f"~{renewal[:7]}"
        else:
            renewal_label = renewal
        downside_rows += f"""<tr>
              <td style="padding:10px 14px;font-size:13px;font-weight:600;color:{_DARK};border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif" bgcolor="{bg}">{acct.get('name') or acct.get('account_id') or '—'}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif" bgcolor="{bg}"><span style="color:{_risk_color(prob)};font-weight:700;font-family:Arial,sans-serif">{round(prob * 100)}%</span></td>
              <td align="right" style="padding:10px 14px;font-size:13px;color:#374151;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif" bgcolor="{bg}">{_fmt(acct.get('arr', 0))}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;font-weight:700;color:{_RED};border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif" bgcolor="{bg}">{_fmt(acct.get('expected_arr_at_risk', 0))}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;color:{_MUTED};border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif" bgcolor="{bg}">{renewal_label}</td>
            </tr>"""

    # ARR concentration insight (below downside table)
    concentration_html = ""
    if concentration and concentration.get("total_arr_at_risk", 0) > 0:
        conc_pct = round(concentration["top3_pct"])
        n = concentration["n_accounts"]
        concentration_html = f"""
              <tr>
                <td style="padding:8px 0 0 0;font-size:12px;color:{_MUTED};font-family:Arial,sans-serif">
                  Top {n} account{'s' if n != 1 else ''} represent <strong>{conc_pct}%</strong> of forecast ARR at risk.
                </td>
              </tr>"""

    downside_section = ""
    if downside_rows:
        downside_section = f"""
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr><td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:{_DARK};font-family:Arial,sans-serif">Top Downside Accounts</td></tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid {_BORDER};font-family:Arial,sans-serif">
                    <tr bgcolor="#f8f9fb">
                      <th align="left"  style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:{_MUTED};border-bottom:1px solid {_BORDER};font-weight:600;font-family:Arial,sans-serif">Account</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:{_MUTED};border-bottom:1px solid {_BORDER};font-weight:600;font-family:Arial,sans-serif">Risk</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:{_MUTED};border-bottom:1px solid {_BORDER};font-weight:600;font-family:Arial,sans-serif">ARR</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:{_MUTED};border-bottom:1px solid {_BORDER};font-weight:600;font-family:Arial,sans-serif">Expected Loss</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:{_MUTED};border-bottom:1px solid {_BORDER};font-weight:600;font-family:Arial,sans-serif">Renewal</th>
                    </tr>
                    {downside_rows}
                  </table>
                </td>
              </tr>
              {concentration_html}
            </table>
          </td>
        </tr>"""

    # ---- WoW drivers bullets (between downside and forecast) ----
    wow_section = ""
    if wow_drivers:
        bullets_html = "".join(
            f'<tr><td style="padding:4px 14px;font-size:13px;color:#374151;font-family:Arial,sans-serif">&#8226;&nbsp; {d}</td></tr>'
            for d in wow_drivers
        )
        wow_section = f"""
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr><td style="padding:0 0 8px 0;font-size:13px;font-weight:700;color:{_DARK};font-family:Arial,sans-serif">Primary drivers of change</td></tr>
              <tr><td>
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
                  {bullets_html}
                </table>
              </td></tr>
            </table>
          </td>
        </tr>"""

    # ---- Section 2: Forecast snapshot ----
    wow_row = ""
    if forecast.get("prior_forecast_base") is not None:
        delta = forecast["forecast_delta"]
        delta_pct = forecast.get("forecast_delta_pct", 0)
        delta_color = _GREEN if delta >= 0 else _RED
        sign = "+" if delta >= 0 else ""
        prior_date = forecast.get("prior_forecast_date", "prior week")
        wow_row = f"""<tr>
                            <td style="padding:10px 14px;font-size:12px;color:#92400e;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif">vs {prior_date}</td>
                            <td align="right" style="padding:10px 14px;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif">
                              <span style="font-size:16px;font-weight:800;color:{delta_color};font-family:Arial,sans-serif">{sign}{_fmt(delta)}</span>
                              <span style="font-size:11px;color:{_MUTED};margin-left:6px;font-family:Arial,sans-serif">({sign}{delta_pct:.1f}%)</span>
                            </td>
                          </tr>"""

    coverage_flag = ""
    if forecast.get("arr_coverage_pct", 100) < 50:
        coverage_flag = f'<span style="margin-left:8px;color:{_AMBER};font-size:11px;font-family:Arial,sans-serif">&#9888; low coverage</span>'

    forecast_section = f"""
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr><td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:{_DARK};font-family:Arial,sans-serif">Forecast Snapshot</td></tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid {_BORDER};font-family:Arial,sans-serif">
                    <tr bgcolor="#f0fdf4">
                      <td style="padding:14px;font-size:12px;color:#166534;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif">Expected ARR · {forecast.get('horizon_date', '')}</td>
                      <td align="right" style="padding:14px;font-size:22px;font-weight:800;color:#10b981;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif">{_fmt(forecast['forecast_base'])}</td>
                    </tr>
                    <tr bgcolor="#fef2f2">
                      <td style="padding:14px;font-size:12px;color:#991b1b;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif">ARR at Risk (model estimate)</td>
                      <td align="right" style="padding:14px;font-size:22px;font-weight:800;color:{_RED};border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif">{_fmt(forecast['arr_at_risk'])}</td>
                    </tr>
                    {wow_row}
                    <tr>
                      <td style="padding:10px 14px;font-size:12px;color:#374151;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif">Current ARR</td>
                      <td align="right" style="padding:10px 14px;font-size:16px;font-weight:700;color:#374151;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif">{_fmt(forecast['current_arr'])}</td>
                    </tr>
                    <tr>
                      <td style="padding:10px 14px;font-size:12px;color:#374151;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;font-family:Arial,sans-serif">Forecast Coverage{coverage_flag}</td>
                      <td align="right" style="padding:10px 14px;font-size:13px;color:{_MUTED};font-family:Arial,sans-serif">{forecast.get('arr_coverage_pct', 0):.0f}% of ARR · {forecast.get('accounts_in_forecast', 0)} accounts</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    # ---- Section 3: Improving health signals ----
    growth_rows = ""
    for i, acct in enumerate(growth):
        bg = "#f9fafb" if i % 2 else "#ffffff"
        improvement_pp = round(abs(acct.get("score_delta", 0)) * 100)
        driver = acct.get("driver", f"Risk score ↓ {improvement_pp}pp")
        growth_rows += f"""<tr>
              <td style="padding:10px 14px;font-size:13px;font-weight:600;color:{_DARK};border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif" bgcolor="{bg}">{acct.get('name') or acct.get('account_id') or '—'}</td>
              <td align="right" style="padding:10px 14px;font-size:13px;color:{_GREEN};font-weight:700;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif" bgcolor="{bg}">&#8595; {improvement_pp}pp</td>
              <td align="right" style="padding:10px 14px;font-size:13px;color:#374151;border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif" bgcolor="{bg}">{_fmt(acct.get('arr', 0))}</td>
              <td style="padding:10px 14px;font-size:12px;color:{_GREEN};border-bottom:1px solid {_BORDER};font-family:Arial,sans-serif" bgcolor="{bg}">{driver}</td>
            </tr>"""

    growth_section = ""
    if growth_rows:
        growth_section = f"""
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr><td style="padding:0 0 10px 0;font-size:15px;font-weight:700;color:{_DARK};font-family:Arial,sans-serif">Accounts Showing Improving Health Signals</td></tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #d1fae5;font-family:Arial,sans-serif">
                    <tr bgcolor="#f0fdf4">
                      <th align="left"  style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#166534;border-bottom:1px solid #d1fae5;font-weight:600;font-family:Arial,sans-serif">Account</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#166534;border-bottom:1px solid #d1fae5;font-weight:600;font-family:Arial,sans-serif">Risk &#8595;</th>
                      <th align="right" style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#166534;border-bottom:1px solid #d1fae5;font-weight:600;font-family:Arial,sans-serif">ARR</th>
                      <th align="left"  style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#166534;border-bottom:1px solid #d1fae5;font-weight:600;font-family:Arial,sans-serif">Signal</th>
                    </tr>
                    {growth_rows}
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    # ---- Coverage note (conditional) ----
    coverage_note = ""
    arr_excluded = coverage.get("arr_excluded", 0)
    if arr_excluded > 0:
        n_missing = coverage.get("accounts_scored_no_renewal_date", 0)
        coverage_note = f"""
        <tr>
          <td style="padding:0 0 24px 0">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr>
                <td style="background-color:#fffbeb;border:1px solid #fde68a;padding:12px 16px;font-size:12px;color:#92400e;font-family:Arial,sans-serif;border-radius:4px">
                  &#9888;&nbsp; <strong>{_fmt(arr_excluded)}</strong> ARR excluded from forecast — renewal date unknown for {n_missing} scored account{'s' if n_missing != 1 else ''}.
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    # ---- Footer assumptions ----
    footer_html = f"""
        <tr>
          <td style="border-top:1px solid {_BORDER};padding-top:20px">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
              <tr>
                <td style="font-size:11px;color:#9ca0b0;padding-bottom:4px;font-family:Arial,sans-serif">
                  Forecast covers accounts renewing in the next 90 days with a known churn score and renewal date.
                  &#8220;Expected loss&#8221; = ARR &#215; churn probability (model estimate, not a guarantee).
                </td>
              </tr>
              <tr>
                <td style="font-size:11px;color:#9ca0b0;padding-bottom:4px;font-family:Arial,sans-serif">
                  Model uncertainty range: &#177;1&#963; (independent Bernoulli). Correlated events not modeled.
                </td>
              </tr>
              <tr>
                <td align="center" style="font-size:11px;color:#9ca0b0;padding-top:8px;font-family:Arial,sans-serif">
                  Generated by PickPulse Intelligence &middot; {digest_data['as_of']} &middot; Log in for full account details
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
  <title>PickPulse Weekly Revenue Digest</title>
</head>
<body style="margin:0;padding:0;font-family:Arial,sans-serif;background-color:#f5f6f8" bgcolor="#f5f6f8">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f5f6f8" style="background-color:#f5f6f8">
    <tr>
      <td align="center" style="padding:24px 16px">
        <table width="600" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif;max-width:600px">

          <!-- Header -->
          <tr>
            <td align="center" bgcolor="{_PURPLE}" style="background-color:{_PURPLE};padding:32px 28px">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr><td align="center" style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#c4b5fd;font-weight:600;padding-bottom:8px;font-family:Arial,sans-serif">PickPulse Intelligence</td></tr>
                <tr><td align="center" style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.3px;font-family:Arial,sans-serif">Weekly Revenue Digest</td></tr>
                <tr><td align="center" style="font-size:12px;color:#c4b5fd;padding-top:8px;font-family:Arial,sans-serif">Week of {digest_data['as_of']}</td></tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td bgcolor="#ffffff" style="background-color:#ffffff;padding:28px;border-left:1px solid {_BORDER};border-right:1px solid {_BORDER};border-bottom:1px solid {_BORDER}">
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,sans-serif">
                {insight_html}
                {downside_section}
                {wow_section}
                {forecast_section}
                {growth_section}
                {coverage_note}
                {footer_html}
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Plain-text fallback
# ---------------------------------------------------------------------------

def _build_text(digest_data: Dict[str, Any]) -> str:
    lines = [
        "PickPulse Weekly Revenue Digest",
        f"Week of {digest_data['as_of']}",
        "",
        digest_data["key_insight"],
        "",
    ]

    if digest_data["top_downside"]:
        lines.append("TOP DOWNSIDE ACCOUNTS")
        for a in digest_data["top_downside"]:
            name = a.get("name") or a.get("account_id") or "—"
            lines.append(
                f"  {name}: {round(a.get('churn_probability', 0) * 100)}% risk  "
                f"| ARR {_fmt(a.get('arr', 0))}  "
                f"| Expected loss {_fmt(a.get('expected_arr_at_risk', 0))}"
            )
        if digest_data.get("arr_concentration"):
            c = digest_data["arr_concentration"]
            lines.append(
                f"  Top {c['n_accounts']} accounts = {round(c['top3_pct'])}% of forecast ARR at risk"
            )
        lines.append("")

    if digest_data["wow_drivers"]:
        lines.append("PRIMARY DRIVERS OF CHANGE")
        for d in digest_data["wow_drivers"]:
            lines.append(f"  • {d}")
        lines.append("")

    fs = digest_data["forecast_snapshot"]
    lines += [
        "FORECAST SNAPSHOT",
        f"  Expected ARR ({fs.get('horizon_date', '90d')}):  {_fmt(fs['forecast_base'])}",
        f"  ARR at Risk (est.):             {_fmt(fs['arr_at_risk'])}",
        f"  Current ARR:                    {_fmt(fs['current_arr'])}",
        f"  Coverage:                       {fs.get('arr_coverage_pct', 0):.0f}%",
    ]
    if fs.get("prior_forecast_base") is not None:
        sign = "+" if fs["forecast_delta"] >= 0 else ""
        lines.append(
            f"  vs {fs.get('prior_forecast_date', 'prior week')}:  "
            f"{sign}{_fmt(fs['forecast_delta'])} ({sign}{fs.get('forecast_delta_pct', 0):.1f}%)"
        )
    lines.append("")

    if digest_data["growth_signals"]:
        lines.append("ACCOUNTS SHOWING IMPROVING HEALTH SIGNALS")
        for a in digest_data["growth_signals"]:
            name = a.get("name") or a.get("account_id") or "—"
            pp = round(abs(a.get("score_delta", 0)) * 100)
            driver = a.get("driver", f"Risk score ↓ {pp}pp")
            lines.append(f"  {name}: risk ↓{pp}pp  | ARR {_fmt(a.get('arr', 0))}  | {driver}")
        lines.append("")

    cov = digest_data["coverage"]
    if cov.get("arr_excluded", 0) > 0:
        lines.append(
            f"Note: {_fmt(cov['arr_excluded'])} ARR excluded — "
            f"renewal date unknown for {cov.get('accounts_scored_no_renewal_date', 0)} accounts."
        )
        lines.append("")

    lines += [
        "—",
        "Forecast covers accounts renewing in 90 days with a known score and renewal date.",
        '"Expected loss" = ARR × churn probability (model estimate, not a guarantee).',
        "Generated by PickPulse Intelligence. Log in for full details.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subject line
# ---------------------------------------------------------------------------

def _build_subject(digest_data: Dict[str, Any]) -> str:
    fs = digest_data["forecast_snapshot"]
    base_str = _fmt(fs["forecast_base"])
    date_str = digest_data["as_of"]

    # If WoW movement is material, call it out in the subject
    if fs.get("prior_forecast_base") is not None:
        delta = fs.get("forecast_delta", 0)
        prior_base = fs.get("prior_forecast_base", 1)
        delta_pct = abs(delta) / prior_base if prior_base else 0
        if delta_pct >= MATERIAL_MOVE_PCT and delta < 0:
            n = len(digest_data.get("top_downside", []))
            return (
                f"PickPulse Revenue Digest · {date_str} · "
                f"Forecast down {_fmt(abs(delta))} vs last week — "
                f"{n} high-risk account{'s' if n != 1 else ''}"
            )
        elif delta_pct >= MATERIAL_MOVE_PCT and delta > 0:
            return (
                f"PickPulse Revenue Digest · {date_str} · "
                f"Forecast up {_fmt(delta)} vs last week — {base_str} expected in 90 days"
            )

    return f"PickPulse Revenue Digest · {date_str} · {base_str} expected ARR in 90 days"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_weekly_digest(
    tenant_id: str,
    send: bool = False,
) -> Dict[str, Any]:
    """Generate the weekly revenue digest for a tenant.

    Args:
        tenant_id: Tenant to generate for.
        send:      If True, attempt email delivery via SMTP (when configured).
                   False (default) returns the digest without sending.
                   This flag makes the function directly callable by a cron
                   trigger without any code changes.

    Returns a dict with: subject, html, text, digest_data, sent_to.
    """
    from app.arr_forecast import compute_arr_forecast
    from app.storage.repo import latest_scores, bulk_latest_signals

    today = date.today()

    # ------------------------------------------------------------------
    # 1. Compute current ARR forecast
    # ------------------------------------------------------------------
    forecast = compute_arr_forecast(tenant_id=tenant_id, horizon_days=90)

    # ------------------------------------------------------------------
    # 2. Load prior snapshot for WoW comparison
    # ------------------------------------------------------------------
    prior = _load_snapshot(tenant_id)

    wow_delta: Optional[float] = None
    wow_delta_pct: Optional[float] = None
    if prior and prior.get("forecast_base"):
        wow_delta = forecast["forecast"]["base"] - prior["forecast_base"]
        wow_delta_pct = (
            (wow_delta / prior["forecast_base"] * 100)
            if prior["forecast_base"] != 0 else None
        )

    # ------------------------------------------------------------------
    # 3. Build top downside list (max 3, by expected_arr_at_risk)
    # ------------------------------------------------------------------
    top_downside = forecast.get("top_at_risk", [])[:MAX_DOWNSIDE_ACCOUNTS]

    # ARR concentration insight
    total_arr_at_risk = forecast["arr_at_risk"]
    arr_concentration: Optional[Dict[str, Any]] = None
    if total_arr_at_risk > 0 and top_downside:
        top3_sum = sum(a["expected_arr_at_risk"] for a in top_downside)
        arr_concentration = {
            "n_accounts": len(top_downside),
            "top3_sum": top3_sum,
            "total_arr_at_risk": total_arr_at_risk,
            "top3_pct": (top3_sum / total_arr_at_risk * 100) if total_arr_at_risk else 0,
        }

    # ------------------------------------------------------------------
    # 4. Compute growth signals (score improved >= 5pp in last 7 days)
    # ------------------------------------------------------------------
    recent_scores = _fetch_recent_scores_by_account(tenant_id, days_back=14)
    score_deltas = _compute_score_deltas(recent_scores, today)

    # Scores lookup for ARR per account
    scored_accounts = {s["account_id"]: s for s in latest_scores(limit=5000, tenant_id=tenant_id)}

    # Identify improving accounts (score went down >= threshold)
    improving = [
        (account_id, delta)
        for account_id, delta in score_deltas.items()
        if delta <= -IMPROVEMENT_THRESHOLD
    ]
    # Sort by ARR × abs(improvement) — prioritize large accounts that improved most
    improving.sort(
        key=lambda x: (abs(x[1]) * float(scored_accounts.get(x[0], {}).get("arr") or 0)),
        reverse=True,
    )
    improving = improving[:MAX_GROWTH_ACCOUNTS]

    # Fetch signal comparisons for improving accounts only (avoid N+1)
    improving_ids = [aid for aid, _ in improving]
    signal_comparisons = _fetch_signals_for_accounts(improving_ids, tenant_id, days_back=14)

    growth_signals = []
    for account_id, delta in improving:
        score_row = scored_accounts.get(account_id, {})
        acct_signals = signal_comparisons.get(account_id, {})
        driver = _determine_health_driver(acct_signals, delta)
        growth_signals.append({
            "account_id": account_id,
            "name": score_row.get("name"),
            "arr": float(score_row.get("arr") or 0),
            "score_delta": delta,
            "driver": driver,
        })

    # ------------------------------------------------------------------
    # 5. Build forecast snapshot block
    # ------------------------------------------------------------------
    forecast_snapshot: Dict[str, Any] = {
        "horizon_date": forecast["horizon_date"],
        "forecast_base": forecast["forecast"]["base"],
        "arr_at_risk": forecast["arr_at_risk"],
        "current_arr": forecast["current_arr"],
        "arr_coverage_pct": forecast["arr_coverage_pct"],
        "accounts_in_forecast": forecast["coverage"]["accounts_in_forecast"],
        "prior_forecast_base": prior["forecast_base"] if prior else None,
        "prior_forecast_date": prior["as_of"] if prior else None,
        "forecast_delta": wow_delta,
        "forecast_delta_pct": wow_delta_pct,
        "lower_1sd": forecast["forecast"]["lower_1sd"],
        "upper_1sd": forecast["forecast"]["upper_1sd"],
    }

    # ------------------------------------------------------------------
    # 6. Generate key insight + WoW drivers
    # ------------------------------------------------------------------
    key_insight = _generate_key_insight(
        forecast_base=forecast["forecast"]["base"],
        arr_at_risk=total_arr_at_risk,
        prior_snapshot=prior,
        n_downside=len(top_downside),
        n_growth=len(growth_signals),
        wow_delta=wow_delta,
        arr_coverage_pct=forecast["arr_coverage_pct"],
    )

    wow_drivers = _generate_wow_drivers(prior, top_downside, wow_delta)

    # ------------------------------------------------------------------
    # 7. Assemble digest_data
    # ------------------------------------------------------------------
    digest_data: Dict[str, Any] = {
        "as_of": today.isoformat(),
        "key_insight": key_insight,
        "top_downside": top_downside,
        "arr_concentration": arr_concentration,
        "wow_drivers": wow_drivers,
        "forecast_snapshot": forecast_snapshot,
        "growth_signals": growth_signals,
        "coverage": forecast["coverage"],
    }

    # ------------------------------------------------------------------
    # 8. Render HTML + text + subject
    # ------------------------------------------------------------------
    html = _build_html(digest_data)
    text = _build_text(digest_data)
    subject = _build_subject(digest_data)

    # ------------------------------------------------------------------
    # 9. Save snapshot for next week's WoW comparison
    # ------------------------------------------------------------------
    _save_snapshot(tenant_id, {
        "as_of": today.isoformat(),
        "forecast_base": forecast["forecast"]["base"],
        "arr_at_risk": total_arr_at_risk,
        "top_downside": [
            {"account_id": a["account_id"], "name": a["name"],
             "expected_arr_at_risk": a["expected_arr_at_risk"]}
            for a in top_downside
        ],
    })

    # ------------------------------------------------------------------
    # 10. Optional send (SMTP placeholder — ready for cron trigger)
    # ------------------------------------------------------------------
    sent_to: List[str] = []
    if send:
        sent_to = _attempt_send(tenant_id, subject, html, text)

    return {
        "subject": subject,
        "html": html,
        "text": text,
        "digest_data": digest_data,
        "sent_to": sent_to,
    }


def _attempt_send(
    tenant_id: str,
    subject: str,
    html: str,
    text: str,
) -> List[str]:
    """Attempt to send via SMTP. Returns list of recipients actually sent to.

    Currently a stub — configure SMTP env vars to enable:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM

    The function signature and return type are intentionally stable so a
    cron trigger (or future webhook) can call generate_weekly_digest(send=True)
    without any changes to the calling code.
    """
    smtp_host = os.environ.get("SMTP_HOST")
    if not smtp_host:
        logger.info("weekly_digest: SMTP_HOST not configured — skipping send")
        return []

    # Import notification settings to get recipients
    try:
        from app.executive_summary import _notification_settings
        recipients = _notification_settings.get(tenant_id, [])
    except Exception:
        recipients = []

    if not recipients:
        logger.info("weekly_digest: no recipients configured for tenant %s", tenant_id)
        return []

    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = os.environ.get("SMTP_FROM", "noreply@pickpulse.co")
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(smtp_host, port) as server:
            server.ehlo()
            server.starttls()
            server.login(
                os.environ.get("SMTP_USER", ""),
                os.environ.get("SMTP_PASS", ""),
            )
            server.sendmail(msg["From"], recipients, msg.as_string())

        logger.info("weekly_digest: sent to %s", recipients)
        return recipients

    except Exception as exc:
        logger.warning("weekly_digest: send failed (%s)", exc)
        return []

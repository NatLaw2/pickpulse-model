#!/usr/bin/env python3
"""Generate all 3 curated demo datasets and print validation stats.

Usage:
    python scripts/generate_demo_datasets.py
"""
from __future__ import annotations

import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine.sample_data import (
    generate_balanced_demo,
    generate_high_risk_demo,
    generate_enterprise_demo,
)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample")

DATASETS = [
    ("balanced_demo.csv", "Balanced Demo", generate_balanced_demo),
    ("high_risk_demo.csv", "High-Risk Demo", generate_high_risk_demo),
    ("enterprise_portfolio_demo.csv", "Enterprise Demo", generate_enterprise_demo),
]

REQUIRED_COLUMNS = [
    "customer_id", "snapshot_date", "churned", "arr", "plan", "seats",
    "monthly_logins", "support_tickets", "nps_score", "days_since_last_login",
    "contract_months_remaining", "industry", "company_size",
    "days_until_renewal", "auto_renew_flag", "renewal_status",
]


def risk_tier(pct: float) -> str:
    if pct >= 70:
        return "High"
    if pct >= 40:
        return "Medium"
    return "Low"


def validate_and_report(name: str, df):
    """Print dataset statistics for demo validation."""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    # Schema check
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"  SCHEMA ERROR — missing columns: {missing}")
        return False
    print(f"  Schema: OK ({len(df.columns)} columns)")

    # Row count
    print(f"  Rows: {len(df):,}")

    # Churn distribution
    churn_counts = df["churned"].value_counts()
    churn_rate = churn_counts.get(1, 0) / len(df) * 100
    print(f"  Churn rate: {churn_rate:.1f}% ({churn_counts.get(1, 0):,} churned / {churn_counts.get(0, 0):,} retained)")

    # ARR stats
    total_arr = df["arr"].sum()
    mean_arr = df["arr"].mean()
    max_arr = df["arr"].max()
    print(f"  Total ARR: ${total_arr:,.0f}")
    print(f"  Mean ARR: ${mean_arr:,.0f}  |  Max ARR: ${max_arr:,.0f}")

    # Simulated risk tiers (using churn probability proxy from features)
    # Since we don't have the model, use the churned label distribution as a proxy
    # and also look at accounts with strong risk signals
    high_risk_signals = df[
        (df["days_since_last_login"] > 30) &
        (df["support_tickets"] >= 4) &
        (df["nps_score"] <= 5)
    ]
    near_renewal = df[df["days_until_renewal"] <= 30]
    urgent = df[
        (df["days_until_renewal"] <= 30) &
        (df["auto_renew_flag"] == 0) &
        (df["nps_score"] <= 5)
    ]

    print(f"  Accounts with strong risk signals: {len(high_risk_signals):,}")
    print(f"  Near-renewal (<=30d): {len(near_renewal):,}")
    print(f"  Urgent (near-renewal + no auto-renew + low NPS): {len(urgent):,}")

    # Hero accounts (non-CUST- names)
    heroes = df[~df["customer_id"].str.startswith("CUST-")]
    if len(heroes) > 0:
        print(f"\n  Hero accounts ({len(heroes)}):")
        for _, h in heroes.sort_values("arr", ascending=False).iterrows():
            print(f"    {h['customer_id']:30s}  ARR ${h['arr']:>9,.0f}  "
                  f"Renewal {h['days_until_renewal']:>3d}d  "
                  f"NPS {h['nps_score']}  "
                  f"Tickets {h['support_tickets']}  "
                  f"Inactive {h['days_since_last_login']}d  "
                  f"Auto-renew {'ON' if h['auto_renew_flag'] else 'OFF'}  "
                  f"Status {h['renewal_status']}")

    # Top 10 by estimated ARR at risk (arr * churn_signal_proxy)
    # Simple proxy: churned accounts' ARR
    churned_df = df[df["churned"] == 1].nlargest(10, "arr")
    if len(churned_df) > 0:
        print(f"\n  Top 10 churned accounts by ARR:")
        for _, row in churned_df.iterrows():
            print(f"    {row['customer_id']:30s}  ARR ${row['arr']:>9,.0f}  "
                  f"Renewal {row['days_until_renewal']:>3d}d  Status {row['renewal_status']}")

    print()
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_ok = True
    for filename, label, gen_fn in DATASETS:
        df = gen_fn()
        path = os.path.join(OUTPUT_DIR, filename)
        df.to_csv(path, index=False)
        print(f"Saved {path} ({len(df):,} rows)")
        ok = validate_and_report(label, df)
        if not ok:
            all_ok = False

    print("\n" + "="*60)
    if all_ok:
        print("All datasets generated and validated successfully.")
    else:
        print("ERRORS found — check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

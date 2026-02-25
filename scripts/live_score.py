#!/usr/bin/env python3
"""Score all integrated accounts using the trained churn model.

Usage:
    python -m scripts.live_score
    # or
    python scripts/live_score.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.integrations.scoring import score_accounts
from app.storage import repo


def main():
    acct_count = repo.account_count()
    if acct_count == 0:
        print("No accounts in database. Run sync_all.py first.")
        return

    print(f"Scoring {acct_count} accounts...")

    try:
        scores = score_accounts()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Train the churn model first via the console or API.")
        return

    if not scores:
        print("No scores generated.")
        return

    # Summary
    high = sum(1 for s in scores if s.tier == "High Risk")
    med = sum(1 for s in scores if s.tier == "Medium Risk")
    low = sum(1 for s in scores if s.tier == "Low Risk")
    total_arr = sum(s.arr_at_risk or 0 for s in scores)

    print(f"\nScored {len(scores)} accounts:")
    print(f"  High Risk:   {high}")
    print(f"  Medium Risk: {med}")
    print(f"  Low Risk:    {low}")
    print(f"  Total ARR at risk: ${total_arr:,.2f}")

    # Show top 5
    top = sorted(scores, key=lambda s: s.churn_probability, reverse=True)[:5]
    print(f"\nTop 5 highest risk:")
    for s in top:
        arr_str = f"${s.arr_at_risk:,.0f}" if s.arr_at_risk else "N/A"
        print(f"  {s.external_id}: {s.churn_probability:.1%} ({s.tier}) — ARR at risk: {arr_str}")


if __name__ == "__main__":
    main()

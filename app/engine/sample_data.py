"""Generate realistic synthetic churn dataset for demos."""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def generate_churn_dataset(n: int = 2000, seed: int = 42) -> pd.DataFrame:
    """Generate a realistic customer churn dataset with renewal fields."""
    rng = np.random.RandomState(seed)
    random.seed(seed)

    plans = ["Enterprise", "Professional", "Starter", "Free Trial"]
    industries = ["SaaS", "E-commerce", "FinTech", "HealthTech", "EdTech",
                  "MarTech", "HR Tech", "Logistics", "Media", "Gaming"]
    sizes = ["1-10", "11-50", "51-200", "201-1000", "1000+"]
    renewal_statuses = ["active", "active", "active", "active",
                        "renewed", "in_notice", "cancelled", "unknown"]

    rows = []
    base_date = datetime(2024, 1, 1)

    for i in range(n):
        customer_id = f"CUST-{20000 + i}"
        plan = random.choice(plans)
        industry = random.choice(industries)
        size = random.choice(sizes)

        # ARR varies by plan
        arr_base = {
            "Enterprise": 120000, "Professional": 36000,
            "Starter": 9600, "Free Trial": 0,
        }[plan]
        arr = max(0, int(rng.normal(arr_base, arr_base * 0.3))) if arr_base > 0 else 0

        seats = max(1, int(rng.exponential({"Enterprise": 50, "Professional": 15,
                                             "Starter": 5, "Free Trial": 2}[plan])))
        monthly_logins = max(0, int(rng.poisson(seats * 8)))
        support_tickets = max(0, int(rng.poisson(2)))
        nps_score = int(np.clip(rng.normal(7, 2), 0, 10))
        days_since_last_login = max(0, int(rng.exponential(15)))
        contract_months = max(0, int(rng.uniform(0, 24)))

        # Renewal fields
        days_until_renewal = max(-30, int(rng.normal(contract_months * 30, 60)))
        auto_renew = int(rng.random() < (0.7 if plan in ["Enterprise", "Professional"] else 0.3))
        renewal_status = random.choice(renewal_statuses)
        # Override renewal_status for consistency
        if days_until_renewal < 0:
            renewal_status = random.choice(["renewed", "cancelled", "active"])
        elif days_until_renewal <= 30:
            renewal_status = random.choice(["active", "in_notice", "active"])

        snapshot_date = base_date + timedelta(days=int(rng.uniform(0, 540)))

        # Churn probability depends on features
        logit = -1.5  # base churn rate ~18%
        logit -= 0.02 * monthly_logins / max(seats, 1)
        logit += 0.15 * support_tickets
        logit -= 0.05 * nps_score
        logit += 0.02 * days_since_last_login
        logit -= 0.08 * contract_months
        logit += {"Free Trial": 1.2, "Starter": 0.3,
                  "Professional": -0.2, "Enterprise": -0.6}[plan]
        # Renewal risk factors
        if days_until_renewal <= 30 and not auto_renew:
            logit += 0.6
        elif days_until_renewal <= 90 and not auto_renew:
            logit += 0.3
        if renewal_status == "in_notice":
            logit += 0.8
        elif renewal_status == "cancelled":
            logit += 2.0
        # Noise
        logit += rng.normal(0, 0.4)

        prob = 1 / (1 + np.exp(-logit))
        churned = int(rng.random() < prob)

        rows.append({
            "customer_id": customer_id,
            "snapshot_date": snapshot_date.strftime("%Y-%m-%d"),
            "churned": churned,
            "arr": arr,
            "plan": plan,
            "seats": seats,
            "monthly_logins": monthly_logins,
            "support_tickets": support_tickets,
            "nps_score": nps_score,
            "days_since_last_login": days_since_last_login,
            "contract_months_remaining": contract_months,
            "industry": industry,
            "company_size": size,
            "days_until_renewal": days_until_renewal,
            "auto_renew_flag": auto_renew,
            "renewal_status": renewal_status,
        })

    df = pd.DataFrame(rows)
    return df


def save_sample_datasets(output_dir: str = "data/sample") -> dict:
    """Generate and save the churn sample dataset."""
    os.makedirs(output_dir, exist_ok=True)

    churn_df = generate_churn_dataset()
    churn_path = os.path.join(output_dir, "churn_customers.csv")
    churn_df.to_csv(churn_path, index=False)

    return {
        "churn": {"path": churn_path, "rows": len(churn_df)},
    }


if __name__ == "__main__":
    result = save_sample_datasets()
    for name, info in result.items():
        print(f"  {name}: {info['rows']} rows -> {info['path']}")

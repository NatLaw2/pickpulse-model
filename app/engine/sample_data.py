"""Generate realistic synthetic churn datasets for demos."""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Original generator (kept for backwards compatibility)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Curated demo dataset generators
# ---------------------------------------------------------------------------

# Curated hero accounts — hand-crafted to surface compelling demo scenarios.
# Each dict is a partial row; the generator fills remaining fields.

_BALANCED_HEROES: List[Dict[str, Any]] = [
    {"customer_id": "Meridian Health Systems", "arr": 185000, "plan": "Enterprise", "seats": 72,
     "monthly_logins": 8, "support_tickets": 7, "nps_score": 3, "days_since_last_login": 38,
     "contract_months_remaining": 1, "days_until_renewal": 18, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "HealthTech", "company_size": "201-1000"},
    {"customer_id": "Apex Financial Group", "arr": 142000, "plan": "Enterprise", "seats": 45,
     "monthly_logins": 3, "support_tickets": 5, "nps_score": 4, "days_since_last_login": 52,
     "contract_months_remaining": 1, "days_until_renewal": 25, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "FinTech", "company_size": "201-1000"},
    {"customer_id": "CloudBridge Analytics", "arr": 168000, "plan": "Enterprise", "seats": 60,
     "monthly_logins": 5, "support_tickets": 9, "nps_score": 2, "days_since_last_login": 65,
     "contract_months_remaining": 0, "days_until_renewal": 8, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "SaaS", "company_size": "51-200"},
    {"customer_id": "NovaTech Solutions", "arr": 95000, "plan": "Enterprise", "seats": 30,
     "monthly_logins": 12, "support_tickets": 4, "nps_score": 5, "days_since_last_login": 21,
     "contract_months_remaining": 2, "days_until_renewal": 42, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "MarTech", "company_size": "51-200"},
    {"customer_id": "Pinnacle Logistics", "arr": 78000, "plan": "Professional", "seats": 18,
     "monthly_logins": 6, "support_tickets": 6, "nps_score": 3, "days_since_last_login": 44,
     "contract_months_remaining": 1, "days_until_renewal": 14, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "Logistics", "company_size": "51-200"},
    {"customer_id": "Evergreen Media Co", "arr": 62000, "plan": "Professional", "seats": 22,
     "monthly_logins": 15, "support_tickets": 3, "nps_score": 6, "days_since_last_login": 12,
     "contract_months_remaining": 3, "days_until_renewal": 65, "auto_renew_flag": 1,
     "renewal_status": "active", "industry": "Media", "company_size": "11-50"},
    {"customer_id": "Brightpath Education", "arr": 54000, "plan": "Professional", "seats": 14,
     "monthly_logins": 4, "support_tickets": 8, "nps_score": 2, "days_since_last_login": 58,
     "contract_months_remaining": 1, "days_until_renewal": 22, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "EdTech", "company_size": "11-50"},
    {"customer_id": "Crestview HR", "arr": 48000, "plan": "Professional", "seats": 10,
     "monthly_logins": 2, "support_tickets": 5, "nps_score": 4, "days_since_last_login": 72,
     "contract_months_remaining": 0, "days_until_renewal": 5, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "HR Tech", "company_size": "11-50"},
]

_HIGH_RISK_HEROES: List[Dict[str, Any]] = [
    {"customer_id": "Titan Insurance Group", "arr": 310000, "plan": "Enterprise", "seats": 120,
     "monthly_logins": 4, "support_tickets": 12, "nps_score": 1, "days_since_last_login": 78,
     "contract_months_remaining": 0, "days_until_renewal": 7, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "FinTech", "company_size": "1000+"},
    {"customer_id": "Meridian Health Systems", "arr": 280000, "plan": "Enterprise", "seats": 95,
     "monthly_logins": 2, "support_tickets": 8, "nps_score": 3, "days_since_last_login": 45,
     "contract_months_remaining": 0, "days_until_renewal": 12, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "HealthTech", "company_size": "1000+"},
    {"customer_id": "Apex Financial Group", "arr": 245000, "plan": "Enterprise", "seats": 80,
     "monthly_logins": 5, "support_tickets": 6, "nps_score": 4, "days_since_last_login": 55,
     "contract_months_remaining": 1, "days_until_renewal": 28, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "FinTech", "company_size": "201-1000"},
    {"customer_id": "CloudBridge Analytics", "arr": 195000, "plan": "Enterprise", "seats": 65,
     "monthly_logins": 3, "support_tickets": 10, "nps_score": 2, "days_since_last_login": 68,
     "contract_months_remaining": 0, "days_until_renewal": 9, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "SaaS", "company_size": "201-1000"},
    {"customer_id": "Vanguard Retail Corp", "arr": 175000, "plan": "Enterprise", "seats": 55,
     "monthly_logins": 7, "support_tickets": 9, "nps_score": 3, "days_since_last_login": 40,
     "contract_months_remaining": 1, "days_until_renewal": 35, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "E-commerce", "company_size": "201-1000"},
    {"customer_id": "Pinnacle Logistics", "arr": 160000, "plan": "Enterprise", "seats": 48,
     "monthly_logins": 6, "support_tickets": 7, "nps_score": 3, "days_since_last_login": 50,
     "contract_months_remaining": 1, "days_until_renewal": 19, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "Logistics", "company_size": "201-1000"},
    {"customer_id": "NovaTech Solutions", "arr": 152000, "plan": "Enterprise", "seats": 42,
     "monthly_logins": 8, "support_tickets": 5, "nps_score": 5, "days_since_last_login": 30,
     "contract_months_remaining": 1, "days_until_renewal": 45, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "MarTech", "company_size": "51-200"},
    {"customer_id": "Brightpath Education", "arr": 88000, "plan": "Enterprise", "seats": 35,
     "monthly_logins": 4, "support_tickets": 11, "nps_score": 2, "days_since_last_login": 62,
     "contract_months_remaining": 0, "days_until_renewal": 15, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "EdTech", "company_size": "51-200"},
    {"customer_id": "Ironclad Security", "arr": 135000, "plan": "Enterprise", "seats": 38,
     "monthly_logins": 10, "support_tickets": 4, "nps_score": 6, "days_since_last_login": 18,
     "contract_months_remaining": 2, "days_until_renewal": 55, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "SaaS", "company_size": "51-200"},
    {"customer_id": "Crestview HR", "arr": 72000, "plan": "Professional", "seats": 16,
     "monthly_logins": 2, "support_tickets": 8, "nps_score": 2, "days_since_last_login": 80,
     "contract_months_remaining": 0, "days_until_renewal": 6, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "HR Tech", "company_size": "11-50"},
    {"customer_id": "Evergreen Media Co", "arr": 68000, "plan": "Professional", "seats": 20,
     "monthly_logins": 9, "support_tickets": 3, "nps_score": 5, "days_since_last_login": 25,
     "contract_months_remaining": 2, "days_until_renewal": 40, "auto_renew_flag": 1,
     "renewal_status": "active", "industry": "Media", "company_size": "11-50"},
    {"customer_id": "Summit Gaming", "arr": 58000, "plan": "Professional", "seats": 12,
     "monthly_logins": 3, "support_tickets": 6, "nps_score": 3, "days_since_last_login": 48,
     "contract_months_remaining": 1, "days_until_renewal": 20, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "Gaming", "company_size": "11-50"},
]

_ENTERPRISE_HEROES: List[Dict[str, Any]] = [
    {"customer_id": "GlobalBank Holdings", "arr": 420000, "plan": "Enterprise", "seats": 200,
     "monthly_logins": 15, "support_tickets": 14, "nps_score": 2, "days_since_last_login": 35,
     "contract_months_remaining": 1, "days_until_renewal": 22, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "FinTech", "company_size": "1000+"},
    {"customer_id": "Titan Insurance Group", "arr": 380000, "plan": "Enterprise", "seats": 180,
     "monthly_logins": 8, "support_tickets": 11, "nps_score": 3, "days_since_last_login": 60,
     "contract_months_remaining": 0, "days_until_renewal": 10, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "FinTech", "company_size": "1000+"},
    {"customer_id": "Pacific Healthcare Corp", "arr": 340000, "plan": "Enterprise", "seats": 150,
     "monthly_logins": 12, "support_tickets": 9, "nps_score": 4, "days_since_last_login": 42,
     "contract_months_remaining": 1, "days_until_renewal": 30, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "HealthTech", "company_size": "1000+"},
    {"customer_id": "Meridian Health Systems", "arr": 295000, "plan": "Enterprise", "seats": 110,
     "monthly_logins": 6, "support_tickets": 7, "nps_score": 3, "days_since_last_login": 50,
     "contract_months_remaining": 1, "days_until_renewal": 18, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "HealthTech", "company_size": "1000+"},
    {"customer_id": "Apex Financial Group", "arr": 260000, "plan": "Enterprise", "seats": 90,
     "monthly_logins": 4, "support_tickets": 8, "nps_score": 3, "days_since_last_login": 55,
     "contract_months_remaining": 1, "days_until_renewal": 25, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "FinTech", "company_size": "201-1000"},
    {"customer_id": "CloudBridge Analytics", "arr": 210000, "plan": "Enterprise", "seats": 75,
     "monthly_logins": 5, "support_tickets": 10, "nps_score": 2, "days_since_last_login": 70,
     "contract_months_remaining": 0, "days_until_renewal": 8, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "SaaS", "company_size": "201-1000"},
    {"customer_id": "Vanguard Retail Corp", "arr": 190000, "plan": "Enterprise", "seats": 65,
     "monthly_logins": 9, "support_tickets": 6, "nps_score": 4, "days_since_last_login": 28,
     "contract_months_remaining": 2, "days_until_renewal": 38, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "E-commerce", "company_size": "201-1000"},
    {"customer_id": "Pinnacle Logistics", "arr": 175000, "plan": "Enterprise", "seats": 55,
     "monthly_logins": 7, "support_tickets": 7, "nps_score": 3, "days_since_last_login": 48,
     "contract_months_remaining": 1, "days_until_renewal": 15, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "Logistics", "company_size": "201-1000"},
    {"customer_id": "Brightpath Education", "arr": 155000, "plan": "Enterprise", "seats": 50,
     "monthly_logins": 3, "support_tickets": 9, "nps_score": 2, "days_since_last_login": 65,
     "contract_months_remaining": 0, "days_until_renewal": 12, "auto_renew_flag": 0,
     "renewal_status": "in_notice", "industry": "EdTech", "company_size": "201-1000"},
    {"customer_id": "NovaTech Solutions", "arr": 145000, "plan": "Enterprise", "seats": 40,
     "monthly_logins": 11, "support_tickets": 4, "nps_score": 5, "days_since_last_login": 15,
     "contract_months_remaining": 2, "days_until_renewal": 50, "auto_renew_flag": 0,
     "renewal_status": "active", "industry": "MarTech", "company_size": "51-200"},
]


def _generate_demo_accounts(
    n: int,
    seed: int,
    heroes: List[Dict[str, Any]],
    plan_weights: Optional[List[float]] = None,
    arr_multiplier: float = 1.0,
    base_churn_logit: float = -1.5,
    renewal_urgency_fraction: float = 0.15,
) -> pd.DataFrame:
    """Core generator for curated demo datasets.

    Parameters
    ----------
    n : int
        Total number of *generated* accounts (heroes are added on top).
    seed : int
        Random seed for reproducibility.
    heroes : list[dict]
        Hand-crafted accounts injected into the dataset.
    plan_weights : list[float] | None
        Probability weights for [Enterprise, Professional, Starter, Free Trial].
    arr_multiplier : float
        Multiplier applied to base ARR values (>1 for enterprise scale).
    base_churn_logit : float
        Base logit for churn probability (more negative = lower base rate).
    renewal_urgency_fraction : float
        Fraction of generated accounts forced into near-term renewal (<=45 days).
    """
    rng = np.random.RandomState(seed)
    random.seed(seed)

    plans = ["Enterprise", "Professional", "Starter", "Free Trial"]
    pw = plan_weights or [0.25, 0.25, 0.25, 0.25]
    industries = [
        "SaaS", "E-commerce", "FinTech", "HealthTech", "EdTech",
        "MarTech", "HR Tech", "Logistics", "Media", "Gaming",
    ]
    sizes = ["1-10", "11-50", "51-200", "201-1000", "1000+"]

    arr_base_map = {
        "Enterprise": int(120000 * arr_multiplier),
        "Professional": int(36000 * arr_multiplier),
        "Starter": int(9600 * arr_multiplier),
        "Free Trial": 0,
    }

    base_date = datetime(2024, 1, 1)
    rows: List[Dict[str, Any]] = []

    for i in range(n):
        customer_id = f"CUST-{30000 + i}"
        plan = rng.choice(plans, p=pw)
        industry = random.choice(industries)
        size = random.choice(sizes)

        arr_base = arr_base_map[plan]
        arr = max(0, int(rng.normal(arr_base, arr_base * 0.3))) if arr_base > 0 else 0

        # Latent "account health" factor — drives correlated signals
        health = rng.normal(0, 1)  # positive = healthy, negative = distressed

        seats = max(1, int(rng.exponential(
            {"Enterprise": 50, "Professional": 15, "Starter": 5, "Free Trial": 2}[plan]
        )))
        # Logins influenced by health
        login_rate = max(1, seats * 8 + health * seats * 2)
        monthly_logins = max(0, int(rng.poisson(login_rate)))

        # Support tickets inversely correlated with health
        ticket_rate = max(0.5, 2.0 - health * 0.8)
        support_tickets = max(0, int(rng.poisson(ticket_rate)))

        # NPS correlated with health
        nps_score = int(np.clip(rng.normal(7 + health * 1.2, 1.5), 0, 10))

        # Days since last login — unhealthy accounts more inactive
        inactivity_base = max(3, 15 - health * 8)
        days_since_last_login = max(0, int(rng.exponential(inactivity_base)))

        contract_months = max(0, int(rng.uniform(0, 24)))

        # Renewal fields — some accounts forced into urgency
        if rng.random() < renewal_urgency_fraction:
            days_until_renewal = max(1, int(rng.uniform(3, 45)))
        else:
            days_until_renewal = max(-30, int(rng.normal(contract_months * 30, 60)))

        auto_renew = int(rng.random() < (0.7 if plan in ["Enterprise", "Professional"] else 0.3))

        # Renewal status with consistency
        if days_until_renewal < 0:
            renewal_status = random.choice(["renewed", "cancelled", "active"])
        elif days_until_renewal <= 30 and health < -0.5:
            renewal_status = random.choice(["in_notice", "in_notice", "active"])
        elif days_until_renewal <= 30:
            renewal_status = random.choice(["active", "in_notice", "active"])
        else:
            rs_pool = ["active"] * 5 + ["renewed", "unknown"]
            renewal_status = random.choice(rs_pool)

        snapshot_date = base_date + timedelta(days=int(rng.uniform(0, 540)))

        # Churn probability
        logit = base_churn_logit
        logit -= 0.02 * monthly_logins / max(seats, 1)
        logit += 0.15 * support_tickets
        logit -= 0.05 * nps_score
        logit += 0.02 * days_since_last_login
        logit -= 0.08 * contract_months
        logit += {"Free Trial": 1.2, "Starter": 0.3,
                  "Professional": -0.2, "Enterprise": -0.6}[plan]
        if days_until_renewal <= 30 and not auto_renew:
            logit += 0.6
        elif days_until_renewal <= 90 and not auto_renew:
            logit += 0.3
        if renewal_status == "in_notice":
            logit += 0.8
        elif renewal_status == "cancelled":
            logit += 2.0
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

    # Inject hero accounts — churned=0 so they remain "active" in the predict
    # pipeline (churned=1 gets archived).  Their degraded signals ensure the
    # model still scores them as high-risk after training on the bulk data.
    recent_date = base_date + timedelta(days=500)
    for hero in heroes:
        # Ensure renewal_status is not "cancelled" (also causes archiving)
        hero_renewal = hero.get("renewal_status", "in_notice")
        if hero_renewal == "cancelled":
            hero_renewal = "in_notice"

        row = {
            "customer_id": hero["customer_id"],
            "snapshot_date": recent_date.strftime("%Y-%m-%d"),
            "churned": 0,
            "arr": hero["arr"],
            "plan": hero.get("plan", "Enterprise"),
            "seats": hero.get("seats", 40),
            "monthly_logins": hero.get("monthly_logins", 5),
            "support_tickets": hero.get("support_tickets", 6),
            "nps_score": hero.get("nps_score", 3),
            "days_since_last_login": hero.get("days_since_last_login", 45),
            "contract_months_remaining": hero.get("contract_months_remaining", 1),
            "industry": hero.get("industry", "SaaS"),
            "company_size": hero.get("company_size", "201-1000"),
            "days_until_renewal": hero.get("days_until_renewal", 20),
            "auto_renew_flag": hero.get("auto_renew_flag", 0),
            "renewal_status": hero_renewal,
        }
        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Public demo dataset generators
# ---------------------------------------------------------------------------

def generate_balanced_demo(seed: int = 100) -> pd.DataFrame:
    """Balanced demo: ~2,000 accounts, 65-75% low / 15-25% med / 8-12% high risk.

    Good default for general SaaS product demos.
    """
    return _generate_demo_accounts(
        n=1990,
        seed=seed,
        heroes=_BALANCED_HEROES,
        plan_weights=[0.20, 0.30, 0.30, 0.20],
        arr_multiplier=1.0,
        base_churn_logit=-1.5,
        renewal_urgency_fraction=0.12,
    )


def generate_high_risk_demo(seed: int = 200) -> pd.DataFrame:
    """High-risk demo: ~1,000 accounts, 55-65% low / 20-25% med / 15-20% high risk.

    Designed for strong "urgent action required" demo narrative.
    """
    return _generate_demo_accounts(
        n=990,
        seed=seed,
        heroes=_HIGH_RISK_HEROES,
        plan_weights=[0.30, 0.30, 0.25, 0.15],
        arr_multiplier=1.2,
        base_churn_logit=-1.0,
        renewal_urgency_fraction=0.25,
    )


def generate_enterprise_demo(seed: int = 300) -> pd.DataFrame:
    """Enterprise demo: ~4,000 accounts, higher ARR footprint.

    Boardroom-ready dataset with large total ARR-at-risk numbers.
    """
    return _generate_demo_accounts(
        n=3990,
        seed=seed,
        heroes=_ENTERPRISE_HEROES,
        plan_weights=[0.30, 0.35, 0.25, 0.10],
        arr_multiplier=1.5,
        base_churn_logit=-1.3,
        renewal_urgency_fraction=0.18,
    )


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def save_sample_datasets(output_dir: str = "data/sample") -> dict:
    """Generate and save the churn sample dataset."""
    os.makedirs(output_dir, exist_ok=True)

    churn_df = generate_churn_dataset()
    churn_path = os.path.join(output_dir, "churn_customers.csv")
    churn_df.to_csv(churn_path, index=False)

    return {
        "churn": {"path": churn_path, "rows": len(churn_df)},
    }


DEMO_GENERATORS = {
    "balanced": generate_balanced_demo,
    "high_risk": generate_high_risk_demo,
    "enterprise": generate_enterprise_demo,
}


if __name__ == "__main__":
    result = save_sample_datasets()
    for name, info in result.items():
        print(f"  {name}: {info['rows']} rows -> {info['path']}")

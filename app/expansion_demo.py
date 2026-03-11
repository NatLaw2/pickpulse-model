"""
Expansion Demo — Sandbox prototype endpoint.

Returns two fully synthetic payloads in a single response:
  - arr_risk:   a sandboxed clone of the churn Overview data structure
  - expansion:  a new expansion opportunities dataset

No production churn state, datasets, predictions, or tenant data are accessed.
This module is entirely self-contained and safe to include alongside the
production churn module without any risk of interference.
"""
from __future__ import annotations

import random
from typing import Any

from fastapi import APIRouter, Depends
from .auth import get_tenant_id

router = APIRouter(prefix="/api/expansion-demo", tags=["expansion-demo"])

# ---------------------------------------------------------------------------
# Seeded RNGs — deterministic, stable across requests.
# Two separate seeds so arr_risk and expansion datasets are independent.
# ---------------------------------------------------------------------------
_SEED_ARR_RISK = 42
_SEED_EXPANSION = 99

# ---------------------------------------------------------------------------
# Company name pool (150 names — enough for both datasets with no repeats
# in the top-10 tables that matter most visually)
# ---------------------------------------------------------------------------
_ACCOUNT_NAMES = [
    "Titan Insurance Group", "Apex Financial Group", "Meridian Health Systems",
    "CloudBridge Analytics", "NovaTech Solutions", "Vanguard Retail Corp",
    "Ironclad Security", "Pinnacle Logistics", "Summit Data Co", "Helix Biotech",
    "Orion Payments", "Atlas Workforce", "Cascade Consulting", "Nexus Media Group",
    "Horizon Energy", "Zenith Software", "Cobalt Ventures", "Echo Analytics",
    "Prism Health", "Sterling Capital", "Lunar Retail", "Vertex Systems",
    "Pacific Data Labs", "Ember Technologies", "Granite Financial",
    "Topaz Solutions", "Solaris Networks", "Argon Digital", "Birch Consulting",
    "Cedar Analytics", "Drake Financial", "Edison Systems", "Fable Media",
    "Griffin Capital", "Harbor Tech", "Indigo Analytics", "Jade Ventures",
    "Kestrel Data", "Lumen Health", "Maple Systems", "Nova Capital",
    "Opal Networks", "Pearl Analytics", "Quartz Solutions", "Raven Digital",
    "Sapphire Tech", "Tundra Systems", "Unity Capital", "Vale Analytics",
    "Willow Health", "Xenon Data", "Yew Consulting", "Zephyr Networks",
    "Amber Financial", "Basalt Solutions", "Chrome Analytics", "Drift Capital",
    "Epoch Systems", "Flint Digital", "Gale Networks", "Halo Analytics",
    "Ion Capital", "Jasper Health", "Kelp Technologies", "Lime Consulting",
    "Mast Analytics", "Node Capital", "Obsidian Data", "Pulse Networks",
    "Quill Systems", "Ridge Analytics", "Slate Capital", "Terra Health",
    "Umber Digital", "Vault Systems", "Wave Analytics", "Xenith Capital",
    "Yarn Technologies", "Zero Digital", "Alloy Solutions", "Beacon Analytics",
    "Crest Capital", "Delta Systems", "Ember Health", "Forge Networks",
    "Glacier Data", "Haven Analytics", "Inlet Capital", "Jetstream Systems",
    "Knoll Digital", "Ledge Analytics", "Mesa Capital", "Neon Health",
    "Oak Systems", "Peak Analytics", "Quest Capital", "Rock Digital",
    "Sand Analytics", "Tide Systems", "Ultra Capital", "Veil Analytics",
    "Wind Health", "Xray Systems", "Yarrow Capital", "Zinc Analytics",
    "Aether Solutions", "Blaze Networks", "Copper Data", "Dawn Systems",
    "Echo Capital", "Frost Analytics", "Glen Health", "Hive Technologies",
    "Isle Digital", "Juniper Capital", "Kite Analytics", "Lark Systems",
    "Mint Capital", "Nora Digital", "Onyx Analytics", "Pike Networks",
    "Reed Capital", "Shore Systems", "Teal Analytics", "Urn Digital",
    "Volt Capital", "Wren Analytics", "Axle Systems", "Bay Capital",
    "Cove Analytics", "Dune Technologies", "Edge Capital", "Fen Analytics",
    "Grove Systems", "Hull Capital", "Iris Analytics", "Jet Systems",
    "Keel Capital", "Lens Analytics", "Moor Systems", "Null Capital",
    "Ore Analytics", "Port Systems", "Rail Capital", "Reef Analytics",
    "Spar Systems", "Trim Capital", "Urge Analytics", "Vale Systems",
    "Wake Capital", "Yarn Analytics",
]

_EXPANSION_SIGNALS = [
    "Seat usage increasing",
    "Feature adoption spike",
    "Increased weekly logins",
    "API usage increase",
    "Additional users added",
]

_RISK_DRIVERS = [
    "days_until_renewal",
    "monthly_logins",
    "nps_score",
    "support_tickets",
    "days_since_last_login",
    "contract_months_remaining",
]


# ---------------------------------------------------------------------------
# ARR Risk sandbox data builders
# ---------------------------------------------------------------------------

def _arr_risk_account(rng: random.Random, idx: int) -> dict[str, Any]:
    arr = rng.randint(50, 500) * 1_000
    churn_risk_pct = round(rng.uniform(5.0, 85.0), 1)
    arr_at_risk = round(arr * churn_risk_pct / 100, 2)
    days = rng.randint(1, 450)
    renewal_label = "<30d" if days < 30 else ("30-90d" if days <= 90 else ">90d")
    if churn_risk_pct >= 70:
        tier = "High Risk"
    elif churn_risk_pct >= 40:
        tier = "Medium Risk"
    else:
        tier = "Low Risk"
    return {
        "customer_id": f"ACCT-{1000 + idx}",
        "account_name": _ACCOUNT_NAMES[idx % len(_ACCOUNT_NAMES)],
        "arr": arr,
        "churn_risk_pct": churn_risk_pct,
        "arr_at_risk": arr_at_risk,
        "days_until_renewal": days,
        "renewal_window_label": renewal_label,
        "tier": tier,
    }


def _build_arr_risk_payload(rng: random.Random) -> dict[str, Any]:
    accounts = [_arr_risk_account(rng, i) for i in range(120)]

    total_arr_at_risk = sum(a["arr_at_risk"] for a in accounts)
    save_rate = 0.35
    renewing_90d = sum(
        1 for a in accounts if a["renewal_window_label"] in ("<30d", "30-90d")
    )
    high_risk_in_window = sum(
        1 for a in accounts
        if a["churn_risk_pct"] >= 70 and a["renewal_window_label"] in ("<30d", "30-90d")
    )
    high_saves   = sum(a["arr_at_risk"] for a in accounts if a["churn_risk_pct"] >= 70)
    medium_saves = sum(a["arr_at_risk"] for a in accounts if 40 <= a["churn_risk_pct"] < 70)
    low_saves    = sum(a["arr_at_risk"] for a in accounts if a["churn_risk_pct"] < 40)

    tier_counts: dict[str, int] = {}
    for a in accounts:
        tier_counts[a["tier"]] = tier_counts.get(a["tier"], 0) + 1

    top_10 = sorted(accounts, key=lambda x: x["arr_at_risk"], reverse=True)[:10]

    top_risk_drivers = [
        {"feature": f, "importance": round(rng.uniform(0.01, 0.07), 3)}
        for f in _RISK_DRIVERS
    ]
    top_risk_drivers.sort(key=lambda x: x["importance"], reverse=True)

    return {
        "kpis": {
            "total_arr_at_risk": round(total_arr_at_risk, 2),
            "projected_recoverable_arr": round(total_arr_at_risk * save_rate, 2),
            "assumed_save_rate": save_rate,
            "renewing_90d": renewing_90d,
            "high_risk_in_window": high_risk_in_window,
        },
        "recovery_buckets": {
            "high_confidence_saves": round(high_saves, 2),
            "medium_confidence_saves": round(medium_saves, 2),
            "low_confidence_saves": round(low_saves, 2),
        },
        "top_at_risk": top_10,
        "tier_counts": tier_counts,
        "top_risk_drivers": top_risk_drivers,
    }


# ---------------------------------------------------------------------------
# Expansion opportunity data builders
# ---------------------------------------------------------------------------

def _expansion_account(rng: random.Random, idx: int) -> dict[str, Any]:
    current_arr = rng.randint(50, 400) * 1_000
    expansion_probability = round(rng.uniform(0.05, 0.95), 2)
    potential_expansion_arr = rng.randint(5, 150) * 1_000
    signal = rng.choice(_EXPANSION_SIGNALS)
    active_users_change = round(rng.uniform(-5.0, 40.0), 1)
    feature_adoption_change = round(rng.uniform(-2.0, 35.0), 1)
    # churn_risk is needed for the Opportunity Matrix scatter plot
    churn_risk = round(rng.uniform(0.05, 0.65), 2)
    if expansion_probability >= 0.70:
        tier = "High"
    elif expansion_probability >= 0.40:
        tier = "Medium"
    else:
        tier = "Low"
    return {
        "account_name": _ACCOUNT_NAMES[idx % len(_ACCOUNT_NAMES)],
        "current_arr": current_arr,
        "expansion_probability": expansion_probability,
        "potential_expansion_arr": potential_expansion_arr,
        "expansion_signal": signal,
        "active_users_change": active_users_change,
        "feature_adoption_change": feature_adoption_change,
        "churn_risk": churn_risk,
        "tier": tier,
    }


def _build_expansion_payload(rng: random.Random) -> dict[str, Any]:
    accounts = [_expansion_account(rng, i) for i in range(300)]

    total_expansion_potential = sum(a["potential_expansion_arr"] for a in accounts)
    high_expansion_accounts   = sum(1 for a in accounts if a["expansion_probability"] >= 0.70)
    avg_expansion_probability = round(
        sum(a["expansion_probability"] for a in accounts) / len(accounts), 2
    )
    # "Expansion likely within 90 days" proxy: expansion_probability >= 0.60
    expansion_likely_90d = sum(1 for a in accounts if a["expansion_probability"] >= 0.60)

    tier_arr: dict[str, float] = {}
    tier_counts: dict[str, int] = {}
    for a in accounts:
        tier_arr[a["tier"]]    = tier_arr.get(a["tier"], 0.0) + a["potential_expansion_arr"]
        tier_counts[a["tier"]] = tier_counts.get(a["tier"], 0) + 1

    top_10 = sorted(accounts, key=lambda x: x["potential_expansion_arr"], reverse=True)[:10]

    # Sample 150 accounts for the scatter plot to avoid overplotting
    matrix_sample = rng.sample(accounts, min(150, len(accounts)))
    matrix_points = [
        {
            "account_name":          a["account_name"],
            "expansion_probability": a["expansion_probability"],
            "churn_risk":            a["churn_risk"],
            "potential_expansion_arr": a["potential_expansion_arr"],
            "tier":                  a["tier"],
        }
        for a in matrix_sample
    ]

    return {
        "kpis": {
            "total_expansion_potential": round(total_expansion_potential, 2),
            "high_expansion_accounts":   high_expansion_accounts,
            "avg_expansion_probability": avg_expansion_probability,
            "expansion_likely_90d":      expansion_likely_90d,
        },
        "tier_arr":          {k: round(v, 2) for k, v in tier_arr.items()},
        "tier_counts":       tier_counts,
        "top_opportunities": top_10,
        "matrix_points":     matrix_points,
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/data")
def expansion_demo_data(tenant_id: str = Depends(get_tenant_id)):
    """
    Return both sandbox payloads in a single response.
    No production churn state is accessed — all data is synthetically generated.
    The tenant_id dependency enforces authentication only; it is not used in the response.
    """
    return {
        "arr_risk":  _build_arr_risk_payload(random.Random(_SEED_ARR_RISK)),
        "expansion": _build_expansion_payload(random.Random(_SEED_EXPANSION)),
    }

"""Salesforce demo dataset generator for PickPulse.

Generates 2 000 synthetic B2B accounts with realistic churn risk distributions,
two signal snapshots per account (historical + current), and outcome labels for
churned accounts.  All randomness is fully deterministic via seed=42002.

Signal distributions are identical to the HubSpot generator (same tier
parameters) — only identity fields, plan names, ARR buckets, and metadata
schema differ to reflect Salesforce CRM conventions.

Usage:
    from app.demo.salesforce import SalesforceDemoDataset
    data = SalesforceDemoDataset().generate()
    # data.keys() -> {'accounts', 'signals', 'outcomes'}
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SALESFORCE_SEED = 42002
N_ACCOUNTS = 2000

# Reference date – "today" for the generator.
_TODAY = date(2026, 4, 15)

# ---------------------------------------------------------------------------
# Word lists (48 × 42 = 2 016 unique pairs; we take the first 2 000)
# ---------------------------------------------------------------------------

_PREFIX_WORDS = [
    "Apex", "Atlas", "Beacon", "Bright", "Cedar", "Cipher", "Clarity", "Cloud",
    "Coral", "Core", "Delta", "Digital", "Edge", "Elevate", "Ember", "Era",
    "Evolve", "Facet", "Fusion", "Gather", "Global", "Harbor", "Impact", "Insight",
    "Iris", "Kite", "Layer", "Leap", "Lumen", "Margin", "Meridian", "Mesa",
    "Nexus", "Nova", "Onyx", "Orbit", "Pact", "Peak", "Pilot", "Prime",
    "Prism", "Quantum", "Rapid", "Relay", "Sage", "Signal", "Smart", "Spark",
]

_CORE_WORDS = [
    "Analytics", "Arc", "Bridge", "Capital", "Cloud", "Connect", "Craft", "Data",
    "Dynamics", "Edge", "Engine", "Exchange", "Finance", "Flow", "Force", "Gate",
    "Grid", "Group", "Health", "Hub", "Insights", "Intel", "Labs", "Link",
    "Logic", "Media", "Mesh", "Mind", "Motion", "Networks", "Node", "Ops",
    "Platform", "Point", "Pulse", "Scale", "Scout", "Solutions", "Systems", "Tech",
    "Wave", "Works",
]

_SUFFIXES  = ["Corp.", "Ltd.", "Industries"]   # cycle by rank
_DOMAIN_TLDS = [".com", ".net"]                # cycle by rank

# Salesforce TitleCase industries
_INDUSTRIES = [
    "Technology",
    "Financial Services",
    "Healthcare",
    "Manufacturing",
    "Retail",
    "Professional Services",
]

# Salesforce numeric-style company sizes
_COMPANY_SIZES = ["1-50", "51-200", "201-500", "501-2000", "2001+"]

# Cycling pool of Salesforce owner names (~20 plausible reps)
_SF_OWNER_NAMES = [
    "Sarah Chen",       "Marcus Johnson",   "Priya Patel",      "James O'Brien",
    "Aisha Williams",   "Daniel Kim",       "Laura Martinez",   "Kevin Okafor",
    "Rachel Thompson",  "David Singh",      "Emily Nakamura",   "Carlos Rivera",
    "Fatima Al-Hassan", "Tyler Brooks",     "Mei Lin",          "Jordan Evans",
    "Nadia Petrov",     "Samuel Adeyemi",   "Claire Dubois",    "Raj Mehta",
]

# ---------------------------------------------------------------------------
# Tier definitions (identical structure to HubSpot generator)
# ---------------------------------------------------------------------------

_TIERS = [
    ("HIGH",     300, 1.00),
    ("MED_HIGH", 300, 0.60),
    ("MED",      400, 0.25),
    ("LOW",     1000, 0.03),
]

# Signal distribution parameters — same as HubSpot (same training signal set)
_SIG_PARAMS: dict[str, dict[str, tuple[float, float, float, float]]] = {
    "HIGH": {
        "days_since_last_login": (68.0,  18.0,  35.0, 120.0),
        "monthly_logins":        ( 1.0,   0.8,   0.0,   3.0),
        "nps_score":             ( 2.8,   1.0,   1.0,   5.0),
        "support_tickets":       ( 5.5,   1.5,   2.0,   9.0),
        "days_until_renewal":    (20.0,  10.0,   5.0,  45.0),
        "seats":                 ( 4.0,   2.0,   1.0,  10.0),
    },
    "MED_HIGH": {
        "days_since_last_login": (42.0,  12.0,  18.0,  70.0),
        "monthly_logins":        ( 3.0,   1.5,   0.0,   7.0),
        "nps_score":             ( 5.0,   1.0,   3.0,   7.0),
        "support_tickets":       ( 3.2,   1.0,   1.0,   6.0),
        "days_until_renewal":    (55.0,  20.0,  15.0, 100.0),
        "seats":                 ( 6.0,   3.0,   2.0,  15.0),
    },
    "MED": {
        "days_since_last_login": (22.0,  10.0,   6.0,  45.0),
        "monthly_logins":        ( 7.0,   2.5,   2.0,  14.0),
        "nps_score":             ( 6.8,   0.8,   5.0,   8.5),
        "support_tickets":       ( 1.5,   0.8,   0.0,   3.0),
        "days_until_renewal":    (130.0, 50.0,  45.0, 250.0),
        "seats":                 ( 9.0,   4.0,   3.0,  22.0),
    },
    "LOW": {
        "days_since_last_login": ( 4.0,   3.0,   0.0,  14.0),
        "monthly_logins":        (17.0,   5.0,   8.0,  35.0),
        "nps_score":             ( 8.8,   0.6,   7.5,  10.0),
        "support_tickets":       ( 0.3,   0.5,   0.0,   2.0),
        "days_until_renewal":    (220.0, 75.0,  90.0, 400.0),
        "seats":                 (14.0,   5.0,   4.0,  45.0),
    },
}

_AUTO_RENEW_PROB: dict[str, float] = {
    "HIGH":     0.08,
    "MED_HIGH": 0.35,
    "MED":      0.72,
    "LOW":      0.95,
}

# Salesforce plan names and their ARR distributions
# Plans: Basic(30%) / Standard(40%) / Premium(20%) / Enterprise(10%)
_PLANS = ["Basic", "Standard", "Premium", "Enterprise"]

# ARR log-normal params: (mu, sigma, lo, hi)
_PLAN_ARR: dict[str, tuple[float, float, float, float]] = {
    "Basic":      (math.log(20_000),  0.45,   7_000,  55_000),
    "Standard":   (math.log(60_000),  0.40,  25_000, 150_000),
    "Premium":    (math.log(130_000), 0.38,  60_000, 280_000),
    "Enterprise": (math.log(280_000), 0.35, 150_000, 600_000),
}

# Plan mix weights by risk pole (4-element: Basic/Standard/Premium/Enterprise)
_PLAN_WEIGHTS_HIGH = [0.40, 0.35, 0.20, 0.05]
_PLAN_WEIGHTS_LOW  = [0.15, 0.35, 0.30, 0.20]


def _is_high_risk(tier: str) -> bool:
    return tier in ("HIGH", "MED_HIGH")


def _lerp_weights(tier: str) -> list[float]:
    """Interpolate plan weights between high-risk and low-risk poles."""
    frac = {"HIGH": 0.0, "MED_HIGH": 0.25, "MED": 0.65, "LOW": 1.0}[tier]
    hi = _PLAN_WEIGHTS_HIGH
    lo = _PLAN_WEIGHTS_LOW
    return [hi[i] * (1 - frac) + lo[i] * frac for i in range(4)]


# ---------------------------------------------------------------------------
# Salesforce external_id: 15-char SF-style object ID
# ---------------------------------------------------------------------------

def _sf_external_id(rank: int) -> str:
    """Generate a Salesforce-style 15-char account ID deterministically."""
    digest = hashlib.md5(f"sf{rank}".encode()).hexdigest()[:12].upper()
    return f"001{digest}"  # "001" prefix (3 chars) + 12 hex chars = 15 chars


# ---------------------------------------------------------------------------
# Helper: domain slug from company name
# ---------------------------------------------------------------------------

def _name_to_slug(name: str) -> str:
    """Strip legal suffixes and punctuation; lowercase; collapse spaces."""
    slug = re.sub(r"\b(Inc|LLC|Co|Corp|Ltd|Industries)\b\.?", "", name, flags=re.I)
    slug = re.sub(r"[^a-zA-Z0-9 ]", "", slug).strip().lower()
    slug = re.sub(r"\s+", "", slug)
    return slug


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class SalesforceDemoDataset:
    """Deterministic synthetic Salesforce-flavoured dataset for PickPulse demos."""

    def generate(self, n: int = N_ACCOUNTS) -> dict:
        """Return ``{'accounts': [...], 'signals': [...], 'outcomes': [...]}``.

        Parameters
        ----------
        n:
            Number of accounts to generate (default 2 000).  Must be ≤ 2 016
            (the number of unique prefix×core pairs).
        """
        if n > len(_PREFIX_WORDS) * len(_CORE_WORDS):
            raise ValueError(f"n={n} exceeds maximum unique name pairs ({len(_PREFIX_WORDS) * len(_CORE_WORDS)})")

        rng = np.random.default_rng(SALESFORCE_SEED)

        # ------------------------------------------------------------------
        # 1. Build tier membership list (deterministic order)
        # ------------------------------------------------------------------
        tier_labels: list[str] = []
        for label, count, _ in _TIERS:
            tier_labels.extend([label] * count)
        tier_labels = tier_labels[:n]

        accounts: list[dict] = []
        signals: list[dict] = []
        outcomes: list[dict] = []

        # Precompute all name pairs in order (48 × 42, first n)
        name_pairs = [
            (_PREFIX_WORDS[i // len(_CORE_WORDS)], _CORE_WORDS[i % len(_CORE_WORDS)])
            for i in range(n)
        ]

        for rank in range(n):
            tier = tier_labels[rank]
            churn_rate = {label: cr for label, _, cr in _TIERS}[tier]
            prefix, core = name_pairs[rank]

            # ---- Identity ------------------------------------------------
            suffix = _SUFFIXES[rank % len(_SUFFIXES)]
            tld    = _DOMAIN_TLDS[rank % len(_DOMAIN_TLDS)]
            name   = f"{prefix} {core} {suffix}"
            slug   = _name_to_slug(name)
            domain = f"{slug}{tld}"
            external_id = _sf_external_id(rank)

            # ---- Plan & ARR ----------------------------------------------
            plan_weights = _lerp_weights(tier)
            plan = str(rng.choice(_PLANS, p=plan_weights))
            arr_mu, arr_sigma, arr_lo, arr_hi = _PLAN_ARR[plan]
            arr_raw = float(np.exp(rng.normal(arr_mu, arr_sigma)))
            arr = float(np.clip(arr_raw, arr_lo, arr_hi))
            arr = round(arr / 100) * 100  # round to nearest $100

            # ---- Signals (current snapshot) ------------------------------
            sig = self._draw_signals(rng, tier)
            auto_renew_flag = sig["auto_renew_flag"]

            # ---- Seats from signal (integer) ------------------------------
            seats_int = max(1, int(round(sig["seats"])))

            # ---- Salesforce-specific metadata ----------------------------
            industry     = _INDUSTRIES[rank % len(_INDUSTRIES)]
            company_size = _COMPANY_SIZES[rank % len(_COMPANY_SIZES)]
            sf_owner     = _SF_OWNER_NAMES[rank % len(_SF_OWNER_NAMES)]

            # sf_account_type: churned HIGH-risk accounts become 'Former Customer'
            # We don't know churn outcome yet, so we mark HIGH tier as the
            # at-risk label; the outcome dict will correctly record churned/renewed.
            sf_account_type   = "Former Customer" if tier == "HIGH" else "Customer"
            sf_contract_status = "At Risk" if _is_high_risk(tier) else "Active"

            metadata = {
                "plan":               plan,
                "seats":              seats_int,
                "industry":           industry,
                "company_size":       company_size,
                "sf_account_type":    sf_account_type,
                "sf_owner_name":      sf_owner,
                "sf_contract_status": sf_contract_status,
            }

            # ---- Account row ---------------------------------------------
            accounts.append({
                "external_id": external_id,
                "name":        name,
                "domain":      domain,
                "arr":         arr,
                "status":      "active",
                "auto_renew":  bool(auto_renew_flag >= 0.5),
                "metadata":    metadata,
            })

            # ---- Outcome (probabilistic churn) ---------------------------
            churned = rng.random() < churn_rate
            if churned:
                days_ago      = int(rng.integers(15, 71))
                effective_dt  = _TODAY - timedelta(days=days_ago)
                effective_date = effective_dt.isoformat()
                recorded_at   = datetime(
                    effective_dt.year, effective_dt.month, effective_dt.day,
                    tzinfo=timezone.utc,
                ).isoformat()
                current_date = effective_dt - timedelta(days=15)
                outcomes.append({
                    "external_id":    external_id,
                    "outcome_type":   "churned",
                    "effective_date": effective_date,
                    "recorded_at":    recorded_at,
                })
            else:
                current_date = _TODAY - timedelta(days=2)

            historical_date = _TODAY - timedelta(days=90)

            # ---- Historical signals (slightly better than current) --------
            hist_sig = self._historical_signals(sig, tier)

            # ---- Emit signal rows ----------------------------------------
            signals.extend(self._build_signal_rows(
                external_id, historical_date.isoformat(), hist_sig, rng, tier,
            ))
            signals.extend(self._build_signal_rows(
                external_id, current_date.isoformat(), sig, rng, tier,
            ))

        return {"accounts": accounts, "signals": signals, "outcomes": outcomes}

    # ------------------------------------------------------------------
    # Internal helpers (identical logic to HubSpot generator)
    # ------------------------------------------------------------------

    def _draw_signals(self, rng: np.random.Generator, tier: str) -> dict:
        """Draw a full set of current-snapshot signal values for one account."""
        params = _SIG_PARAMS[tier]
        result: dict[str, float] = {}

        for key, (mean, std, lo, hi) in params.items():
            raw = float(np.clip(rng.normal(mean, std), lo, hi))
            if key == "nps_score":
                result[key] = round(raw, 1)
            else:
                result[key] = float(max(0, int(round(raw))))

        # auto_renew_flag: Bernoulli draw
        prob = _AUTO_RENEW_PROB[tier]
        result["auto_renew_flag"] = 1.0 if rng.random() < prob else 0.0

        return result

    def _historical_signals(self, current: dict, tier: str) -> dict:
        """Return a historical snapshot that is slightly better than *current*.

        For "bad direction" signals (high values are bad: days_since_last_login,
        support_tickets) the historical value is 0.7× the current value —
        i.e., the account looked healthier 90 days ago.
        For "good direction" signals (high values are good: monthly_logins,
        nps_score, days_until_renewal, seats) the historical value is ~1.10×
        the current value, capped at the tier ceiling.
        """
        hist = dict(current)

        bad_dir  = {"days_since_last_login", "support_tickets"}
        good_dir = {"monthly_logins", "nps_score", "days_until_renewal", "seats"}

        for key in bad_dir:
            if key in hist:
                hist[key] = round(hist[key] * 0.7, 1)
        for key in good_dir:
            if key in hist:
                _, _, _, hi = _SIG_PARAMS[tier][key]
                better = hist[key] * 1.10
                if key == "nps_score":
                    hist[key] = round(min(better, hi), 1)
                else:
                    hist[key] = float(min(int(round(better)), int(hi)))

        # auto_renew_flag is a contract attribute — keep unchanged
        return hist

    def _build_signal_rows(
        self,
        external_id: str,
        signal_date: str,
        sig: dict,
        rng: np.random.Generator,
        tier: str,
    ) -> list[dict]:
        """Convert a signal dict into a list of signal row dicts."""
        rows: list[dict] = []

        numeric_keys = [
            "days_since_last_login",
            "monthly_logins",
            "nps_score",
            "support_tickets",
            "days_until_renewal",
            "auto_renew_flag",
            "seats",
        ]

        for key in numeric_keys:
            rows.append({
                "external_id":  external_id,
                "signal_date":  signal_date,
                "signal_key":   key,
                "signal_value": sig.get(key),
                "signal_text":  None,
            })

        # contract_months_remaining derived from days_until_renewal
        dur = sig.get("days_until_renewal", 0.0)
        contract_months = int(round(dur / 30.2))
        rows.append({
            "external_id":  external_id,
            "signal_date":  signal_date,
            "signal_key":   "contract_months_remaining",
            "signal_value": float(contract_months),
            "signal_text":  None,
        })

        # extra JSON blob
        high_risk = _is_high_risk(tier)
        if high_risk:
            contact_count = int(rng.integers(1, 4))
            deal_count    = int(rng.integers(0, 2))
        else:
            contact_count = int(rng.integers(3, 12))
            deal_count    = int(rng.integers(1, 4))

        days_login = sig.get("days_since_last_login", 0.0)
        jitter_pct = rng.uniform(-0.20, 0.20)
        days_activity = round(max(0.0, days_login * (1.0 + jitter_pct)), 1)

        extra = {
            "contact_count":            contact_count,
            "deal_count":               deal_count,
            "days_since_last_activity": days_activity,
        }
        rows.append({
            "external_id":  external_id,
            "signal_date":  signal_date,
            "signal_key":   "extra",
            "signal_value": None,
            "signal_text":  json.dumps(extra),
        })

        return rows

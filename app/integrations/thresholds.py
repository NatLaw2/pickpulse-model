"""Single source of truth for CRM training eligibility thresholds.

Used by:
  - app/integrations/readiness.py  (eligibility gate shown to user before training)
  - app/crm_training.py            (data sufficiency check inside training pipeline)

Both layers MUST use these constants so the eligibility gate and the training
check are always in sync.  A mismatch causes confusing failures: the gate passes
the user through but the training check rejects them with a different threshold.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Eligibility gate (readiness.py)
# ---------------------------------------------------------------------------

# Minimum total synced accounts before any evaluation is meaningful.
MIN_TOTAL_ACCOUNTS: int = 10

# Minimum churned examples required to enable training.
# Set conservatively — below this the model has too little signal to be reliable.
MIN_CHURNED: int = 20

# Minimum fraction of accounts with at least one signal row.
MIN_SIGNAL_PCT: float = 0.15

# ---------------------------------------------------------------------------
# Training data sufficiency (crm_training.py)
# These map to MIN_POSITIVE_LABELED / MIN_NEGATIVE_LABELED / MIN_TOTAL_LABELED
# ---------------------------------------------------------------------------

# Total labeled rows required (churned + not-churned).
MIN_TOTAL_LABELED: int = 30

# Churned=1 examples required.  Must be ≤ MIN_CHURNED so the gate never passes
# fewer positive examples than training requires.
MIN_POSITIVE_LABELED: int = 10

# Churned=0 examples required.
MIN_NEGATIVE_LABELED: int = 10

# ---------------------------------------------------------------------------
# Confidence tiers
# ---------------------------------------------------------------------------

HIGH_CHURNED: int = 50
HIGH_SIGNAL: float = 0.70
HIGH_TOTAL: int = 200

MEDIUM_CHURNED: int = 20
MEDIUM_SIGNAL: float = 0.40
MEDIUM_TOTAL: int = 50

# ---------------------------------------------------------------------------
# Salesforce account sync ceiling — used to detect silent truncation.
# Must match _ACCOUNT_LIMIT in app/integrations/salesforce.py.
# ---------------------------------------------------------------------------
SF_ACCOUNT_LIMIT: int = 2000

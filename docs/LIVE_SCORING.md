# Live Scoring Guide

## Overview

Live scoring allows you to score real customer accounts from integrated systems (HubSpot, Stripe) against your trained churn model, without needing to export and upload CSVs.

## Prerequisites

1. **Trained model** — Train the churn model via the console or API
2. **Connected integration** — At least one connector configured and synced
3. **Synced accounts** — Run a sync to populate the accounts database

## How It Works

1. **Data Assembly**: The scoring engine joins accounts with their latest signals to build a flat DataFrame matching the churn model's input schema
2. **Feature Engineering**: The same normalization and derived features pipeline runs (ARR tier, engagement score, contract urgency, renewal windows)
3. **Model Inference**: The trained HistGradientBoostingClassifier produces calibrated churn probabilities
4. **Enrichment**: Each score gets tier classification, ARR at risk, urgency score, and recommended action
5. **Storage**: Scores are persisted to `churn_scores_daily` for historical tracking

## Scoring via Console

1. Navigate to **Integrations** page
2. Ensure accounts are synced (click **Sync Now** if needed)
3. Click **Score All Accounts** in the pipeline section
4. Results appear in the table below

## Scoring via API

```bash
# Score all synced accounts
curl -X POST http://localhost:8000/api/integrations/score

# Response:
# {
#   "status": "scored",
#   "accounts_scored": 150,
#   "tier_counts": {"High Risk": 23, "Medium Risk": 45, "Low Risk": 82},
#   "total_arr_at_risk": 1250000.00
# }

# Get latest scores
curl http://localhost:8000/api/integrations/scores/latest?limit=50
```

## Scoring via CLI

```bash
python scripts/live_score.py
```

Output:
```
Scoring 150 accounts...

Scored 150 accounts:
  High Risk:   23
  Medium Risk: 45
  Low Risk:    82
  Total ARR at risk: $1,250,000.00

Top 5 highest risk:
  cus_abc123: 87.3% (High Risk) — ARR at risk: $45,000
  ...
```

## Daily Automation

For production use, set up a cron job or scheduler:

```bash
# Sync + score daily at 6am
0 6 * * * cd /path/to/pickpulse-model && python scripts/sync_all.py && python scripts/live_score.py
```

## Data Flow

```
Integration APIs
      │
      ▼
  sync_all.py  →  accounts + account_signals_daily (SQLite)
      │
      ▼
  live_score.py  →  churn_scores_daily (SQLite)
      │
      ▼
  Console UI (Integrations page)  →  Latest Churn Scores table
```

## Score History

Scores are stored with timestamps, so you can track churn risk trends over time:

```sql
-- Score history for a specific account
SELECT scored_at, churn_probability, tier, arr_at_risk
FROM churn_scores_daily
WHERE external_id = 'cus_abc123'
ORDER BY scored_at DESC;
```

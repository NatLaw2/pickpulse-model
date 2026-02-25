# Integration Setup Guide

## Overview

PickPulse Intelligence supports direct integrations with HubSpot CRM and Stripe Billing to pull real customer data for churn scoring. This eliminates the need for CSV uploads and enables automated daily scoring.

## Architecture

```
HubSpot / Stripe  ──►  Sync Engine  ──►  SQLite (accounts + signals)
                                                    │
                                                    ▼
                                          Scoring Engine
                                                    │
                                                    ▼
                                          churn_scores_daily
                                                    │
                                                    ▼
                                          Console UI (Integrations page)
```

## Setup

### 1. HubSpot

1. Go to **Settings > Integrations > Private Apps** in your HubSpot account
2. Create a new private app with these scopes:
   - `crm.objects.companies.read`
   - `crm.objects.contacts.read`
   - `crm.objects.deals.read`
3. Copy the access token
4. In the PickPulse console, go to **Integrations** and click **Connect** on the HubSpot card
5. Paste your access token and click **Test & Save**

**What gets synced:**
- Companies → `accounts` table (name, industry, revenue, employee count)
- Contacts → seat count signal per company
- Deals → engagement proxy signal

### 2. Stripe

1. Go to **Developers > API Keys** in your Stripe dashboard
2. Copy your **Secret key** (starts with `sk_live_` or `sk_test_`)
3. In the PickPulse console, go to **Integrations** and click **Connect** on the Stripe card
4. Paste your API key and click **Test & Save**

**What gets synced:**
- Customers + Subscriptions → `accounts` table (name, email, ARR, plan)
- Subscription details → renewal signals (days_until_renewal, auto_renew, cancellation status)
- Invoices → engagement proxy

### 3. Trigger a Sync

After connecting, click **Sync Now** on the connector card. This pulls:
- All accounts from the external system
- Latest engagement/usage signals for each account

### 4. Score Accounts

Once accounts are synced and you have a trained churn model:
1. Click **Score All Accounts** in the scoring pipeline section
2. Results appear in the **Latest Churn Scores** table

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/integrations` | List all connectors and their status |
| `POST` | `/api/integrations/{name}/configure?api_key=...` | Configure a connector |
| `GET` | `/api/integrations/{name}/status` | Detailed connector status |
| `POST` | `/api/integrations/{name}/sync` | Trigger a sync |
| `GET` | `/api/integrations/accounts` | List synced accounts |
| `POST` | `/api/integrations/score` | Score all accounts |
| `GET` | `/api/integrations/scores/latest` | Get latest churn scores |

## CLI Scripts

```bash
# Sync all enabled connectors
python scripts/sync_all.py

# Score all synced accounts
python scripts/live_score.py
```

## Database

Integration data is stored in SQLite at `{DATA_DIR}/pickpulse.db` with three tables:

- **accounts** — normalized account records from all sources
- **account_signals_daily** — daily usage/engagement signals
- **churn_scores_daily** — historical churn scores per account

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_DIR` | Directory for SQLite database and data files | `data` |

API keys for connectors are stored in-memory only (per server session). For persistent configuration, set them via the API on each server start or use environment variables.

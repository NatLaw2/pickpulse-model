# Automation — Daily Sync & Score

## Overview

Two cron-protected API endpoints let an external scheduler (GitHub Actions,
Render Cron, etc.) keep accounts and scores fresh without manual clicks.

| Endpoint              | Method | What it does                                    |
|-----------------------|--------|-------------------------------------------------|
| `/api/cron/sync-all`  | POST   | Syncs every enabled connector (HubSpot, Stripe) |
| `/api/cron/score`     | POST   | Scores all synced accounts against the model     |

Both require a `Authorization: Bearer <CRON_API_KEY>` header.

## Environment Variables

| Variable          | Where to set       | Description                              |
|-------------------|--------------------|------------------------------------------|
| `CRON_API_KEY`    | Render + GitHub     | Shared secret protecting cron endpoints  |
| `RENDER_API_URL`  | GitHub Secrets only | e.g. `https://pickpulse-churn-api.onrender.com` |
| `SUPABASE_URL`    | Render              | Supabase project URL                     |
| `SUPABASE_SERVICE_ROLE_KEY` | Render    | Supabase service role key                |

## GitHub Actions Setup

1. Go to your repo → **Settings → Secrets and variables → Actions**.
2. Add two repository secrets:
   - `RENDER_API_URL` = `https://pickpulse-churn-api.onrender.com`
   - `CRON_API_KEY` = any strong random string (e.g. `openssl rand -hex 32`)
3. Set the same `CRON_API_KEY` in **Render → Environment**.
4. The workflow at `.github/workflows/daily-sync-score.yml` runs daily at
   06:00 UTC. You can also trigger it manually from the Actions tab.

## Manual Testing

```bash
# Sync
curl -X POST https://pickpulse-churn-api.onrender.com/api/cron/sync-all \
  -H "Authorization: Bearer $CRON_API_KEY"

# Score
curl -X POST https://pickpulse-churn-api.onrender.com/api/cron/score \
  -H "Authorization: Bearer $CRON_API_KEY"
```

## Run Demo (no auth required)

For a quick end-to-end test of a single connector:

```bash
curl -X POST https://pickpulse-churn-api.onrender.com/api/integrations/hubspot/run-demo
```

This syncs the connector and scores all accounts in one call. Also available
from the Integrations UI via the **Run Demo Sync + Score** button.

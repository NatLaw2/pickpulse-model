# Live Storage Audit — Integration Tables

**Date:** 2026-02-25
**Author:** automated audit

## What Was Using SQLite

The integration layer (`app/storage/`) stored three tables in a local SQLite file
(`{DATA_DIR}/pickpulse.db`):

| Table | Purpose | Written By | Read By |
|-------|---------|-----------|---------|
| `accounts` | Normalized customer records from HubSpot/Stripe | `repo.upsert_accounts()` via `sync.py` | `repo.list_accounts()`, `repo.account_count()`, `repo.get_account()` used by console_api endpoints + scoring.py |
| `account_signals_daily` | Daily engagement/usage signals per account | `repo.upsert_signals()` via `sync.py` | `repo.latest_signals()` used by `scoring.py` to build scoring DataFrame |
| `churn_scores_daily` | Churn model scores per account per run | `repo.insert_scores()` via `scoring.py` | `repo.latest_scores()`, `repo.score_history()` used by console_api GET endpoints |

### API Endpoints That Touch SQLite

| Endpoint | Operation |
|----------|-----------|
| `GET /api/integrations` | READ — `account_count()` per connector |
| `POST /api/integrations/{name}/configure` | None (in-memory only) |
| `GET /api/integrations/{name}/status` | READ — `account_count()` |
| `POST /api/integrations/{name}/sync` | WRITE — `upsert_accounts()`, `upsert_signals()` |
| `GET /api/integrations/accounts` | READ — `list_accounts()`, `account_count()` |
| `POST /api/integrations/score` | READ — `account_count()`, then WRITE via `scoring.py` → `insert_scores()` |
| `GET /api/integrations/scores/latest` | READ — `latest_scores()` |

Internal: `scoring.py._build_scoring_dataframe()` calls `list_accounts()` and
`latest_signals()` to assemble the input DataFrame.

### Additional Touch Point

`console_api.py` line 719: `get_connection()` is called at **module import time** to
initialize the SQLite DB and apply schema. This must be replaced with lazy Supabase
initialization.

## Why SQLite Is Not Production-Safe

1. **Render free-tier has no persistent disk.** `DATA_DIR=./data` is ephemeral — every
   deploy or dyno restart wipes the SQLite file along with all synced accounts, signals,
   and score history.
2. **Single-writer concurrency.** SQLite's WAL mode helps, but concurrent writes from
   multiple Uvicorn workers or async requests can still cause `SQLITE_BUSY` errors.
3. **No remote access.** The dashboard frontend cannot query SQLite directly; it must go
   through the API. With Supabase Postgres, the frontend could optionally use Row-Level
   Security for direct reads.
4. **No backups.** There is no backup or point-in-time recovery for the SQLite file.

## Resolution

Replace `app/storage/db.py` and `app/storage/repo.py` with a Supabase Postgres client.
Create the three tables as a Supabase migration. Delete `schema.sql`.

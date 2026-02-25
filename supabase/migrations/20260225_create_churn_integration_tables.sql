-- =============================================================================
-- Churn Integration Tables
-- Tables for the PickPulse Intelligence churn risk integration layer.
-- Stores synced accounts, daily signals, and churn scores from
-- HubSpot / Stripe connectors.
-- =============================================================================

-- Ensure uuid generation is available
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- 1) accounts
-- ---------------------------------------------------------------------------
create table if not exists public.accounts (
    id                uuid        primary key default gen_random_uuid(),
    external_id       text        not null,
    source            text        not null,          -- 'stripe', 'hubspot', 'csv'
    name              text        not null default '',
    domain            text,
    mrr               numeric,
    arr               numeric,
    currency          text,
    status            text,                          -- 'active', 'canceled', etc.
    contract_end_date date,
    auto_renew        boolean,
    metadata          jsonb       not null default '{}'::jsonb,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

-- Unique on (source, external_id) — one record per connector per external account
create unique index if not exists uq_accounts_source_external
    on public.accounts (source, external_id);

create index if not exists idx_accounts_source  on public.accounts (source);
create index if not exists idx_accounts_status  on public.accounts (status);

-- Auto-update updated_at
create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_accounts_updated_at on public.accounts;
create trigger trg_accounts_updated_at
    before update on public.accounts
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 2) account_signals_daily
-- ---------------------------------------------------------------------------
create table if not exists public.account_signals_daily (
    id            uuid        primary key default gen_random_uuid(),
    account_id    uuid        not null references public.accounts(id) on delete cascade,
    signal_date   date        not null,
    signal_key    text        not null,              -- e.g. 'invoices_paid_30d', 'tickets_30d'
    signal_value  numeric,
    signal_text   text,
    metadata      jsonb       not null default '{}'::jsonb,
    created_at    timestamptz not null default now()
);

create unique index if not exists uq_signals_account_date_key
    on public.account_signals_daily (account_id, signal_date, signal_key);

create index if not exists idx_signals_date
    on public.account_signals_daily (signal_date);

-- ---------------------------------------------------------------------------
-- 3) churn_scores_daily
-- ---------------------------------------------------------------------------
create table if not exists public.churn_scores_daily (
    id                 uuid        primary key default gen_random_uuid(),
    account_id         uuid        not null references public.accounts(id) on delete cascade,
    score_date         date        not null,
    churn_risk_pct     numeric     not null,
    urgency            numeric,
    renewal_window     text,
    arr_at_risk        numeric,
    recommended_action text,
    account_status     text,                         -- 'active', 'renewed', 'archived'
    model_version      text,
    features           jsonb       not null default '{}'::jsonb,
    created_at         timestamptz not null default now()
);

create unique index if not exists uq_scores_account_date
    on public.churn_scores_daily (account_id, score_date);

create index if not exists idx_scores_date
    on public.churn_scores_daily (score_date);

create index if not exists idx_scores_risk_desc
    on public.churn_scores_daily (churn_risk_pct desc);

-- account_outcomes: canonical outcome events per account.
-- Used for prediction-vs-actual reconciliation and model calibration trust layer.
-- outcome_type in ('renewed', 'churned', 'expanded')
-- source tracks how the outcome was recorded

create table if not exists public.account_outcomes (
    id             uuid primary key default gen_random_uuid(),
    tenant_id      text not null,
    account_id     uuid not null references public.accounts(id) on delete cascade,
    outcome_type   text not null check (outcome_type in ('renewed', 'churned', 'expanded')),
    effective_date date not null default current_date,
    source         text not null default 'manual'
                       check (source in ('manual', 'hubspot', 'stripe', 'system')),
    notes          text,
    recorded_at    timestamptz not null default now()
);

create index if not exists account_outcomes_tenant_account_idx
    on public.account_outcomes (tenant_id, account_id);

create index if not exists account_outcomes_tenant_date_idx
    on public.account_outcomes (tenant_id, effective_date desc);

-- RLS: service role bypasses; anon blocked by default
alter table public.account_outcomes enable row level security;

create policy "service_role full access" on public.account_outcomes
    to service_role
    using (true)
    with check (true);

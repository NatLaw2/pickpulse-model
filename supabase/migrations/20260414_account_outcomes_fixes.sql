-- account_outcomes: create table if missing, then ensure correct constraints.
-- Safe to run whether the table exists or not.

-- Step 1: Create the table with correct constraints if it doesn't exist yet.
create table if not exists public.account_outcomes (
    id             uuid primary key default gen_random_uuid(),
    tenant_id      text not null,
    account_id     uuid not null references public.accounts(id) on delete cascade,
    outcome_type   text not null check (outcome_type in ('renewed', 'churned', 'expanded')),
    effective_date date not null default current_date,
    source         text not null default 'manual'
                       check (source in ('manual', 'hubspot', 'salesforce', 'stripe', 'system')),
    notes          text,
    recorded_at    timestamptz not null default now()
);

-- Step 2: If the table already existed with the old source constraint (missing 'salesforce'),
-- drop it and add the correct one.
alter table public.account_outcomes
    drop constraint if exists account_outcomes_source_check;

alter table public.account_outcomes
    add constraint account_outcomes_source_check
    check (source in ('manual', 'hubspot', 'salesforce', 'stripe', 'system'));

-- Step 3: Add UNIQUE(tenant_id, account_id) for safe upsert semantics.
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'account_outcomes_tenant_account_unique'
    ) then
        alter table public.account_outcomes
            add constraint account_outcomes_tenant_account_unique
            unique (tenant_id, account_id);
    end if;
end
$$;

-- Step 4: Indexes (no-op if already exist).
create index if not exists account_outcomes_tenant_account_idx
    on public.account_outcomes (tenant_id, account_id);

create index if not exists account_outcomes_tenant_date_idx
    on public.account_outcomes (tenant_id, effective_date desc);

-- Step 5: RLS — service role full access; anon blocked by default.
alter table public.account_outcomes enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where tablename = 'account_outcomes'
          and policyname = 'service_role full access'
    ) then
        execute $policy$
            create policy "service_role full access" on public.account_outcomes
                to service_role
                using (true)
                with check (true)
        $policy$;
    end if;
end
$$;

-- Fix account_outcomes table:
-- 1. Add 'salesforce' to the source CHECK constraint (was missing, blocking Salesforce outcomes)
-- 2. Add UNIQUE(tenant_id, account_id) so demo seed can upsert safely without duplicates

-- Drop the old source constraint
alter table public.account_outcomes
    drop constraint if exists account_outcomes_source_check;

-- Add updated constraint that includes 'salesforce'
alter table public.account_outcomes
    add constraint account_outcomes_source_check
    check (source in ('manual', 'hubspot', 'salesforce', 'stripe', 'system'));

-- Add unique constraint on (tenant_id, account_id) so upsert on conflict works.
-- Use DO block to handle case where the constraint already exists.
do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'account_outcomes_tenant_account_unique'
    ) then
        alter table public.account_outcomes
            add constraint account_outcomes_tenant_account_unique
            unique (tenant_id, account_id);
    end if;
end
$$;

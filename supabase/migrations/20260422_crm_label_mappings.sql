-- =============================================================================
-- crm_label_mappings: customer-defined churn label mappings per tenant/provider.
--
-- Persists which CRM field + value(s) indicate a churned account.
-- Used by outcome_import.py during every sync to detect and label churned accounts.
-- One row per (tenant_id, provider) — upserted on save.
-- =============================================================================

create table if not exists public.crm_label_mappings (
    id              uuid        primary key default gen_random_uuid(),
    tenant_id       text        not null,
    provider        text        not null,
    field_name      text        not null,
    churned_values  jsonb       not null default '[]'::jsonb,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    constraint crm_label_mappings_tenant_provider_key
        unique (tenant_id, provider)
);

create index if not exists idx_crm_label_mappings_tenant
    on public.crm_label_mappings (tenant_id);

-- Reuse set_updated_at() defined by earlier migrations
drop trigger if exists trg_crm_label_mappings_updated_at on public.crm_label_mappings;
create trigger trg_crm_label_mappings_updated_at
    before update on public.crm_label_mappings
    for each row execute function public.set_updated_at();

alter table public.crm_label_mappings enable row level security;

create policy "service_role full access" on public.crm_label_mappings
    to service_role
    using (true)
    with check (true);

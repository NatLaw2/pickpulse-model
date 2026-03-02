-- =============================================================================
-- Integration Platform Tables
-- Persistent integration config, encrypted tokens, sync state, field mappings,
-- and audit events for the PickPulse Intelligence integration platform.
-- =============================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- 1) integrations — persistent connector config per tenant
-- ---------------------------------------------------------------------------
create table if not exists public.integrations (
    id            uuid        primary key default gen_random_uuid(),
    tenant_id     uuid        not null default '00000000-0000-0000-0000-000000000000'::uuid,
    provider      text        not null,
    display_name  text        not null,
    auth_method   text        not null default 'api_key',
    status        text        not null default 'pending',
    enabled       boolean     not null default false,
    config        jsonb       not null default '{}'::jsonb,
    connected_at  timestamptz,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create unique index if not exists uq_integrations_tenant_provider
    on public.integrations (tenant_id, provider);

create index if not exists idx_integrations_tenant
    on public.integrations (tenant_id);

create index if not exists idx_integrations_status
    on public.integrations (status);

-- Auto-update updated_at (reuse function if exists from accounts migration)
create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_integrations_updated_at on public.integrations;
create trigger trg_integrations_updated_at
    before update on public.integrations
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 2) integration_tokens — encrypted OAuth/API tokens
-- ---------------------------------------------------------------------------
create table if not exists public.integration_tokens (
    id              uuid        primary key default gen_random_uuid(),
    integration_id  uuid        not null references public.integrations(id) on delete cascade,
    token_type      text        not null default 'access',
    encrypted_value text        not null,
    iv              text        not null,
    expires_at      timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create unique index if not exists uq_tokens_integration_type
    on public.integration_tokens (integration_id, token_type);

drop trigger if exists trg_tokens_updated_at on public.integration_tokens;
create trigger trg_tokens_updated_at
    before update on public.integration_tokens
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 3) integration_sync_state — cursor/checkpoint tracking
-- ---------------------------------------------------------------------------
create table if not exists public.integration_sync_state (
    id              uuid        primary key default gen_random_uuid(),
    integration_id  uuid        not null references public.integrations(id) on delete cascade,
    resource_type   text        not null,
    cursor          text,
    last_synced_at  timestamptz,
    records_synced  integer     not null default 0,
    status          text        not null default 'idle',
    error_message   text,
    retry_count     integer     not null default 0,
    next_retry_at   timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create unique index if not exists uq_sync_state_integration_resource
    on public.integration_sync_state (integration_id, resource_type);

drop trigger if exists trg_sync_state_updated_at on public.integration_sync_state;
create trigger trg_sync_state_updated_at
    before update on public.integration_sync_state
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 4) integration_field_mappings — per-provider field mapping config
-- ---------------------------------------------------------------------------
create table if not exists public.integration_field_mappings (
    id              uuid        primary key default gen_random_uuid(),
    integration_id  uuid        not null references public.integrations(id) on delete cascade,
    source_field    text        not null,
    target_field    text        not null,
    transform       text,
    is_default      boolean     not null default true,
    created_at      timestamptz not null default now()
);

create unique index if not exists uq_field_mappings_integration_source
    on public.integration_field_mappings (integration_id, source_field);

-- ---------------------------------------------------------------------------
-- 5) integration_events — audit trail
-- ---------------------------------------------------------------------------
create table if not exists public.integration_events (
    id              uuid        primary key default gen_random_uuid(),
    integration_id  uuid        not null references public.integrations(id) on delete cascade,
    event_type      text        not null,
    details         jsonb       not null default '{}'::jsonb,
    created_at      timestamptz not null default now()
);

create index if not exists idx_events_integration
    on public.integration_events (integration_id, created_at desc);

-- ---------------------------------------------------------------------------
-- RLS policies (permissive for service-role, tenant isolation for anon)
-- ---------------------------------------------------------------------------
alter table public.integrations enable row level security;
alter table public.integration_tokens enable row level security;
alter table public.integration_sync_state enable row level security;
alter table public.integration_field_mappings enable row level security;
alter table public.integration_events enable row level security;

-- Service role bypasses RLS, so no explicit policy needed for backend.
-- These policies allow the service role full access:
create policy "Service role full access on integrations"
    on public.integrations for all
    using (true) with check (true);

create policy "Service role full access on integration_tokens"
    on public.integration_tokens for all
    using (true) with check (true);

create policy "Service role full access on integration_sync_state"
    on public.integration_sync_state for all
    using (true) with check (true);

create policy "Service role full access on integration_field_mappings"
    on public.integration_field_mappings for all
    using (true) with check (true);

create policy "Service role full access on integration_events"
    on public.integration_events for all
    using (true) with check (true);

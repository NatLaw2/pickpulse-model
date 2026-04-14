"""Integration service layer — persistent config, encrypted tokens, sync state."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.storage.db import get_client
from app.integrations.crypto import encrypt_token, decrypt_token
from app.integrations import oauth as oauth_module
from app.integrations.models import SyncResult

logger = logging.getLogger(__name__)

# Default tenant for single-tenant mode
DEFAULT_TENANT = "00000000-0000-0000-0000-000000000000"

TEMPLATES_DIR = Path(__file__).parent / "templates"


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

def _load_templates() -> Dict[str, Dict[str, Any]]:
    """Load all provider template JSON files."""
    templates: Dict[str, Dict[str, Any]] = {}
    if not TEMPLATES_DIR.exists():
        return templates
    for f in TEMPLATES_DIR.glob("*.json"):
        try:
            with open(f) as fh:
                data = json.load(fh)
                templates[data["provider"]] = data
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to load template %s: %s", f, exc)
    return templates


_templates_cache: Optional[Dict[str, Dict[str, Any]]] = None


def get_templates() -> Dict[str, Dict[str, Any]]:
    """Get cached provider templates."""
    global _templates_cache
    if _templates_cache is None:
        _templates_cache = _load_templates()
    return _templates_cache


def get_template(provider: str) -> Optional[Dict[str, Any]]:
    """Get a single provider template."""
    return get_templates().get(provider)


# ---------------------------------------------------------------------------
# Integration CRUD
# ---------------------------------------------------------------------------

def list_integrations(tenant_id: str = DEFAULT_TENANT) -> List[Dict[str, Any]]:
    """List all providers with their integration status.

    Merges template metadata with DB state.
    """
    templates = get_templates()
    sb = get_client()

    # Get all integrations for this tenant
    res = sb.table("integrations").select("*").eq("tenant_id", tenant_id).execute()
    db_integrations = {row["provider"]: row for row in (res.data or [])}

    result = []
    for provider, tmpl in templates.items():
        db_row = db_integrations.get(provider)
        result.append({
            "provider": provider,
            "display_name": tmpl["display_name"],
            "category": tmpl.get("category", ""),
            "auth_method": tmpl["auth_method"],
            "icon": tmpl.get("icon", "plug"),
            "description": tmpl.get("description", ""),
            "status": db_row["status"] if db_row else "not_configured",
            "enabled": db_row["enabled"] if db_row else False,
            "connected_at": db_row["connected_at"] if db_row else None,
            "template_status": tmpl.get("status", "coming_soon"),
            "integration_id": db_row["id"] if db_row else None,
        })

    return result


def get_integration(
    tenant_id: str = DEFAULT_TENANT,
    provider: Optional[str] = None,
    integration_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get a single integration by provider name or ID."""
    sb = get_client()
    q = sb.table("integrations").select("*")
    if integration_id:
        q = q.eq("id", integration_id)
    else:
        q = q.eq("tenant_id", tenant_id).eq("provider", provider)
    res = q.limit(1).execute()
    return res.data[0] if res.data else None


# ---------------------------------------------------------------------------
# Connect (API key)
# ---------------------------------------------------------------------------

def connect_api_key(
    tenant_id: str,
    provider: str,
    api_key: str,
) -> Dict[str, Any]:
    """Connect a provider using an API key.

    Encrypts the key, creates/updates the integration record.
    """
    sb = get_client()
    tmpl = get_template(provider)
    display_name = tmpl["display_name"] if tmpl else provider.title()

    # Upsert integration record
    integration_data = {
        "tenant_id": tenant_id,
        "provider": provider,
        "display_name": display_name,
        "auth_method": "api_key",
        "status": "connected",
        "enabled": True,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }
    res = sb.table("integrations").upsert(
        integration_data, on_conflict="tenant_id,provider"
    ).execute()
    integration = res.data[0]
    integration_id = integration["id"]

    # Encrypt and store the API key
    ciphertext, iv = encrypt_token(api_key)
    sb.table("integration_tokens").upsert(
        {
            "integration_id": integration_id,
            "token_type": "api_key",
            "encrypted_value": ciphertext,
            "iv": iv,
            "expires_at": None,
        },
        on_conflict="integration_id,token_type",
    ).execute()

    # Seed default field mappings if not already present
    _seed_default_mappings(integration_id, provider)

    # Log event
    log_event(integration_id, "connected", {"method": "api_key"})

    return integration


# ---------------------------------------------------------------------------
# Connect (OAuth)
# ---------------------------------------------------------------------------

def start_oauth(
    tenant_id: str,
    provider: str,
    redirect_uri: str,
) -> Dict[str, str]:
    """Start OAuth flow. Returns {auth_url, state}."""
    auth_url, state = oauth_module.generate_auth_url(provider, tenant_id, redirect_uri)
    return {"auth_url": auth_url, "state": state}


def complete_oauth(
    provider: str,
    code: str,
    state: str,
    redirect_uri: str,
) -> Dict[str, Any]:
    """Complete OAuth flow. Validates state, exchanges code, stores tokens."""
    # Validate state
    payload = oauth_module.validate_state(state)
    if payload["provider"] != provider:
        raise ValueError("State provider mismatch")

    tenant_id = payload["tenant_id"]

    # Exchange code for tokens
    tokens = oauth_module.exchange_code(provider, code, redirect_uri)

    sb = get_client()
    tmpl = get_template(provider)
    display_name = tmpl["display_name"] if tmpl else provider.title()

    # Upsert integration
    integration_data = {
        "tenant_id": tenant_id,
        "provider": provider,
        "display_name": display_name,
        "auth_method": "oauth",
        "status": "connected",
        "enabled": True,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }
    res = sb.table("integrations").upsert(
        integration_data, on_conflict="tenant_id,provider"
    ).execute()
    integration = res.data[0]
    integration_id = integration["id"]

    # Store encrypted access token
    ct, iv = encrypt_token(tokens["access_token"])
    expires_at = None
    if tokens.get("expires_in"):
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
        ).isoformat()

    sb.table("integration_tokens").upsert(
        {
            "integration_id": integration_id,
            "token_type": "access",
            "encrypted_value": ct,
            "iv": iv,
            "expires_at": expires_at,
        },
        on_conflict="integration_id,token_type",
    ).execute()

    # Store refresh token if provided
    if tokens.get("refresh_token"):
        rt_ct, rt_iv = encrypt_token(tokens["refresh_token"])
        sb.table("integration_tokens").upsert(
            {
                "integration_id": integration_id,
                "token_type": "refresh",
                "encrypted_value": rt_ct,
                "iv": rt_iv,
                "expires_at": None,
            },
            on_conflict="integration_id,token_type",
        ).execute()

    # Store instance_url if provided (Salesforce returns org-specific API base URL)
    if tokens.get("instance_url"):
        iu_ct, iu_iv = encrypt_token(tokens["instance_url"])
        sb.table("integration_tokens").upsert(
            {
                "integration_id": integration_id,
                "token_type": "instance_url",
                "encrypted_value": iu_ct,
                "iv": iu_iv,
                "expires_at": None,
            },
            on_conflict="integration_id,token_type",
        ).execute()

    # Seed default field mappings
    _seed_default_mappings(integration_id, provider)

    # Log event
    log_event(integration_id, "connected", {"method": "oauth"})

    return integration


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------

def disconnect(tenant_id: str, provider: str) -> None:
    """Disconnect an integration — purge tokens, clear stale scores, disable."""
    integration = get_integration(tenant_id=tenant_id, provider=provider)
    if not integration:
        return

    sb = get_client()
    integration_id = integration["id"]

    # Delete tokens
    sb.table("integration_tokens").delete().eq(
        "integration_id", integration_id
    ).execute()

    # Update status
    sb.table("integrations").update({
        "status": "disconnected",
        "enabled": False,
    }).eq("id", integration_id).execute()

    # Clear stale churn scores so reconnecting does not pre-populate the UI
    # with results from a prior session before the user re-trains/re-scores.
    try:
        from app.storage import repo
        repo.clear_scores_for_source(provider, tenant_id=tenant_id)
    except Exception as exc:
        logger.warning("disconnect: score clear failed for %s: %s", provider, exc)

    log_event(integration_id, "disconnected", {})


# ---------------------------------------------------------------------------
# Token access (with auto-refresh)
# ---------------------------------------------------------------------------

def get_decrypted_token(
    integration_id: str,
    token_type: str = "access",
) -> Optional[str]:
    """Get decrypted token. Auto-refreshes OAuth tokens if expiring within 5 min."""
    sb = get_client()

    res = sb.table("integration_tokens").select("*").eq(
        "integration_id", integration_id
    ).eq("token_type", token_type).limit(1).execute()

    if not res.data:
        # Fall back to api_key token type
        if token_type == "access":
            res = sb.table("integration_tokens").select("*").eq(
                "integration_id", integration_id
            ).eq("token_type", "api_key").limit(1).execute()
            if not res.data:
                return None

    token_row = res.data[0]

    # Check if OAuth access token needs refresh
    if token_row["token_type"] == "access" and token_row.get("expires_at"):
        expires_at = datetime.fromisoformat(token_row["expires_at"].replace("Z", "+00:00"))
        if expires_at - datetime.now(timezone.utc) < timedelta(minutes=5):
            # Try to refresh
            refreshed = _try_refresh_token(integration_id)
            if refreshed:
                return refreshed

    return decrypt_token(token_row["encrypted_value"], token_row["iv"])


def _try_refresh_token(integration_id: str) -> Optional[str]:
    """Attempt to refresh an OAuth access token using the refresh token."""
    sb = get_client()

    # Get integration to find provider
    int_res = sb.table("integrations").select("provider").eq(
        "id", integration_id
    ).limit(1).execute()
    if not int_res.data:
        return None
    provider = int_res.data[0]["provider"]

    # Get refresh token
    rt_res = sb.table("integration_tokens").select("*").eq(
        "integration_id", integration_id
    ).eq("token_type", "refresh").limit(1).execute()
    if not rt_res.data:
        return None

    refresh_token = decrypt_token(rt_res.data[0]["encrypted_value"], rt_res.data[0]["iv"])

    try:
        tokens = oauth_module.refresh_access_token(provider, refresh_token)
    except Exception as exc:
        logger.warning("Token refresh failed for %s: %s", integration_id, exc)
        return None

    # Store new access token
    new_access = tokens["access_token"]
    ct, iv = encrypt_token(new_access)
    expires_at = None
    if tokens.get("expires_in"):
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
        ).isoformat()

    sb.table("integration_tokens").upsert(
        {
            "integration_id": integration_id,
            "token_type": "access",
            "encrypted_value": ct,
            "iv": iv,
            "expires_at": expires_at,
        },
        on_conflict="integration_id,token_type",
    ).execute()

    log_event(integration_id, "token_refreshed", {})
    return new_access


# ---------------------------------------------------------------------------
# Field mappings
# ---------------------------------------------------------------------------

def get_field_mappings(integration_id: str) -> List[Dict[str, Any]]:
    """Get field mappings for an integration."""
    sb = get_client()
    res = sb.table("integration_field_mappings").select("*").eq(
        "integration_id", integration_id
    ).order("source_field").execute()
    return res.data or []


def update_field_mappings(
    integration_id: str,
    mappings: List[Dict[str, str]],
) -> int:
    """Upsert field mappings. Each dict has: source_field, target_field, transform."""
    sb = get_client()
    rows = []
    for m in mappings:
        rows.append({
            "integration_id": integration_id,
            "source_field": m["source_field"],
            "target_field": m["target_field"],
            "transform": m.get("transform", "direct"),
            "is_default": False,
        })
    if not rows:
        return 0
    res = sb.table("integration_field_mappings").upsert(
        rows, on_conflict="integration_id,source_field"
    ).execute()
    return len(res.data) if res.data else 0


def _seed_default_mappings(integration_id: str, provider: str) -> None:
    """Seed default field mappings from the provider template."""
    tmpl = get_template(provider)
    if not tmpl or "default_field_map" not in tmpl:
        return

    sb = get_client()
    # Check if mappings already exist
    existing = sb.table("integration_field_mappings").select("id").eq(
        "integration_id", integration_id
    ).limit(1).execute()
    if existing.data:
        return  # Already seeded

    rows = []
    for source, mapping in tmpl["default_field_map"].items():
        rows.append({
            "integration_id": integration_id,
            "source_field": source,
            "target_field": mapping["target"],
            "transform": mapping.get("transform", "direct"),
            "is_default": True,
        })
    if rows:
        sb.table("integration_field_mappings").upsert(
            rows, on_conflict="integration_id,source_field"
        ).execute()


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------

def get_sync_state(integration_id: str) -> List[Dict[str, Any]]:
    """Get sync state for all resource types of an integration."""
    sb = get_client()
    res = sb.table("integration_sync_state").select("*").eq(
        "integration_id", integration_id
    ).execute()
    return res.data or []


def update_sync_state(
    integration_id: str,
    resource_type: str,
    *,
    status: Optional[str] = None,
    cursor: Optional[str] = None,
    records_synced: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    """Update sync state for a resource type."""
    sb = get_client()
    row: Dict[str, Any] = {
        "integration_id": integration_id,
        "resource_type": resource_type,
    }
    if status is not None:
        row["status"] = status
    if status == "completed":
        row["last_synced_at"] = datetime.now(timezone.utc).isoformat()
        row["error_message"] = None
        row["retry_count"] = 0
    if status == "failed":
        row["error_message"] = error_message
    if cursor is not None:
        row["cursor"] = cursor
    if records_synced is not None:
        row["records_synced"] = records_synced

    sb.table("integration_sync_state").upsert(
        row, on_conflict="integration_id,resource_type"
    ).execute()


# ---------------------------------------------------------------------------
# Sync orchestration
# ---------------------------------------------------------------------------

def trigger_sync(tenant_id: str, provider: str) -> SyncResult:
    """Trigger a sync for an integration.

    Uses the service layer for token access and sync state tracking.
    """
    from app.integrations.registry import get_connector_for_integration
    from app.storage import repo

    integration = get_integration(tenant_id=tenant_id, provider=provider)
    if not integration:
        return SyncResult(connector=provider, errors=[f"Integration '{provider}' not found"])

    integration_id = integration["id"]
    start = time.time()
    result = SyncResult(connector=provider)

    # Get connector instance with decrypted token
    try:
        connector = get_connector_for_integration(integration_id)
    except Exception as exc:
        logger.exception("get_connector_for_integration raised for %s", provider)
        result.errors.append(f"Could not build connector for '{provider}': {exc}")
        return result
    if connector is None:
        result.errors.append(f"Could not instantiate connector for '{provider}'")
        return result

    # Update integration status
    sb = get_client()
    sb.table("integrations").update({"status": "syncing"}).eq("id", integration_id).execute()

    # Sync accounts
    update_sync_state(integration_id, "accounts", status="running")
    try:
        accounts = connector.pull_accounts()
        result.accounts_synced = repo.upsert_accounts(accounts, tenant_id=tenant_id)
        update_sync_state(
            integration_id, "accounts",
            status="completed",
            records_synced=result.accounts_synced,
        )
    except Exception as exc:
        logger.exception("Failed to pull accounts from %s", provider)
        result.errors.append(f"Account pull failed: {exc}")
        update_sync_state(
            integration_id, "accounts",
            status="failed",
            error_message=str(exc),
        )

    # Sync signals
    if result.accounts_synced > 0:
        update_sync_state(integration_id, "signals", status="running")
        try:
            stored = repo.list_accounts(source=provider, limit=10000, tenant_id=tenant_id)
            eids = [a["external_id"] for a in stored]
            signals = connector.pull_signals(eids)
            result.signals_synced = repo.upsert_signals(signals, tenant_id=tenant_id)
            update_sync_state(
                integration_id, "signals",
                status="completed",
                records_synced=result.signals_synced,
            )
        except Exception as exc:
            logger.exception("Failed to pull signals from %s", provider)
            result.errors.append(f"Signal pull failed: {exc}")
            update_sync_state(
                integration_id, "signals",
                status="failed",
                error_message=str(exc),
            )

    result.duration_seconds = round(time.time() - start, 2)

    # Update integration status
    new_status = "healthy" if not result.errors else "error"
    sb.table("integrations").update({"status": new_status}).eq("id", integration_id).execute()

    # Log event
    log_event(integration_id, "sync_completed", {
        "accounts": result.accounts_synced,
        "signals": result.signals_synced,
        "errors": result.errors,
        "duration": result.duration_seconds,
    })

    return result


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def check_health(tenant_id: str, provider: str) -> Dict[str, Any]:
    """Check connection health for an integration."""
    from app.integrations.registry import get_connector_for_integration
    from app.storage import repo

    integration = get_integration(tenant_id=tenant_id, provider=provider)
    if not integration:
        return {"provider": provider, "status": "not_configured", "connected": False}

    connector = get_connector_for_integration(integration["id"])
    connected = False
    if connector:
        try:
            connected = connector.test_connection()
        except Exception:
            connected = False

    account_count = repo.account_count(source=provider, tenant_id=tenant_id)
    sync_states = get_sync_state(integration["id"])

    return {
        "provider": provider,
        "status": integration["status"],
        "connected": connected,
        "enabled": integration["enabled"],
        "account_count": account_count,
        "connected_at": integration.get("connected_at"),
        "sync_states": sync_states,
    }


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def log_event(
    integration_id: str,
    event_type: str,
    details: Dict[str, Any],
) -> None:
    """Write an audit event."""
    try:
        sb = get_client()
        sb.table("integration_events").insert({
            "integration_id": integration_id,
            "event_type": event_type,
            "details": details,
        }).execute()
    except Exception as exc:
        logger.warning("Failed to log event: %s", exc)


def get_events(
    integration_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Get recent events for an integration."""
    sb = get_client()
    res = sb.table("integration_events").select("*").eq(
        "integration_id", integration_id
    ).order("created_at", desc=True).limit(limit).execute()
    return res.data or []

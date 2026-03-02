"""OAuth Authorization Code flow + HMAC-signed state validation."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import requests

# ---------------------------------------------------------------------------
# Provider OAuth configs (loaded from templates at import time)
# ---------------------------------------------------------------------------

_OAUTH_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "hubspot": {
        "authorize_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "scopes": "crm.objects.companies.read crm.objects.deals.read crm.objects.contacts.read crm.schemas.companies.read crm.objects.owners.read crm.objects.activities.read",
        "client_id_env": "HUBSPOT_CLIENT_ID",
        "client_secret_env": "HUBSPOT_CLIENT_SECRET",
    },
    "salesforce": {
        "authorize_url": "https://login.salesforce.com/services/oauth2/authorize",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "scopes": "api refresh_token",
        "client_id_env": "SALESFORCE_CLIENT_ID",
        "client_secret_env": "SALESFORCE_CLIENT_SECRET",
    },
    "intercom": {
        "authorize_url": "https://app.intercom.com/oauth",
        "token_url": "https://api.intercom.io/auth/eagle/token",
        "scopes": "",
        "client_id_env": "INTERCOM_CLIENT_ID",
        "client_secret_env": "INTERCOM_CLIENT_SECRET",
    },
}


def _get_state_secret() -> bytes:
    """Return the HMAC signing key for OAuth state params."""
    secret = os.environ.get("OAUTH_STATE_SECRET", "")
    if not secret:
        raise RuntimeError("OAUTH_STATE_SECRET env var is required for OAuth flows.")
    return secret.encode("utf-8")


def _get_provider_config(provider: str) -> Dict[str, Any]:
    """Get OAuth config for a provider."""
    cfg = _OAUTH_PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"No OAuth config for provider: {provider}")
    return cfg


# ---------------------------------------------------------------------------
# State token (HMAC-signed, JSON-encoded)
# ---------------------------------------------------------------------------

def generate_state(tenant_id: str, provider: str, redirect_uri: str) -> str:
    """Generate an HMAC-signed OAuth state token.

    Contains: tenant_id, provider, nonce, issued_at, redirect.
    """
    payload = {
        "tenant_id": tenant_id,
        "provider": provider,
        "nonce": secrets.token_hex(16),
        "issued_at": int(time.time()),
        "redirect": redirect_uri,
    }
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()

    sig = hmac.new(_get_state_secret(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def validate_state(state_token: str, max_age_seconds: int = 600) -> Dict[str, Any]:
    """Validate an HMAC-signed state token. Returns the payload dict.

    Raises ValueError on invalid/expired state.
    """
    parts = state_token.split(".", 1)
    if len(parts) != 2:
        raise ValueError("Malformed state token")

    payload_b64, sig = parts
    expected_sig = hmac.new(
        _get_state_secret(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid state signature")

    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (json.JSONDecodeError, Exception) as exc:
        raise ValueError(f"Failed to decode state payload: {exc}")

    issued_at = payload.get("issued_at", 0)
    if time.time() - issued_at > max_age_seconds:
        raise ValueError("State token expired")

    return payload


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def generate_auth_url(
    provider: str,
    tenant_id: str,
    redirect_uri: str,
) -> Tuple[str, str]:
    """Build the OAuth authorization URL for a provider.

    Returns (auth_url, state_token).
    """
    cfg = _get_provider_config(provider)
    client_id = os.environ.get(cfg["client_id_env"], "")
    if not client_id:
        raise RuntimeError(f"{cfg['client_id_env']} env var is required for {provider} OAuth")

    state = generate_state(tenant_id, provider, redirect_uri)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": cfg["scopes"],
        "state": state,
        "response_type": "code",
    }

    auth_url = f"{cfg['authorize_url']}?{urlencode(params)}"
    return auth_url, state


def exchange_code(
    provider: str,
    code: str,
    redirect_uri: str,
) -> Dict[str, Any]:
    """Exchange an authorization code for access + refresh tokens.

    Returns dict with: access_token, refresh_token (optional), expires_in (optional).
    """
    cfg = _get_provider_config(provider)
    client_id = os.environ.get(cfg["client_id_env"], "")
    client_secret = os.environ.get(cfg["client_secret_env"], "")

    if not client_id or not client_secret:
        raise RuntimeError(
            f"{cfg['client_id_env']} and {cfg['client_secret_env']} env vars required"
        )

    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }

    resp = requests.post(cfg["token_url"], data=data, timeout=15)
    resp.raise_for_status()
    body = resp.json()

    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token"),
        "expires_in": body.get("expires_in"),
    }


def refresh_access_token(
    provider: str,
    refresh_token: str,
) -> Dict[str, Any]:
    """Refresh an OAuth access token.

    Returns dict with: access_token, expires_in.
    """
    cfg = _get_provider_config(provider)
    client_id = os.environ.get(cfg["client_id_env"], "")
    client_secret = os.environ.get(cfg["client_secret_env"], "")

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    resp = requests.post(cfg["token_url"], data=data, timeout=15)
    resp.raise_for_status()
    body = resp.json()

    return {
        "access_token": body["access_token"],
        "expires_in": body.get("expires_in"),
    }


def is_oauth_provider(provider: str) -> bool:
    """Check if a provider uses OAuth."""
    return provider in _OAUTH_PROVIDERS

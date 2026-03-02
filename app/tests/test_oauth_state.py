"""Tests for OAuth state token generation and validation."""
import time
import pytest


@pytest.fixture(autouse=True)
def set_oauth_secret(monkeypatch):
    """Set a test OAuth state secret."""
    monkeypatch.setenv("OAUTH_STATE_SECRET", "test-secret-key-for-hmac-signing")


def test_generate_validate_roundtrip():
    """State token survives generate → validate roundtrip."""
    from app.integrations.oauth import generate_state, validate_state

    state = generate_state("tenant-123", "hubspot", "https://app.example.com/callback")
    payload = validate_state(state)

    assert payload["tenant_id"] == "tenant-123"
    assert payload["provider"] == "hubspot"
    assert payload["redirect"] == "https://app.example.com/callback"
    assert "nonce" in payload
    assert "issued_at" in payload


def test_state_contains_dot_separator():
    """State token has payload.signature format."""
    from app.integrations.oauth import generate_state

    state = generate_state("t", "p", "r")
    assert "." in state
    parts = state.split(".")
    assert len(parts) == 2


def test_expired_state_rejected(monkeypatch):
    """Expired state token is rejected."""
    from app.integrations.oauth import generate_state, validate_state

    state = generate_state("tenant-123", "hubspot", "https://example.com/cb")

    # Pretend 15 minutes have passed (max_age is 600s = 10min)
    with pytest.raises(ValueError, match="expired"):
        validate_state(state, max_age_seconds=0)


def test_tampered_state_rejected():
    """Tampered state token is rejected."""
    from app.integrations.oauth import generate_state, validate_state

    state = generate_state("tenant-123", "hubspot", "https://example.com/cb")

    # Tamper with the payload
    parts = state.split(".")
    tampered = parts[0][:-1] + ("A" if parts[0][-1] != "A" else "B") + "." + parts[1]

    with pytest.raises(ValueError, match="Invalid state signature"):
        validate_state(tampered)


def test_malformed_state_rejected():
    """Malformed state token is rejected."""
    from app.integrations.oauth import validate_state

    with pytest.raises(ValueError, match="Malformed"):
        validate_state("no-dot-here")


def test_wrong_secret_rejects(monkeypatch):
    """State signed with different secret is rejected."""
    from app.integrations.oauth import generate_state, validate_state

    state = generate_state("tenant-123", "hubspot", "https://example.com/cb")

    # Change the secret
    monkeypatch.setenv("OAUTH_STATE_SECRET", "different-secret")

    # Need to reload to pick up new secret
    import importlib
    import app.integrations.oauth as oauth_mod
    importlib.reload(oauth_mod)

    with pytest.raises(ValueError, match="Invalid state signature"):
        oauth_mod.validate_state(state)


def test_different_tenants_produce_different_states():
    """Different tenant_ids produce different state tokens."""
    from app.integrations.oauth import generate_state

    s1 = generate_state("tenant-1", "hubspot", "https://example.com/cb")
    s2 = generate_state("tenant-2", "hubspot", "https://example.com/cb")
    assert s1 != s2


def test_nonce_unique():
    """Each state token has a unique nonce."""
    from app.integrations.oauth import generate_state, validate_state

    s1 = generate_state("t", "p", "r")
    s2 = generate_state("t", "p", "r")

    p1 = validate_state(s1)
    p2 = validate_state(s2)
    assert p1["nonce"] != p2["nonce"]

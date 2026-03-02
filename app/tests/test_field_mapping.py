"""Tests for provider template loading and field mapping transforms."""
import json
import os
import pytest
from pathlib import Path


TEMPLATES_DIR = Path(__file__).parent.parent / "integrations" / "templates"


def test_all_templates_valid_json():
    """All template files are valid JSON."""
    for f in TEMPLATES_DIR.glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
        assert "provider" in data, f"{f.name} missing 'provider'"
        assert "display_name" in data, f"{f.name} missing 'display_name'"
        assert "auth_method" in data, f"{f.name} missing 'auth_method'"
        assert "status" in data, f"{f.name} missing 'status'"


def test_template_count():
    """We have 11 provider templates."""
    templates = list(TEMPLATES_DIR.glob("*.json"))
    assert len(templates) == 11


def test_available_providers():
    """At least HubSpot, Stripe, and CSV are 'available'."""
    available = []
    for f in TEMPLATES_DIR.glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
        if data.get("status") == "available":
            available.append(data["provider"])
    assert "hubspot" in available
    assert "stripe" in available
    assert "csv" in available


def test_hubspot_template_has_oauth_fields():
    """HubSpot template has OAuth-specific fields."""
    with open(TEMPLATES_DIR / "hubspot.json") as f:
        data = json.load(f)
    assert data["auth_method"] == "oauth"
    assert "oauth_scopes" in data
    assert "oauth_authorize_url" in data
    assert "oauth_token_url" in data


def test_stripe_template_has_api_key():
    """Stripe template uses API key auth."""
    with open(TEMPLATES_DIR / "stripe.json") as f:
        data = json.load(f)
    assert data["auth_method"] == "api_key"


def test_all_templates_have_default_field_map():
    """All templates have a default_field_map."""
    for f in TEMPLATES_DIR.glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
        assert "default_field_map" in data, f"{f.name} missing 'default_field_map'"
        field_map = data["default_field_map"]
        assert isinstance(field_map, dict)
        for source, mapping in field_map.items():
            assert "target" in mapping, f"{f.name}: mapping for '{source}' missing 'target'"


def test_field_map_targets_are_valid():
    """All field map targets are recognized PickPulse account fields."""
    valid_targets = {
        "name", "domain", "arr", "plan", "industry", "company_size", "seats",
        "monthly_logins", "support_tickets", "nps_score", "days_since_last_login",
        "days_until_renewal", "created_at",
    }

    for f in TEMPLATES_DIR.glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
        for source, mapping in data.get("default_field_map", {}).items():
            target = mapping["target"]
            assert target in valid_targets, (
                f"{f.name}: unknown target '{target}' for source '{source}'. "
                f"Valid targets: {valid_targets}"
            )


def test_all_templates_have_sample_payload():
    """All templates include a sample_payload for preview."""
    for f in TEMPLATES_DIR.glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
        assert "sample_payload" in data, f"{f.name} missing 'sample_payload'"


def test_coming_soon_templates():
    """Coming soon templates exist for expected providers."""
    expected_coming_soon = {"salesforce", "chargebee", "zendesk", "intercom", "segment", "amplitude", "mixpanel"}
    coming_soon = set()
    for f in TEMPLATES_DIR.glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
        if data.get("status") == "coming_soon":
            coming_soon.add(data["provider"])

    for provider in expected_coming_soon:
        assert provider in coming_soon, f"{provider} should be 'coming_soon'"


def test_custom_crm_has_requires_config():
    """Custom CRM template has configuration fields."""
    with open(TEMPLATES_DIR / "custom_crm.json") as f:
        data = json.load(f)
    assert "requires_config" in data
    assert "base_url" in data["requires_config"]


def test_csv_template_has_validation_rules():
    """CSV template has validation rules."""
    with open(TEMPLATES_DIR / "csv.json") as f:
        data = json.load(f)
    assert "validation_rules" in data
    assert "required_columns" in data["validation_rules"]

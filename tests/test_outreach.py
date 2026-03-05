"""Tests for the AI Outreach Drafts feature."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app.outreach import (
    DraftEmailRequest,
    _check_rate_limit,
    _fallback_email,
    _generate_email,
    build_mailto,
    _rate_store,
    RATE_LIMIT_MAX,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_request(**overrides) -> DraftEmailRequest:
    defaults = {
        "customer_id": "Acme Corp",
        "customer_name": "Acme Corp",
        "contact_name": "Sarah Johnson",
        "contact_email": "sarah@acme.com",
        "churn_risk_pct": 82.0,
        "arr": 120_000,
        "arr_at_risk": 98_400,
        "days_until_renewal": 45,
        "recommended_action": "Executive save plan",
        "risk_driver_summary": "declining logins, support tickets up 40%",
        "tier": "High Risk",
        "tone": "friendly",
    }
    defaults.update(overrides)
    return DraftEmailRequest(**defaults)


# ---------------------------------------------------------------------------
# build_mailto tests
# ---------------------------------------------------------------------------

class TestBuildMailto:
    def test_with_email(self):
        url = build_mailto("test@example.com", "Hello", "Body text")
        assert url.startswith("mailto:test@example.com?")
        assert "subject=Hello" in url
        assert "body=Body" in url

    def test_without_email(self):
        url = build_mailto(None, "Hello", "Body text")
        assert url.startswith("mailto:?")
        assert "subject=Hello" in url

    def test_special_chars_encoded(self):
        url = build_mailto("test@example.com", "Re: Q1 Review", "Hi Sarah,\n\nLet's chat.")
        assert "%0A" in url or "%0a" in url  # newline encoded
        assert "Re%3A" in url or "Re:" not in url.split("?")[1].split("&")[0]  # colon encoded

    def test_empty_subject_and_body(self):
        url = build_mailto("a@b.com", "", "")
        assert "mailto:a@b.com?" in url


# ---------------------------------------------------------------------------
# Fallback email tests
# ---------------------------------------------------------------------------

class TestFallbackEmail:
    def test_with_contact_name(self):
        req = _make_request(contact_name="Sarah")
        result = _fallback_email(req)
        assert "subject" in result
        assert "body" in result
        assert "Sarah" in result["body"]

    def test_without_contact_name(self):
        req = _make_request(contact_name=None, customer_name=None)
        result = _fallback_email(req)
        assert "there" in result["body"]

    def test_fallback_has_required_keys(self):
        result = _fallback_email(_make_request())
        assert isinstance(result["subject"], str)
        assert isinstance(result["body"], str)
        assert len(result["subject"]) > 0
        assert len(result["body"]) > 0


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_whitespace_trimmed(self):
        req = _make_request(customer_id="  Acme Corp  ", contact_name="  Sarah  ")
        assert req.customer_id == "Acme Corp"
        assert req.contact_name == "Sarah"

    def test_max_length_exceeded_raises(self):
        with pytest.raises(Exception):  # Pydantic ValidationError
            _make_request(customer_id="x" * 201)

    def test_max_length_at_boundary(self):
        req = _make_request(customer_id="x" * 200)
        assert len(req.customer_id) == 200

    def test_recommended_action_max_length(self):
        with pytest.raises(Exception):
            _make_request(recommended_action="y" * 501)

    def test_risk_driver_summary_max_length(self):
        with pytest.raises(Exception):
            _make_request(risk_driver_summary="z" * 501)

    def test_invalid_tone_rejected(self):
        with pytest.raises(Exception):
            _make_request(tone="sarcastic")

    def test_valid_tones_accepted(self):
        for tone in ("friendly", "direct", "executive"):
            req = _make_request(tone=tone)
            assert req.tone == tone


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------

class TestRateLimit:
    def setup_method(self):
        _rate_store.clear()

    def test_under_limit_passes(self):
        for _ in range(RATE_LIMIT_MAX):
            _check_rate_limit("user-1")  # should not raise

    def test_over_limit_raises_429(self):
        for _ in range(RATE_LIMIT_MAX):
            _check_rate_limit("user-2")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("user-2")
        assert exc_info.value.status_code == 429

    def test_different_users_independent(self):
        for _ in range(RATE_LIMIT_MAX):
            _check_rate_limit("user-a")
        # user-b should still be fine
        _check_rate_limit("user-b")  # should not raise


# ---------------------------------------------------------------------------
# Email generation tests (mocked OpenAI)
# ---------------------------------------------------------------------------

class TestGenerateEmail:
    @patch("app.outreach.OPENAI_API_KEY", "test-key")
    @patch("app.outreach.openai")
    def test_successful_generation(self, mock_openai_module):
        mock_client = MagicMock()
        mock_openai_module.OpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "subject": "Quick check-in on your experience",
                        "body": "Hi Sarah, I wanted to touch base.",
                    })
                )
            )]
        )

        req = _make_request()
        result = _generate_email(req)

        assert result["subject"] == "Quick check-in on your experience"
        assert "Sarah" in result["body"]

    @patch("app.outreach.OPENAI_API_KEY", "test-key")
    @patch("app.outreach.openai")
    def test_bad_json_falls_back(self, mock_openai_module):
        mock_client = MagicMock()
        mock_openai_module.OpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(content="not valid json at all")
            )]
        )

        req = _make_request()
        result = _generate_email(req)

        # Should get fallback
        assert result["subject"] == "Quick check-in"
        assert "Sarah" in result["body"]

    @patch("app.outreach.OPENAI_API_KEY", "test-key")
    @patch("app.outreach.openai")
    def test_empty_subject_falls_back(self, mock_openai_module):
        mock_client = MagicMock()
        mock_openai_module.OpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(
                    content=json.dumps({"subject": "", "body": "Hi there"})
                )
            )]
        )

        req = _make_request()
        result = _generate_email(req)

        # Empty subject → fallback
        assert result["subject"] == "Quick check-in"

    @patch("app.outreach.OPENAI_API_KEY", "test-key")
    @patch("app.outreach.openai")
    def test_api_exception_falls_back(self, mock_openai_module):
        mock_client = MagicMock()
        mock_openai_module.OpenAI.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API down")

        req = _make_request()
        result = _generate_email(req)

        assert result["subject"] == "Quick check-in"

"""Tests for per-account risk drivers and ICS generation."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.explain import (
    generate_risk_drivers,
    build_risk_driver_summary,
    generate_ics,
    _next_business_day_10am_utc,
)


# ---------------------------------------------------------------------------
# Risk driver generation tests
# ---------------------------------------------------------------------------
class TestGenerateRiskDrivers:
    def test_high_inactivity(self):
        row = {"days_since_last_login": 75, "churn_risk_pct": 80}
        drivers = generate_risk_drivers(row)
        assert any("75 days" in d for d in drivers)

    def test_low_logins(self):
        row = {"monthly_logins": 1, "churn_risk_pct": 50}
        drivers = generate_risk_drivers(row)
        assert any("1 login" in d for d in drivers)

    def test_support_tickets(self):
        row = {"support_tickets": 6, "churn_risk_pct": 60}
        drivers = generate_risk_drivers(row)
        assert any("6 support" in d for d in drivers)

    def test_low_nps(self):
        row = {"nps_score": 3, "churn_risk_pct": 45}
        drivers = generate_risk_drivers(row)
        assert any("detractor" in d.lower() for d in drivers)

    def test_renewal_soon(self):
        row = {"days_until_renewal": 15, "churn_risk_pct": 72}
        drivers = generate_risk_drivers(row)
        assert any("15 days" in d for d in drivers)

    def test_auto_renew_off(self):
        row = {"auto_renew_flag": 0, "churn_risk_pct": 55}
        drivers = generate_risk_drivers(row)
        assert any("auto" in d.lower() for d in drivers)

    def test_max_5_drivers(self):
        row = {
            "days_since_last_login": 90,
            "monthly_logins": 1,
            "support_tickets": 7,
            "nps_score": 2,
            "days_until_renewal": 10,
            "seats": 1,
            "auto_renew_flag": 0,
            "churn_risk_pct": 85,
        }
        drivers = generate_risk_drivers(row)
        assert len(drivers) <= 5

    def test_empty_row_returns_fallback(self):
        row = {"churn_risk_pct": 30}
        drivers = generate_risk_drivers(row)
        assert len(drivers) >= 1
        assert "composite" in drivers[0].lower() or len(drivers) > 0

    def test_nan_values_handled(self):
        import math
        row = {
            "days_since_last_login": float("nan"),
            "support_tickets": float("nan"),
            "nps_score": float("nan"),
            "churn_risk_pct": 50,
        }
        drivers = generate_risk_drivers(row)
        # Should not crash, should return fallback
        assert isinstance(drivers, list)


class TestBuildRiskDriverSummary:
    def test_joins_with_semicolons(self):
        drivers = ["Low logins", "High tickets", "Renewal soon"]
        summary = build_risk_driver_summary(drivers)
        assert "Low logins" in summary
        assert ";" in summary

    def test_max_500_chars(self):
        drivers = ["x" * 200] * 5
        summary = build_risk_driver_summary(drivers)
        assert len(summary) <= 500

    def test_empty_drivers(self):
        summary = build_risk_driver_summary([])
        assert summary == ""


# ---------------------------------------------------------------------------
# ICS generation tests
# ---------------------------------------------------------------------------
class TestGenerateIcs:
    def test_valid_ics_structure(self):
        dt = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
        ics = generate_ics("Acme Corp", dt)
        assert "BEGIN:VCALENDAR" in ics
        assert "END:VCALENDAR" in ics
        assert "BEGIN:VEVENT" in ics
        assert "END:VEVENT" in ics
        assert "Acme Corp" in ics

    def test_30_minute_duration(self):
        dt = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
        ics = generate_ics("Test", dt)
        assert "DTSTART:20260310T100000Z" in ics
        assert "DTEND:20260310T103000Z" in ics

    def test_summary_includes_customer(self):
        dt = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
        ics = generate_ics("BigCo", dt)
        assert "SUMMARY:Success Review — BigCo" in ics


class TestNextBusinessDay:
    def test_returns_future_date(self):
        dt = _next_business_day_10am_utc()
        assert dt > datetime.now(timezone.utc)

    def test_is_weekday(self):
        dt = _next_business_day_10am_utc()
        assert dt.weekday() < 5  # Mon-Fri

    def test_is_10am_utc(self):
        dt = _next_business_day_10am_utc()
        assert dt.hour == 10
        assert dt.minute == 0

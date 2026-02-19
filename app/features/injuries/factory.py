"""Factory for selecting injury provider via INJURY_PROVIDER env var.

Values:
  - "null" (default): NullInjuryProvider — all zeros
  - "scrape": ScrapeInjuryProvider — stub, returns zeros for now
"""
from __future__ import annotations

import os

from .base import InjuryProvider
from .null_provider import NullInjuryProvider


def get_injury_provider() -> InjuryProvider:
    """Return injury provider based on INJURY_PROVIDER env var."""
    provider_name = os.getenv("INJURY_PROVIDER", "null").lower().strip()

    if provider_name == "scrape":
        from .nba_injury_scrape import ScrapeInjuryProvider
        return ScrapeInjuryProvider()

    return NullInjuryProvider()

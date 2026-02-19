"""Stub injury provider — placeholder for future scraping integration.

TODO: Implement actual injury data fetching from a source like:
  - ESPN injury reports
  - Supabase injury_snapshots_nba table
  - Third-party API

For now, falls back to NullInjuryProvider behavior.
"""
from __future__ import annotations

from typing import Dict

from .base import InjuryProvider


class ScrapeInjuryProvider(InjuryProvider):
    """Stub: returns zeros until a real data source is wired up."""

    def get_team_injury_features(self, date: str, team: str) -> Dict[str, float]:
        # TODO: query injury data source for `team` on `date`
        return {
            "injury_count": 0.0,
            "injury_impact": 0.0,
            "star_out": 0.0,
        }

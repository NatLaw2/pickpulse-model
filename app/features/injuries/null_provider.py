"""Null injury provider — returns zeros for all features.

This is the default provider when no injury data source is configured.
"""
from __future__ import annotations

from typing import Dict

from .base import InjuryProvider


class NullInjuryProvider(InjuryProvider):
    """Default: no injury data, all features = 0."""

    def get_team_injury_features(self, date: str, team: str) -> Dict[str, float]:
        return {
            "injury_count": 0.0,
            "injury_impact": 0.0,
            "star_out": 0.0,
        }

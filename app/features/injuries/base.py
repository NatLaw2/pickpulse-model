"""Base interface for injury feature providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class InjuryProvider(ABC):
    """Interface for pluggable injury feature providers.

    Implementations return a dict of numeric features for a given team on a date.
    Default values should be 0 (no injury impact).
    """

    @abstractmethod
    def get_team_injury_features(self, date: str, team: str) -> Dict[str, float]:
        """Return injury features for a team on a specific date.

        Args:
            date: game date in YYYY-MM-DD format
            team: full team name (e.g. "Boston Celtics")

        Returns:
            Dict with keys like:
                injury_count: number of players out
                injury_impact: estimated impact score (0-1)
                star_out: 1 if a top player is out, 0 otherwise
        """
        ...

    def get_game_injury_features(
        self, date: str, home_team: str, away_team: str,
    ) -> Dict[str, float]:
        """Return injury features for both teams.

        Returns dict with home_injury_* and away_injury_* prefixes.
        """
        home = self.get_team_injury_features(date, home_team)
        away = self.get_team_injury_features(date, away_team)
        out: Dict[str, float] = {}
        for k, v in home.items():
            out[f"home_{k}"] = v
        for k, v in away.items():
            out[f"away_{k}"] = v
        return out

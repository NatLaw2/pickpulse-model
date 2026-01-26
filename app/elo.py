import math
from typing import Dict

# Minimal NBA Elo seed. Replace/expand later or load from DB.
NBA_ELO: Dict[str, float] = {
    "Atlanta Hawks": 1500,
    "Boston Celtics": 1600,
    "Brooklyn Nets": 1480,
    "Charlotte Hornets": 1450,
    "Chicago Bulls": 1475,
    "Cleveland Cavaliers": 1550,
    "Dallas Mavericks": 1530,
    "Denver Nuggets": 1580,
    "Detroit Pistons": 1425,
    "Golden State Warriors": 1520,
    "Houston Rockets": 1500,
    "Indiana Pacers": 1500,
    "LA Clippers": 1530,
    "Los Angeles Lakers": 1510,
    "Memphis Grizzlies": 1510,
    "Miami Heat": 1520,
    "Milwaukee Bucks": 1560,
    "Minnesota Timberwolves": 1540,
    "New Orleans Pelicans": 1490,
    "New York Knicks": 1540,
    "Oklahoma City Thunder": 1560,
    "Orlando Magic": 1500,
    "Philadelphia 76ers": 1540,
    "Phoenix Suns": 1540,
    "Portland Trail Blazers": 1450,
    "Sacramento Kings": 1510,
    "San Antonio Spurs": 1460,
    "Toronto Raptors": 1480,
    "Utah Jazz": 1470,
    "Washington Wizards": 1420,
}

def elo_win_prob(elo_a: float, elo_b: float) -> float:
    # standard Elo logistic
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))

def get_team_elo(team_name: str) -> float:
    # default if missing
    return NBA_ELO.get(team_name, 1500.0)

def prob_to_american(p: float) -> int:
    # Convert probability to "fair" American odds (rounded)
    p = min(max(p, 1e-6), 1 - 1e-6)
    if p >= 0.5:
        return int(round(-100 * p / (1 - p)))
    return int(round(100 * (1 - p) / p))

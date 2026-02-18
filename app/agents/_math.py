"""Odds conversion, no-vig normalization, CLV computation.

Reuses formulas from app/model_nba.py and app/calibration/confidence_calibrate.py.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Odds helpers
# ---------------------------------------------------------------------------

def implied_prob(odds: Any) -> float:
    """American odds -> raw implied probability (includes vig)."""
    if odds is None:
        return float("nan")
    odds = float(odds)
    if not math.isfinite(odds) or odds == 0:
        return 0.5
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def normalize_no_vig(p_a: float, p_b: float) -> Tuple[float, float]:
    """Remove vig by normalizing two implied probs to sum to 1."""
    a = p_a if math.isfinite(p_a) else 0.0
    b = p_b if math.isfinite(p_b) else 0.0
    s = a + b
    if s <= 0:
        return 0.5, 0.5
    return a / s, b / s


def american_profit(odds: Any) -> float:
    """Profit per 1 unit risked for American odds (win scenario)."""
    if odds is None:
        return 0.0
    odds = float(odds)
    if not math.isfinite(odds) or odds == 0:
        return 0.0
    if odds < 0:
        return 100.0 / abs(odds)
    return odds / 100.0


def safe_float(x: Any) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except (ValueError, TypeError):
        return None


def safe_int(x: Any) -> Optional[int]:
    f = safe_float(x)
    return int(f) if f is not None and math.isfinite(f) else None


# ---------------------------------------------------------------------------
# CLV computation
# ---------------------------------------------------------------------------

def clv_moneyline(
    locked_ml_home: Any,
    locked_ml_away: Any,
    closing_ml_home: Any,
    closing_ml_away: Any,
    picked_side: str,
) -> Optional[float]:
    """
    CLV for moneyline pick.

    CLV = implied_prob_novig(closing, picked_side) - implied_prob_novig(locked, picked_side)

    Positive = we locked better odds than market closed at.
    (Higher closing no-vig prob means the market moved toward our pick.)
    """
    lh = safe_float(locked_ml_home)
    la = safe_float(locked_ml_away)
    ch = safe_float(closing_ml_home)
    ca = safe_float(closing_ml_away)

    if lh is None or la is None or ch is None or ca is None:
        return None

    p_locked_home, p_locked_away = normalize_no_vig(implied_prob(lh), implied_prob(la))
    p_close_home, p_close_away = normalize_no_vig(implied_prob(ch), implied_prob(ca))

    side = picked_side.strip().lower()
    if side == "home":
        return p_close_home - p_locked_home
    elif side == "away":
        return p_close_away - p_locked_away
    return None


def clv_spread(
    locked_point: Any,
    locked_price: Any,
    closing_point: Any,
    closing_price: Any,
    picked_side: str,
) -> Optional[float]:
    """
    CLV for spread pick.

    Two components:
    1. Point movement: (closing_point - locked_point) — positive if spread moved toward us
       (For home side: more positive closing spread = worse for home. So invert.)
    2. Price comparison: difference in no-vig price probs.

    Simplified: we compare the locked spread vs closing spread.
    If the line moved toward our pick, that's positive CLV.
    """
    lp = safe_float(locked_point)
    lpr = safe_float(locked_price)
    cp = safe_float(closing_point)
    cpr = safe_float(closing_price)

    if lp is None or cp is None:
        return None

    # Point movement CLV: if we picked home -3 and it closed -5, the market
    # moved toward home (we got a better number). CLV = (locked - closing) for
    # the picked side, since more negative closing = market favors us more.
    # Convention: locked_point and closing_point are from the picked side's perspective.
    point_clv = lp - cp  # positive when line moves toward our pick

    # Price component (vig-adjusted probability shift)
    price_clv = 0.0
    if lpr is not None and cpr is not None:
        # Spread prices: -110 both sides is standard. Compare no-vig implied probs.
        p_locked = implied_prob(lpr)
        p_closing = implied_prob(cpr)
        if math.isfinite(p_locked) and math.isfinite(p_closing):
            price_clv = p_closing - p_locked

    # Combine: point movement (scaled to prob-ish units) + price shift
    # 1 point of spread ~ 0.03 probability (rough NBA approximation)
    return point_clv * 0.03 + price_clv


def resolve_side(pick: Dict[str, Any], home_team: str, away_team: str) -> Optional[str]:
    """Map pick's selection_team/side to 'home' or 'away'."""
    sel = (pick.get("selection_team") or pick.get("side") or "").strip().lower()
    home = home_team.strip().lower()
    away = away_team.strip().lower()
    if not sel:
        return None
    if home and (home in sel or sel in home):
        return "home"
    if away and (away in sel or sel in away):
        return "away"
    return None


# ---------------------------------------------------------------------------
# Elo helpers (for strategy tournament)
# ---------------------------------------------------------------------------

def elo_win_prob(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def logloss(y_true: float, y_pred: float) -> float:
    """Single-sample log loss."""
    eps = 1e-15
    p = max(eps, min(1 - eps, y_pred))
    if y_true >= 0.5:
        return -math.log(p)
    return -math.log(1 - p)

from typing import List, Optional, Tuple, Any, Dict
import bisect
import json
import os

from .schema import GameIn, GameRecommendation
from .elo import get_team_elo, elo_win_prob
from .config import settings


# -------------------------
# Odds / probability helpers
# -------------------------

def implied_prob_from_american(odds: int) -> float:
    if odds == 0:
        return 0.5
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)

def normalize_no_vig(p_a: float, p_b: float) -> Tuple[float, float]:
    s = (p_a or 0.0) + (p_b or 0.0)
    if s <= 0:
        return 0.5, 0.5
    return p_a / s, p_b / s

def clamp01(x: float) -> float:
    if x != x:  # NaN
        return 0.5
    return max(0.0, min(1.0, float(x)))

def clamp_int(x: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(x))))

def tier(score: int) -> str:
    if score >= settings.TIER_HIGH:
        return "high"
    if score >= settings.TIER_MED:
        return "medium"
    return "low"


# -------------------------
# Confidence curve loader (Elo fallback)
# -------------------------

_CONF_CACHE: Optional[dict] = None

def _load_conf_curve() -> Optional[dict]:
    global _CONF_CACHE
    if _CONF_CACHE is not None:
        return _CONF_CACHE

    path = getattr(settings, "CONF_CURVE_PATH", "")
    if not path:
        _CONF_CACHE = None
        return None

    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            _CONF_CACHE = None
            return None
        _CONF_CACHE = data
        return data
    except (FileNotFoundError, Exception):
        _CONF_CACHE = None
        return None


def _curve_edge_max(curve: dict, default: float = 0.25) -> float:
    try:
        mx = curve.get("meta", {}).get("edge_max", default)
        mx = float(mx)
        return mx if mx > 0 else default
    except Exception:
        return default


def _lookup_bins(edge: float, bins: List[Dict[str, Any]], edge_max: float) -> float:
    edge = float(max(0.0, min(edge, edge_max)))
    for b in bins:
        lo = float(b.get("lo", 0.0))
        hi = float(b.get("hi", 0.0))
        if lo <= edge < hi:
            return float(b.get("win_rate_iso", 0.5))
    return float(bins[-1].get("win_rate_iso", 0.5)) if bins else 0.5


def good_bet_prob_from_edge(edge: float) -> float:
    curve = _load_conf_curve()
    edge_nn = max(0.0, float(edge))
    if curve:
        edge_max = _curve_edge_max(curve)
        edge_nn = min(edge_nn, edge_max)
        bins = curve.get("bins")
        if isinstance(bins, list) and bins:
            return clamp01(_lookup_bins(edge_nn, bins, edge_max))
    return clamp01(0.50 + edge_nn * 2.0)


# -------------------------
# ML model path (new)
# -------------------------

def _try_ml_reco(game: GameIn) -> Optional[dict]:
    """Try the trained ML probability model. Returns pick dict or None if unavailable."""
    try:
        from .ml.predict import is_available, predict_win_prob
    except ImportError:
        return None

    if not is_available():
        return None

    ml = game.odds.moneyline
    if not ml or ml.home is None or ml.away is None:
        return None

    p_home_mkt = implied_prob_from_american(int(ml.home))
    p_away_mkt = implied_prob_from_american(int(ml.away))
    p_home_nv, p_away_nv = normalize_no_vig(p_home_mkt, p_away_mkt)

    # Get spread if available
    sp_point = 0.0
    if game.odds.spread and game.odds.spread.home and game.odds.spread.home.point is not None:
        sp_point = float(game.odds.spread.home.point)

    # Predict for both sides, pick the higher probability
    p_home = predict_win_prob(
        locked_home_nv=p_home_nv,
        locked_away_nv=p_away_nv,
        spread_home_point=sp_point,
        is_home=1,
    )
    p_away = predict_win_prob(
        locked_home_nv=p_home_nv,
        locked_away_nv=p_away_nv,
        spread_home_point=sp_point,
        is_home=0,
    )

    if p_home is None or p_away is None:
        return None

    # Pick side with higher win probability
    if p_home >= p_away:
        side = "HOME"
        win_prob = p_home
        edge = p_home - p_home_nv
    else:
        side = "AWAY"
        win_prob = p_away
        edge = p_away - p_away_nv

    # Require minimum edge vs market
    if edge < settings.MIN_EDGE_ML:
        return {"status": "no_bet", "reason": f"ML edge {edge:.3f} below threshold {settings.MIN_EDGE_ML}"}

    score = clamp_int(win_prob * 100)

    selection = (
        f"{game.homeTeam.abbreviation or game.homeTeam.name} ML"
        if side == "HOME"
        else f"{game.awayTeam.abbreviation or game.awayTeam.name} ML"
    )

    return {
        "status": "pick",
        "selection": selection,
        "confidence": tier(score),
        "score": score,
        "rationale": [
            f"ML win probability (calibrated): {win_prob:.3f}",
            f"Edge vs market: {edge:.3f}",
            "Logistic regression + isotonic calibration",
        ],
    }


# -------------------------
# Market recommendation logic
# -------------------------

def ml_reco(game: GameIn) -> dict:
    # Try ML model first
    ml_result = _try_ml_reco(game)
    if ml_result is not None:
        return ml_result

    # Elo fallback
    ml = game.odds.moneyline
    if not ml or (ml.home is None and ml.away is None):
        return {"status": "no_bet", "reason": "Moneyline not available"}

    home_elo = get_team_elo(game.homeTeam.name) + settings.HOME_ADV_ELO
    away_elo = get_team_elo(game.awayTeam.name)
    p_home = float(elo_win_prob(home_elo, away_elo))
    p_away = 1.0 - p_home

    p_home_mkt = implied_prob_from_american(int(ml.home)) if ml.home is not None else None
    p_away_mkt = implied_prob_from_american(int(ml.away)) if ml.away is not None else None

    if p_home_mkt is not None and p_away_mkt is not None:
        p_home_nv, p_away_nv = normalize_no_vig(p_home_mkt, p_away_mkt)
    else:
        return {"status": "no_bet", "reason": "Moneyline market missing"}

    edges = [
        ("HOME", p_home - p_home_nv),
        ("AWAY", p_away - p_away_nv),
    ]

    side, edge = max(edges, key=lambda x: x[1])

    if edge < settings.MIN_EDGE_ML:
        return {"status": "no_bet", "reason": "Edge below threshold"}

    gbp = good_bet_prob_from_edge(edge)
    score = clamp_int(gbp * 100)

    selection = (
        f"{game.homeTeam.abbreviation or game.homeTeam.name} ML"
        if side == "HOME"
        else f"{game.awayTeam.abbreviation or game.awayTeam.name} ML"
    )

    return {
        "status": "pick",
        "selection": selection,
        "confidence": tier(score),
        "score": score,
        "rationale": [
            f"Good bet probability (calibrated): {gbp:.3f}",
            f"Estimated edge vs market: {edge:.3f}",
            "Elo prior + calibrated edge → probability (fallback)",
        ],
    }


def spread_reco(game: GameIn) -> dict:
    return {"status": "no_bet", "reason": "Spread model pending calibration"}


def total_reco(game: GameIn) -> dict:
    return {"status": "no_bet", "reason": "Totals model not enabled yet"}


def recommend_nba(games: List[GameIn]) -> dict:
    out = {}
    for g in games:
        out[g.id] = GameRecommendation(
            moneyline=ml_reco(g),
            spread=spread_reco(g),
            total=total_reco(g),
        ).model_dump()
    return out

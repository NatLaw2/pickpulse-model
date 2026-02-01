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
# Confidence curve loader
# -------------------------

_CONF_CACHE: Optional[dict] = None

def _load_conf_curve() -> Optional[dict]:
    """
    Loads artifacts/confidence_curve.json written by confidence_calibrate.

    This runs once per process and caches the result.
    """
    global _CONF_CACHE
    if _CONF_CACHE is not None:
        return _CONF_CACHE

    path = getattr(settings, "CONF_CURVE_PATH", "")
    if not path:
        print("[model] CONF_CURVE_PATH not set")
        _CONF_CACHE = None
        return None

    try:
        with open(path, "r") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            print("[model] confidence curve invalid format")
            _CONF_CACHE = None
            return None

        bins = data.get("bins", [])
        print(f"[model] loaded confidence curve from {path} (bins={len(bins)})")

        _CONF_CACHE = data
        return data

    except FileNotFoundError:
        print(f"[model] confidence curve NOT FOUND at {path}")
        _CONF_CACHE = None
        return None
    except Exception as e:
        print(f"[model] failed to load confidence curve: {e}")
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

    # Conservative fallback
    return clamp01(0.50 + edge_nn * 2.0)


# -------------------------
# Market recommendation logic
# -------------------------

def ml_reco(game: GameIn) -> dict:
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
            "Elo prior + calibrated edge → probability",
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

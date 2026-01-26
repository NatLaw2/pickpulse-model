from typing import List
import math

from .schema import GameIn, GameRecommendation
from .elo import get_team_elo, elo_win_prob
from .config import settings

def implied_prob_from_american(odds: int) -> float:
    if odds == 0:
        return 0.5
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)

def tier(score: int) -> str:
    if score >= settings.TIER_HIGH:
        return "high"
    if score >= settings.TIER_MED:
        return "medium"
    return "low"

def clamp_int(x: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(x))))

def ml_reco(game: GameIn) -> dict:
    ml = game.odds.moneyline
    if not ml or (ml.home is None and ml.away is None):
        return {"status": "no_bet", "reason": "Moneyline not available"}

    home_elo = get_team_elo(game.homeTeam.name) + settings.HOME_ADV_ELO
    away_elo = get_team_elo(game.awayTeam.name)
    p_home = elo_win_prob(home_elo, away_elo)
    p_away = 1 - p_home

    # market implied
    p_home_mkt = implied_prob_from_american(ml.home) if ml.home is not None else None
    p_away_mkt = implied_prob_from_american(ml.away) if ml.away is not None else None

    # pick side with better model-vs-market edge
    edges = []
    if p_home_mkt is not None:
        edges.append(("HOME", p_home - p_home_mkt))
    if p_away_mkt is not None:
        edges.append(("AWAY", p_away - p_away_mkt))

    if not edges:
        return {"status": "no_bet", "reason": "Moneyline market missing"}

    side, edge = max(edges, key=lambda x: x[1])

    if edge < settings.MIN_EDGE_ML:
        return {"status": "no_bet", "reason": f"Edge below threshold ({edge:.3f})", "score": clamp_int(50 + edge*800)}

    # score: base 60 + edge scaled + model certainty factor (distance from 50%)
    certainty = abs((p_home if side == "HOME" else p_away) - 0.5)
    score = clamp_int(60 + edge * 900 + certainty * 80)

    selection = f"{game.homeTeam.abbreviation or game.homeTeam.name} ML" if side == "HOME" else f"{game.awayTeam.abbreviation or game.awayTeam.name} ML"

    rationale = [
        f"Model win prob: {p_home:.3f} (home), {p_away:.3f} (away)",
        f"Market implied: {p_home_mkt:.3f} (home), {p_away_mkt:.3f} (away)" if (p_home_mkt is not None and p_away_mkt is not None) else "Market implied probability available",
        f"Estimated edge: {edge:.3f}",
        "Elo prior + home advantage applied",
    ]

    return {"status": "pick", "selection": selection, "confidence": tier(score), "rationale": rationale[:5], "score": score}

def spread_reco(game: GameIn) -> dict:
    sp = game.odds.spread
    if not sp or (sp.home is None and sp.away is None):
        return {"status": "no_bet", "reason": "Spread not available"}

    # Margin proxy from Elo diff (rough; calibrate later)
    home_elo = get_team_elo(game.homeTeam.name) + settings.HOME_ADV_ELO
    away_elo = get_team_elo(game.awayTeam.name)

    # heuristic: 25 Elo ≈ 1 point (coarse NBA proxy)
    elo_diff = home_elo - away_elo
    pred_margin_home = elo_diff / 25.0  # predicted home margin

    # Need a market line to compare to
    home_line = sp.home.point if sp.home and sp.home.point is not None else None
    away_line = sp.away.point if sp.away and sp.away.point is not None else None

    if home_line is None and away_line is None:
        return {"status": "no_bet", "reason": "Spread line missing"}

    # Lines are typically symmetric: home_line = -away_line
    line_home = home_line if home_line is not None else (-away_line)

    # edge in points: predicted - market (positive means home should be more favored than market)
    edge_pts_home = pred_margin_home - (-line_home)  # careful: if home_line is -3, market expects home +3 margin
    # Actually market spread home_line is usually negative when home is favored.
    # Expected home margin per market is -home_line. So compare pred_margin_home vs (-home_line).
    edge_pts_home = pred_margin_home - (-line_home)

    # Choose side
    if edge_pts_home >= 0:
        # home value
        best_edge = edge_pts_home
        side = "HOME"
        selection = f"{game.homeTeam.abbreviation or game.homeTeam.name} {line_home:+.1f}"
    else:
        best_edge = -edge_pts_home
        side = "AWAY"
        # away line usually +X
        away_point = away_line if away_line is not None else (-(line_home))
        selection = f"{game.awayTeam.abbreviation or game.awayTeam.name} {away_point:+.1f}"

    if best_edge < settings.MIN_EDGE_SPREAD:
        return {"status": "no_bet", "reason": f"Edge below threshold ({best_edge:.2f} pts)", "score": clamp_int(50 + best_edge*10)}

    score = clamp_int(60 + best_edge * 8)
    rationale = [
        f"Predicted home margin (Elo proxy): {pred_margin_home:.2f}",
        f"Market expected home margin: {-line_home:.2f}",
        f"Edge estimate: {best_edge:.2f} pts",
        "Elo margin proxy (will be calibrated with historical data)",
    ]

    return {"status": "pick", "selection": selection, "confidence": tier(score), "rationale": rationale[:5], "score": score}

def total_reco(game: GameIn) -> dict:
    # Totals require pace/off/def features (we’ll add next).
    # For now we return no_bet, which is allowed by your rules.
    return {"status": "no_bet", "reason": "Totals model not enabled yet (pace/efficiency pending)"}

def recommend_nba(games: List[GameIn]) -> dict:
    out = {}
    for g in games:
        out[g.id] = GameRecommendation(
            moneyline=ml_reco(g),
            spread=spread_reco(g),
            total=total_reco(g),
        ).model_dump()
    return out

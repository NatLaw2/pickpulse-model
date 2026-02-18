"""Agent 2: Strategy Tournament — parameter variant search against production data.

Generates K/HFA/MIN_EDGE variants, replays locked_picks through walk-forward Elo,
re-grades against game_results, and scores by logloss + mean CLV + ROI.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from itertools import product
from typing import Any, Dict, List, Optional, Tuple

from ._supabase import (
    fetch_locked_picks,
    fetch_game_results,
    fetch_closing_lines,
    since_date,
)
from ._math import (
    elo_win_prob,
    implied_prob,
    normalize_no_vig,
    clv_moneyline,
    american_profit,
    logloss,
    safe_float,
    safe_int,
)

# Elo seeds (same as app/elo.py)
from ..elo import NBA_ELO

# ---------------------------------------------------------------------------
# Variant grid
# ---------------------------------------------------------------------------

K_VALUES = [8, 10, 12]
HFA_VALUES = [35, 40, 45, 50]
MIN_EDGE_VALUES = [0.02, 0.03, 0.04]


def _generate_variants() -> List[Dict[str, Any]]:
    variants = []
    for k, hfa, me in product(K_VALUES, HFA_VALUES, MIN_EDGE_VALUES):
        variants.append({"K": k, "HFA": hfa, "MIN_EDGE": me})
    return variants


# ---------------------------------------------------------------------------
# Walk-forward Elo replay
# ---------------------------------------------------------------------------

def _replay_variant(
    variant: Dict[str, Any],
    locked: List[Dict[str, Any]],
    games: Dict[str, Dict[str, Any]],
    closing: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Replay locked picks through Elo with variant params, grade, and score."""
    k = variant["K"]
    hfa = variant["HFA"]
    min_edge = variant["MIN_EDGE"]

    # Sort locked picks by game start time for walk-forward
    timed = []
    for lp in locked:
        start = lp.get("game_start_time") or lp.get("run_date") or ""
        timed.append((start, lp))
    timed.sort(key=lambda x: x[0])

    ratings: Dict[str, float] = {team: elo for team, elo in NBA_ELO.items()}
    init_elo = 1500.0

    results_list: List[Dict[str, Any]] = []
    logloss_vals: List[float] = []
    clv_vals: List[float] = []
    units_total = 0.0
    n_bets = 0
    n_wins = 0
    n_losses = 0

    for _, lp in timed:
        eid = str(lp.get("event_id", ""))
        game = games.get(eid)
        if not game:
            continue

        home_team = (lp.get("home_team") or "").strip()
        away_team = (lp.get("away_team") or "").strip()
        if not home_team or not away_team:
            continue

        # Game result
        hs = safe_float(game.get("home_score"))
        as_ = safe_float(game.get("away_score"))
        if hs is None or as_ is None:
            continue

        home_won = 1 if hs > as_ else 0
        market = lp.get("market", "")

        # Only replay moneyline (spread model not calibrated yet)
        if market != "moneyline":
            continue

        # Elo prediction with variant params
        home_elo = ratings.get(home_team, init_elo) + hfa
        away_elo = ratings.get(away_team, init_elo)
        p_home_elo = elo_win_prob(home_elo, away_elo)
        p_away_elo = 1.0 - p_home_elo

        # Market no-vig from locked odds
        lh = safe_float(lp.get("locked_ml_home"))
        la = safe_float(lp.get("locked_ml_away"))
        if lh is None or la is None:
            # Update Elo anyway
            change = k * (home_won - p_home_elo)
            ratings[home_team] = ratings.get(home_team, init_elo) + change
            ratings[away_team] = ratings.get(away_team, init_elo) - change
            continue

        p_home_nv, p_away_nv = normalize_no_vig(implied_prob(lh), implied_prob(la))

        # Edge
        edge_home = p_home_elo - p_home_nv
        edge_away = p_away_elo - p_away_nv

        if edge_home >= edge_away:
            best_side = "home"
            edge = edge_home
            p_model = p_home_elo
            bet_won = home_won
            odds = int(lh)
        else:
            best_side = "away"
            edge = edge_away
            p_model = p_away_elo
            bet_won = 1 - home_won
            odds = int(la)

        # Check if this variant would have picked this game
        would_pick = edge >= min_edge

        if would_pick:
            # Log loss
            ll = logloss(float(bet_won), p_model)
            logloss_vals.append(ll)

            # Units
            if bet_won:
                u = american_profit(odds)
                n_wins += 1
            else:
                u = -1.0
                n_losses += 1
            units_total += u
            n_bets += 1

            # CLV (closing vs locked)
            closing_lines = closing.get(eid, [])
            closing_ml_home = None
            closing_ml_away = None
            home_lower = home_team.lower()
            away_lower = away_team.lower()
            for cl in closing_lines:
                name = (cl.get("outcome_name") or "").strip().lower()
                if cl.get("market") == "h2h":
                    if home_lower and name == home_lower:
                        closing_ml_home = cl.get("price")
                    elif away_lower and name == away_lower:
                        closing_ml_away = cl.get("price")

            clv = clv_moneyline(lh, la, closing_ml_home, closing_ml_away, best_side)
            if clv is not None:
                clv_vals.append(clv)

        # Update Elo (always, walk-forward)
        change = k * (home_won - p_home_elo)
        ratings[home_team] = ratings.get(home_team, init_elo) + change
        ratings[away_team] = ratings.get(away_team, init_elo) - change

    # Score
    mean_ll = sum(logloss_vals) / len(logloss_vals) if logloss_vals else float("inf")
    mean_clv = sum(clv_vals) / len(clv_vals) if clv_vals else 0.0
    pct_pos_clv = (sum(1 for c in clv_vals if c > 0) / len(clv_vals) * 100) if clv_vals else 0.0
    roi = (units_total / n_bets * 100) if n_bets else 0.0

    return {
        **variant,
        "n_bets": n_bets,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_pct": round(n_wins / n_bets * 100, 1) if n_bets else None,
        "units": round(units_total, 3),
        "roi_pct": round(roi, 2),
        "logloss": round(mean_ll, 5),
        "mean_clv": round(mean_clv, 5),
        "pct_positive_clv": round(pct_pos_clv, 1),
    }


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(
    days: int = 180,
    features_data: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run strategy tournament over the last N days of production data."""
    since = since_date(days)
    print(f"[tournament] Fetching data since {since}...")

    locked = fetch_locked_picks(since)
    print(f"[tournament] Locked picks: {len(locked)}")

    games = fetch_game_results()
    print(f"[tournament] Game results: {len(games)}")

    closing = fetch_closing_lines()
    print(f"[tournament] Closing line events: {len(closing)}")

    variants = _generate_variants()
    print(f"[tournament] Testing {len(variants)} variants...")

    results: List[Dict[str, Any]] = []
    for i, v in enumerate(variants):
        res = _replay_variant(v, locked, games, closing)
        results.append(res)
        if (i + 1) % 10 == 0:
            print(f"[tournament] Completed {i+1}/{len(variants)} variants")

    # Rank: primary by logloss (lower better), tiebreak by mean CLV (higher better)
    results.sort(key=lambda r: (r["logloss"], -r.get("mean_clv", 0)))

    # Current champion params for comparison
    champion = {"K": 10, "HFA": 40, "MIN_EDGE": 0.03}
    champion_result = None
    for r in results:
        if r["K"] == champion["K"] and r["HFA"] == champion["HFA"] and r["MIN_EDGE"] == champion["MIN_EDGE"]:
            champion_result = r
            break

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "n_variants": len(variants),
        "n_locked_picks": len(locked),
        "champion": champion_result,
        "top_5": results[:5],
        "all_results": results,
    }

    return report

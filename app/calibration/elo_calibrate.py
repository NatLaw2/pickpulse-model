# app/calibration/elo_calibrate.py
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Tuple, List, Optional

import pandas as pd


def elo_win_prob(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def clamp_prob(p: float) -> float:
    return max(1e-6, min(1 - 1e-6, p))


def log_loss(y: int, p: float) -> float:
    p = clamp_prob(p)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def brier(y: int, p: float) -> float:
    return (y - p) ** 2


@dataclass
class EloParams:
    k: float
    home_adv_elo: float
    init_elo: float = 1500.0


@dataclass
class EvalResult:
    params: EloParams
    seasons_train: List[int]
    seasons_val: List[int]
    n: int
    logloss: float
    brier: float


def run_elo_backtest(
    df: pd.DataFrame,
    params: EloParams,
    train_seasons: List[int],
    val_seasons: List[int],
) -> Tuple[float, float, int]:
    """
    Train Elo sequentially through train seasons (updating ratings),
    then continue into val seasons and compute metrics on val games.

    Walk-forward realism:
    - We update ratings through BOTH train and val games
    - But only SCORE on val games
    """
    ratings: Dict[str, float] = {}
    k = params.k
    hfa = params.home_adv_elo

    def get_rating(team: str) -> float:
        return ratings.get(team, params.init_elo)

    total_ll = 0.0
    total_br = 0.0
    n = 0

    # Ensure chronological order
    df = df.copy()
    df["date_dt"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date_dt"]).reset_index(drop=True)

    target_seasons = set(train_seasons + val_seasons)

    for _, row in df.iterrows():
        season = int(row["season"])
        if season not in target_seasons:
            continue

        home = row["home_team"]
        away = row["away_team"]
        home_pts = int(row["home_pts"])
        away_pts = int(row["away_pts"])

        home_won = 1 if home_pts > away_pts else 0

        home_elo = get_rating(home) + hfa
        away_elo = get_rating(away)

        p_home = elo_win_prob(home_elo, away_elo)

        # Score only on validation seasons
        if season in val_seasons:
            total_ll += log_loss(home_won, p_home)
            total_br += brier(home_won, p_home)
            n += 1

        # Always update Elo during both train + val
        expected = p_home
        actual = float(home_won)
        change = k * (actual - expected)

        ratings[home] = get_rating(home) + change
        ratings[away] = get_rating(away) - change

    if n == 0:
        return float("inf"), float("inf"), 0

    return total_ll / n, total_br / n, n


def parse_int_list(s: str) -> List[int]:
    """
    Accepts:
      "2020,2021,2022"
      "2020-2024"
      "2020-2022,2024,2025"
    """
    s = (s or "").strip()
    if not s:
        return []
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out: List[int] = []
    for p in parts:
        if "-" in p:
            a, b = p.split("-", 1)
            a, b = int(a.strip()), int(b.strip())
            lo, hi = min(a, b), max(a, b)
            out.extend(list(range(lo, hi + 1)))
        else:
            out.append(int(p))
    return sorted(list(dict.fromkeys(out)))


def grid_search(
    df: pd.DataFrame,
    train_seasons: List[int],
    val_seasons: List[int],
    k_values: List[float],
    hfa_values: List[float],
    init_elo: float = 1500.0,
    verbose: bool = True,
) -> EvalResult:
    if not train_seasons or not val_seasons:
        raise RuntimeError("train_seasons and val_seasons must be non-empty.")

    best: Optional[EvalResult] = None
    eps = 1e-12  # tie-break stability

    for k in k_values:
        for hfa in hfa_values:
            params = EloParams(k=float(k), home_adv_elo=float(hfa), init_elo=float(init_elo))
            ll, br, n = run_elo_backtest(df, params, train_seasons=train_seasons, val_seasons=val_seasons)

            res = EvalResult(
                params=params,
                seasons_train=train_seasons,
                seasons_val=val_seasons,
                n=n,
                logloss=ll,
                brier=br,
            )

            if verbose:
                print(f"[grid] K={k:>5} HFA={hfa:>5}  n={n:<4}  logloss={ll:.4f}  brier={br:.4f}")

            if best is None:
                best = res
            else:
                # Primary: logloss. Secondary: brier.
                if (res.logloss + eps < best.logloss) or (
                    abs(res.logloss - best.logloss) <= eps and (res.brier + eps < best.brier)
                ):
                    best = res

    assert best is not None

    print("\n=== BEST ===")
    print(f"Train seasons: {best.seasons_train}")
    print(f"Val seasons:   {best.seasons_val}")
    print(f"n={best.n} logloss={best.logloss:.4f} brier={best.brier:.4f}")
    print(f"K={best.params.k} HOME_ADV_ELO={best.params.home_adv_elo}")
    print("\nPaste into Render env:")
    print(f"ELO_K={best.params.k}")
    print(f"HOME_ADV_ELO={best.params.home_adv_elo}")

    return best


def write_artifact(best: EvalResult, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "objective": {"primary": "logloss", "secondary": "brier"},
        "train_seasons": best.seasons_train,
        "val_seasons": best.seasons_val,
        "n_val": best.n,
        "metrics": {"logloss": best.logloss, "brier": best.brier},
        "params": asdict(best.params),
        "env_recommended": {
            "ELO_K": str(best.params.k),
            "HOME_ADV_ELO": str(best.params.home_adv_elo),
        },
    }

    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[artifact] wrote -> {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Calibrate Elo params using walk-forward validation.")
    ap.add_argument("--data", default="data/nba_games.csv", help="Path to NBA games CSV.")
    ap.add_argument("--train", default="", help='Train seasons, e.g. "2020-2024" or "2020,2021,2022,2023,2024".')
    ap.add_argument("--val", default="", help='Val seasons, e.g. "2025" or "2025-2026".')
    ap.add_argument("--k", default="10,15,20,25,30,35,40", help='K grid, e.g. "10,15,20".')
    ap.add_argument("--hfa", default="40,50,60,65,70,75,80", help='HFA grid, e.g. "40,50,60".')
    ap.add_argument("--init", type=float, default=1500.0, help="Initial Elo for unseen teams.")
    ap.add_argument("--artifact", default="artifacts/elo_params.json", help="Where to write the best params JSON.")
    args = ap.parse_args()

    df = pd.read_csv(args.data)

    seasons = sorted(df["season"].unique().tolist())
    if len(seasons) < 2:
        raise RuntimeError("Need at least 2 seasons to calibrate.")

    train_seasons = parse_int_list(args.train)
    val_seasons = parse_int_list(args.val)

    # If user didn’t pass seasons, default to: train = all but last, val = last
    if not train_seasons or not val_seasons:
        val_season = int(seasons[-1])
        train_seasons = [int(s) for s in seasons if int(s) != val_season]
        val_seasons = [val_season]

    k_values = [float(x.strip()) for x in args.k.split(",") if x.strip()]
    hfa_values = [float(x.strip()) for x in args.hfa.split(",") if x.strip()]

    best = grid_search(
        df,
        train_seasons=train_seasons,
        val_seasons=val_seasons,
        k_values=k_values,
        hfa_values=hfa_values,
        init_elo=args.init,
        verbose=True,
    )

    write_artifact(best, args.artifact)


if __name__ == "__main__":
    main()

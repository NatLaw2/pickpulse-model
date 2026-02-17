# app/calibration/confidence_calibrate.py
from __future__ import annotations

import bisect
import json
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd

# ----------------------------
# Elo helpers (standalone)
# ----------------------------
def elo_win_prob(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))

def clamp_prob(p: float) -> float:
    return max(1e-6, min(1 - 1e-6, float(p)))

def implied_prob_from_american(odds: float) -> float:
    if odds is None or (isinstance(odds, float) and math.isnan(odds)):
        return float("nan")
    odds = float(odds)
    if odds == 0:
        return 0.5
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)

def normalize_no_vig(p_home: float, p_away: float) -> Tuple[float, float]:
    p_home = float(p_home)
    p_away = float(p_away)
    s = p_home + p_away
    if not math.isfinite(s) or s <= 0:
        return 0.5, 0.5
    return p_home / s, p_away / s


# ----------------------------
# Team Elo seeds (copied from your elo.py)
# Calibration-only seed; runtime Elo lives elsewhere
# ----------------------------
NBA_ELO_SEED: Dict[str, float] = {
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

def get_seed(team: str, init_elo: float = 1500.0) -> float:
    return float(NBA_ELO_SEED.get(team, init_elo))


# ----------------------------
# Config via env
# ----------------------------
ELO_K = float(os.getenv("ELO_K", "10"))
HOME_ADV_ELO = float(os.getenv("HOME_ADV_ELO", "40"))
INIT_ELO = float(os.getenv("ELO_INIT", "1500"))

# For calibration we usually keep EDGE_MIN=0 so we learn full curve from 0+
EDGE_MIN = float(os.getenv("EDGE_MIN", "0.00"))
EDGE_MAX = float(os.getenv("EDGE_MAX", "0.25"))

# Reporting bins (NOT used for fitting)
N_BINS = int(os.getenv("CONF_BINS", "18"))
MIN_BIN_N = int(os.getenv("CONF_MIN_BIN_N", "10"))

TRAIN_SEASONS = os.getenv("CONF_TRAIN_SEASONS", "2020,2021,2022,2023,2024").strip()
VAL_SEASONS = os.getenv("CONF_VAL_SEASONS", "2025").strip()

OUT_PATH = os.getenv("CONF_OUT", "artifacts/confidence_curve.json").strip()
IN_CSV = os.getenv("CONF_IN", "data/nba_calibration_ml.csv").strip()


def parse_seasons(s: str) -> List[int]:
    out: List[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out


# ----------------------------
# Isotonic Regression (PAVA) on individual samples
# ----------------------------
@dataclass
class IsoBlock:
    y: float
    w: float
    x_min: float
    x_max: float

def isotonic_fit_samples(x: List[float], y: List[int], w: List[float] | None = None) -> List[IsoBlock]:
    """
    Fit monotone non-decreasing function yhat(x) using PAVA on samples (x_i, y_i).
    Returns blocks with constant fitted probability over x ranges.

    This is the correct approach vs bin-first (avoids flatline from empty bins).
    """
    if w is None:
        w = [1.0] * len(x)

    # sort by x
    order = sorted(range(len(x)), key=lambda i: x[i])
    xs = [float(x[i]) for i in order]
    ys = [float(y[i]) for i in order]
    ws = [float(w[i]) for i in order]

    blocks: List[IsoBlock] = []
    for xi, yi, wi in zip(xs, ys, ws):
        yi = clamp_prob(yi)  # y is 0/1; clamp harmless
        blocks.append(IsoBlock(y=yi, w=wi, x_min=xi, x_max=xi))

        # PAVA merge if monotonicity violated
        while len(blocks) >= 2 and blocks[-2].y > blocks[-1].y:
            b2 = blocks.pop()
            b1 = blocks.pop()
            tw = b1.w + b2.w
            avg = (b1.y * b1.w + b2.y * b2.w) / tw if tw > 0 else (b1.y + b2.y) / 2.0
            blocks.append(IsoBlock(
                y=clamp_prob(avg),
                w=tw,
                x_min=b1.x_min,
                x_max=b2.x_max,
            ))

    return blocks


# ----------------------------
# Build training/validation rows
# ----------------------------
def build_dataset_rows(
    df: pd.DataFrame,
    seasons_train: List[int],
    seasons_val: List[int],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Walk-forward Elo + market no-vig. We choose the side with larger edge (home or away).
    Output columns:
      - season, date, home_team, away_team
      - home_win (0/1)
      - p_home_elo, p_home_nv
      - bet_side ('HOME'|'AWAY')
      - edge (>=0 clipped)
      - bet_won (0/1)  <-- IMPORTANT label for calibration
    """
    use = df.copy()
    use = use[use["match_status"] == "matched"].copy()
    use = use.dropna(subset=["home_team", "away_team", "home_win", "p_home_nv", "p_away_nv"]).copy()

    use["date_dt"] = pd.to_datetime(use["date"], errors="coerce")
    use = use.dropna(subset=["date_dt"]).sort_values(["date_dt"]).reset_index(drop=True)

    ratings: Dict[str, float] = {}

    def get_rating(team: str) -> float:
        return float(ratings.get(team, get_seed(team, INIT_ELO)))

    rows = []

    for _, r in use.iterrows():
        season = int(r["season"])
        if season not in (seasons_train + seasons_val):
            continue

        home = str(r["home_team"])
        away = str(r["away_team"])
        home_win = int(r["home_win"])

        # market no-vig probs from file
        p_home_nv = float(r["p_home_nv"])
        p_away_nv = float(r["p_away_nv"])

        # elo prob (walk-forward)
        home_elo = get_rating(home) + HOME_ADV_ELO
        away_elo = get_rating(away)
        p_home_elo = float(elo_win_prob(home_elo, away_elo))
        p_away_elo = 1.0 - p_home_elo

        # compute both edges explicitly (avoid algebra mistakes)
        edge_home = p_home_elo - p_home_nv
        edge_away = p_away_elo - p_away_nv

        if edge_home >= edge_away:
            bet_side = "HOME"
            edge = edge_home
            bet_won = home_win
        else:
            bet_side = "AWAY"
            edge = edge_away
            bet_won = 1 - home_win

        # only keep positive edge signal; clip tails
        edge = float(max(0.0, min(edge, EDGE_MAX)))

        rows.append({
            "season": season,
            "date": str(r["date"]),
            "home_team": home,
            "away_team": away,
            "home_win": home_win,
            "p_home_elo": p_home_elo,
            "p_home_nv": p_home_nv,
            "bet_side": bet_side,
            "edge": edge,
            "bet_won": int(bet_won),
        })

        # update Elo ratings every game (walk-forward realism)
        expected = p_home_elo
        actual = home_win
        change = ELO_K * (actual - expected)
        ratings[home] = get_rating(home) + change
        ratings[away] = get_rating(away) - change

    out = pd.DataFrame(rows)

    train_rows = out[out["season"].isin(seasons_train)].copy()
    val_rows = out[out["season"].isin(seasons_val)].copy()
    return train_rows, val_rows


# ----------------------------
# Curve building + evaluation
# ----------------------------
def blocks_to_knots(blocks: List[IsoBlock]) -> List[Dict]:
    """
    Convert isotonic blocks into knot representation for fast runtime lookup.
    Each knot is {x_max, p}. For edge <= x_max, p is block p (step function).
    """
    knots = []
    for b in blocks:
        knots.append({
            "x_max": float(b.x_max),
            "p": float(clamp_prob(b.y)),
            "n": int(round(b.w)),
        })
    # ensure increasing x_max
    knots.sort(key=lambda k: k["x_max"])
    return knots

def lookup_knots(knots: List[Dict], edge: float) -> float:
    edge = float(edge)
    xs = [k["x_max"] for k in knots]
    i = bisect.bisect_left(xs, edge)
    if i < len(knots):
        return float(knots[i]["p"])
    return float(knots[-1]["p"]) if knots else 0.5

def build_reporting_bins(train_rows: pd.DataFrame, knots: List[Dict], n_bins: int, edge_max: float, min_bin_n: int) -> List[Dict]:
    """
    Reporting-only bins for humans. We evaluate:
      - win_rate_raw = mean(bet_won) in bin
      - win_rate_iso = mean(lookup(edge)) in bin (smoothed)
    """
    d = train_rows.copy()
    d = d[d["edge"] >= EDGE_MIN].copy()
    d["edge"] = d["edge"].clip(lower=0.0, upper=edge_max)

    n_bins = max(6, int(n_bins))
    step = float(edge_max) / n_bins

    out = []
    lo = 0.0
    for i in range(n_bins):
        hi = (i + 1) * step
        m = (d["edge"] >= lo) & (d["edge"] < hi) if i < n_bins - 1 else (d["edge"] >= lo) & (d["edge"] <= hi)
        chunk = d[m]
        n = int(len(chunk))

        if n >= max(1, min_bin_n):
            win_rate_raw = float(chunk["bet_won"].mean())
        elif n > 0:
            win_rate_raw = float(chunk["bet_won"].mean())
        else:
            win_rate_raw = None  # important: don't invent fake signal

        # isotonic value evaluated at each sample, averaged (for reporting)
        if n > 0:
            preds = [lookup_knots(knots, float(e)) for e in chunk["edge"].tolist()]
            win_rate_iso = float(sum(preds) / len(preds))
        else:
            # use midpoint evaluation for empty bins
            mid = (lo + hi) / 2.0
            win_rate_iso = float(lookup_knots(knots, mid))

        out.append({
            "lo": float(lo),
            "hi": float(hi),
            "n": n,
            "win_rate_raw": None if win_rate_raw is None else float(clamp_prob(win_rate_raw)),
            "win_rate_iso": float(clamp_prob(win_rate_iso)),
        })
        lo = hi

    return out

def eval_on_val(val_rows: pd.DataFrame, knots: List[Dict], edge_max: float) -> Dict:
    if len(val_rows) == 0:
        return {"rows_val": 0}

    d = val_rows.copy()
    d["edge"] = d["edge"].clip(lower=0.0, upper=edge_max)
    d["p_conf"] = d["edge"].apply(lambda e: lookup_knots(knots, float(e)))

    eps = 1e-6
    p = d["p_conf"].clip(eps, 1 - eps)
    y = d["bet_won"].astype(int)

    logloss = float((-(y * p.apply(math.log) + (1 - y) * (1 - p).apply(math.log))).mean())
    brier = float(((y - p) ** 2).mean())

    return {
        "rows_val": int(len(d)),
        "logloss": logloss,
        "brier": brier,
        "avg_conf": float(d["p_conf"].mean()),
        "avg_win": float(d["bet_won"].mean()),
    }


def main():
    seasons_train = parse_seasons(TRAIN_SEASONS)
    seasons_val = parse_seasons(VAL_SEASONS)

    df = pd.read_csv(IN_CSV)

    train_rows, val_rows = build_dataset_rows(df, seasons_train=seasons_train, seasons_val=seasons_val)

    # Fit isotonic on individual samples (edge -> P(win))
    train_fit = train_rows.copy()
    train_fit = train_fit[train_fit["edge"] >= EDGE_MIN].copy()
    train_fit["edge"] = train_fit["edge"].clip(lower=0.0, upper=EDGE_MAX)

    x = train_fit["edge"].astype(float).tolist()
    y = train_fit["bet_won"].astype(int).tolist()

    if len(x) < 50:
        raise RuntimeError(f"Not enough training rows to calibrate: {len(x)}")

    blocks = isotonic_fit_samples(x, y)
    knots = blocks_to_knots(blocks)

    curve = {
        "meta": {
            "method": "isotonic_samples",
            "edge_definition": "selected_side_edge = p_model_selected - p_market_novig_selected",
            "label_definition": "bet_won = 1 if selected_side wins else 0",
            "elo_k": ELO_K,
            "home_adv_elo": HOME_ADV_ELO,
            "edge_min": EDGE_MIN,
            "edge_max": EDGE_MAX,
            "rows_train": int(len(train_fit)),
            "bins_reporting": int(N_BINS),
            "min_bin_n": int(MIN_BIN_N),
        },
        "knots": knots,
        "notes": [
            "Calibration is isotonic regression on per-game samples (not bin means).",
            "This produces a stepwise monotone map: edge -> P(win of selected side).",
            "Runtime should compute edge_selected and lookup this curve to get 'Good Bet Probability'.",
            "Reporting bins are derived from the fitted curve and may include empty bins.",
        ],
        "formulas": {
            "p_home_elo": "elo_win_prob(elo_home + HOME_ADV_ELO, elo_away)",
            "p_home_nv": "normalize(implied_prob(home_odds), implied_prob(away_odds)).home",
            "p_away_elo": "1 - p_home_elo",
            "p_away_nv": "1 - p_home_nv (or provided p_away_nv)",
            "edge_home": "p_home_elo - p_home_nv",
            "edge_away": "p_away_elo - p_away_nv",
            "edge_selected": "max(edge_home, edge_away) clipped to [0, EDGE_MAX]",
            "good_bet_probability": "lookup_isotonic_knots(edge_selected)",
        },
    }

    # Reporting bins for human inspection
    curve["bins"] = build_reporting_bins(train_fit, knots, n_bins=N_BINS, edge_max=EDGE_MAX, min_bin_n=MIN_BIN_N)

    # Validation metrics
    curve["val"] = eval_on_val(val_rows, knots, edge_max=EDGE_MAX)

    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(curve, f, indent=2)

    print(f"[confidence] wrote -> {OUT_PATH}")
    print(f"[confidence] train_rows={len(train_rows)} val_rows={len(val_rows)}")
    print(f"[confidence] val_logloss={curve['val'].get('logloss')} val_brier={curve['val'].get('brier')}")


if __name__ == "__main__":
    main()

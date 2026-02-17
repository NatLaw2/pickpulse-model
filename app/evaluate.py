#!/usr/bin/env python3
"""
PickPulse NBA Evaluation Harness

Pulls live pick_snapshots + game_results from Supabase,
grades each pick, and writes a report (JSON + Markdown).

Does NOT change model logic — read-only evaluation.

Usage:
    python -m app.evaluate              # last 30 days (default)
    python -m app.evaluate --days 7
    python -m app.evaluate --days 90

Required env vars:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY   (preferred; falls back to SUPABASE_ANON_KEY)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# ENV + Supabase helpers (mirrors app/backtest pattern)
# ---------------------------------------------------------------------------

def _env(name: str, *fallbacks: str, default: Optional[str] = None) -> str:
    for key in (name, *fallbacks):
        v = os.getenv(key)
        if v and v.strip():
            return v.strip()
    if default is not None:
        return default
    raise RuntimeError(f"Missing env var: {name} (tried fallbacks: {list(fallbacks)})")


_supabase_url: Optional[str] = None
_supabase_key: Optional[str] = None


def _get_sb_config() -> Tuple[str, str]:
    global _supabase_url, _supabase_key
    if _supabase_url is None:
        _supabase_url = _env("SUPABASE_URL")
        _supabase_key = _env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY")
    return _supabase_url, _supabase_key  # type: ignore[return-value]


def _headers() -> Dict[str, str]:
    _, key = _get_sb_config()
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
    }


def _sb_get(path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    base_url, _ = _get_sb_config()
    url = f"{base_url.rstrip('/')}{path}"
    r = requests.get(url, headers=_headers(), params=params, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Supabase GET {r.status_code}: {r.text[:300]}")
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected Supabase response: {str(data)[:300]}")
    return data


def _sb_get_all(path: str, params: Dict[str, str], limit: int = 50_000) -> List[Dict[str, Any]]:
    """Paginated fetch."""
    out: List[Dict[str, Any]] = []
    page_size = 1000
    offset = 0
    while len(out) < limit:
        take = min(page_size, limit - len(out))
        batch = _sb_get(path, {**params, "limit": str(take), "offset": str(offset)})
        out.extend(batch)
        if len(batch) < take:
            break
        offset += take
    return out


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------

PICK_COLS = ",".join([
    "event_id", "sport", "market", "side", "tier",
    "score", "confidence", "run_date", "source",
    "home_team", "away_team", "selection_team",
])

RESULT_COLS = ",".join([
    "event_id", "home_team", "away_team",
    "home_score", "away_score",
    "closing_ml_home", "closing_ml_away",
    "closing_spread_home_point", "closing_spread_home_price",
    "closing_spread_away_point", "closing_spread_away_price",
])


def fetch_picks(since: str) -> List[Dict[str, Any]]:
    """Fetch live NBA pick_snapshots since a run_date."""
    return _sb_get_all("/rest/v1/pick_snapshots", {
        "select": PICK_COLS,
        "sport": "eq.nba",
        "source": "eq.live",
        "run_date": f"gte.{since}",
        "order": "run_date.desc",
    })


def fetch_results() -> Dict[str, Dict[str, Any]]:
    """Fetch all NBA game_results, keyed by event_id."""
    rows = _sb_get_all("/rest/v1/game_results", {
        "select": RESULT_COLS,
        "sport": "eq.nba",
    })
    return {str(r["event_id"]): r for r in rows}


CLOSING_LINE_COLS = ",".join([
    "event_id", "market", "outcome_name", "price", "point", "bookmaker_key",
])


def fetch_closing_lines(book: str = "fanduel") -> Dict[str, List[Dict[str, Any]]]:
    """Fetch closing_lines for NBA from preferred book, keyed by event_id."""
    rows = _sb_get_all("/rest/v1/closing_lines", {
        "select": CLOSING_LINE_COLS,
        "sport": "eq.nba",
        "bookmaker_key": f"eq.{book}",
    })
    by_eid: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_eid.setdefault(str(r["event_id"]), []).append(r)
    return by_eid


def _enrich_result(
    result: Dict[str, Any],
    closing: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Fill null closing odds in game_results from closing_lines table."""
    eid = str(result.get("event_id", ""))
    lines = closing.get(eid, [])
    if not lines:
        return result

    r = dict(result)  # shallow copy
    home = (r.get("home_team") or "").strip().lower()
    away = (r.get("away_team") or "").strip().lower()

    for cl in lines:
        name = (cl.get("outcome_name") or "").strip().lower()
        mkt = cl.get("market", "")
        price = cl.get("price")
        point = cl.get("point")

        is_home = home and name == home
        is_away = away and name == away

        if mkt == "h2h":
            if is_home and r.get("closing_ml_home") is None:
                r["closing_ml_home"] = price
            elif is_away and r.get("closing_ml_away") is None:
                r["closing_ml_away"] = price
        elif mkt == "spreads":
            if is_home and r.get("closing_spread_home_point") is None:
                r["closing_spread_home_point"] = point
                r["closing_spread_home_price"] = price
            elif is_away and r.get("closing_spread_away_point") is None:
                r["closing_spread_away_point"] = point
                r["closing_spread_away_price"] = price

    return r


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def _safe_float(x: Any) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int(x: Any) -> Optional[int]:
    f = _safe_float(x)
    return int(f) if f is not None and math.isfinite(f) else None


def _american_profit(odds: int) -> float:
    if odds == 0:
        return 0.0
    return (100.0 / abs(odds)) if odds < 0 else (odds / 100.0)


def _resolve_side(pick: Dict[str, Any], result: Dict[str, Any]) -> Optional[str]:
    """Map the pick's side/selection_team to 'home' or 'away'."""
    sel = (pick.get("selection_team") or pick.get("side") or "").strip().lower()
    home = (result.get("home_team") or "").strip().lower()
    away = (result.get("away_team") or "").strip().lower()
    if not sel:
        return None
    # direct containment
    if home and home in sel:
        return "home"
    if away and away in sel:
        return "away"
    if home and sel in home:
        return "home"
    if away and sel in away:
        return "away"
    return None


def grade_pick(pick: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Returns a graded record or None if ungraded (missing scores/odds).
    """
    hs = _safe_float(result.get("home_score"))
    as_ = _safe_float(result.get("away_score"))
    if hs is None or as_ is None:
        return None  # game not final

    market = pick.get("market", "")
    side = _resolve_side(pick, result)

    # --- moneyline ---
    if market == "moneyline":
        ml_home = _safe_int(result.get("closing_ml_home"))
        ml_away = _safe_int(result.get("closing_ml_away"))
        if side is None or ml_home is None or ml_away is None:
            return None
        odds = ml_home if side == "home" else ml_away
        picked_won = (hs > as_) if side == "home" else (as_ > hs)
        if hs == as_:
            outcome, units = "push", 0.0
        elif picked_won:
            outcome, units = "win", _american_profit(odds)
        else:
            outcome, units = "loss", -1.0

    # --- spread ---
    elif market == "spread":
        sp = _safe_float(result.get(f"closing_spread_{side}_point" if side else ""))
        sp_price = _safe_int(result.get(f"closing_spread_{side}_price" if side else ""))
        if side is None or sp is None or sp_price is None:
            return None
        adj = (hs + sp) if side == "home" else (as_ + sp)
        opp = as_ if side == "home" else hs
        if abs(adj - opp) < 1e-9:
            outcome, units = "push", 0.0
        elif adj > opp:
            outcome, units = "win", _american_profit(sp_price)
        else:
            outcome, units = "loss", -1.0

    # --- total ---
    elif market == "total":
        # game_results doesn't store closing total lines yet — skip
        return None

    else:
        return None

    return {
        "event_id": pick["event_id"],
        "market": market,
        "tier": pick.get("tier"),
        "side": pick.get("side"),
        "score": pick.get("score"),
        "confidence": pick.get("confidence"),
        "run_date": pick.get("run_date"),
        "outcome": outcome,
        "units": units,
        "closing_odds": odds if market == "moneyline" else sp_price,
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _record(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    wins = sum(1 for r in rows if r["outcome"] == "win")
    losses = sum(1 for r in rows if r["outcome"] == "loss")
    pushes = sum(1 for r in rows if r["outcome"] == "push")
    total_units = sum(r["units"] for r in rows)
    bets = wins + losses  # pushes excluded from denominator
    return {
        "n": len(rows),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_pct": round(wins / bets * 100, 1) if bets else None,
        "units": round(total_units, 3),
        "roi_pct": round(total_units / bets * 100, 2) if bets else None,
    }


def _group_by(rows: List[Dict[str, Any]], key: str) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        k = str(r.get(key, "unknown"))
        groups.setdefault(k, []).append(r)
    return groups


def _calibration_bins(rows: List[Dict[str, Any]], n_bins: int = 5) -> List[Dict[str, Any]]:
    """
    Bin picks by predicted confidence, compare to actual win rate.
    Only includes rows with a usable confidence value.
    """
    usable = [(r["confidence"], 1 if r["outcome"] == "win" else 0)
              for r in rows
              if r["confidence"] is not None and r["outcome"] in ("win", "loss")]
    if not usable:
        return []
    usable.sort(key=lambda t: t[0])

    bins: List[Dict[str, Any]] = []
    chunk = max(1, len(usable) // n_bins)
    for i in range(0, len(usable), chunk):
        sl = usable[i:i + chunk]
        confs = [c for c, _ in sl]
        actuals = [a for _, a in sl]
        bins.append({
            "bin_lo": round(min(confs), 3),
            "bin_hi": round(max(confs), 3),
            "n": len(sl),
            "predicted_avg": round(sum(confs) / len(confs), 3),
            "actual_win_rate": round(sum(actuals) / len(actuals), 3),
        })
    return bins


def build_report(graded: List[Dict[str, Any]], days: int) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "total_graded": len(graded),
    }

    # overall
    report["overall"] = _record(graded)

    # by market
    by_market = _group_by(graded, "market")
    report["by_market"] = {k: _record(v) for k, v in sorted(by_market.items())}

    # by tier
    by_tier = _group_by(graded, "tier")
    report["by_tier"] = {k: _record(v) for k, v in sorted(by_tier.items())}

    # by market × tier
    cross: Dict[str, Any] = {}
    for mkt, mkt_rows in sorted(by_market.items()):
        sub = _group_by(mkt_rows, "tier")
        cross[mkt] = {k: _record(v) for k, v in sorted(sub.items())}
    report["by_market_tier"] = cross

    # calibration (5 bins)
    report["calibration"] = _calibration_bins(graded, n_bins=5)

    return report


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def report_to_markdown(rpt: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# PickPulse NBA Evaluation Report")
    lines.append(f"Generated: {rpt['generated_at']}")
    lines.append(f"Lookback: {rpt['lookback_days']} days")
    lines.append(f"Total graded picks: **{rpt['total_graded']}**")
    lines.append("")

    def _fmt(rec: Dict[str, Any]) -> str:
        wp = f"{rec['win_pct']}%" if rec['win_pct'] is not None else "—"
        roi = f"{rec['roi_pct']}%" if rec['roi_pct'] is not None else "—"
        return (
            f"{rec['wins']}W-{rec['losses']}L"
            f" ({rec['pushes']}P)"
            f" | Win%: {wp}"
            f" | Units: {rec['units']:+.3f}"
            f" | ROI: {roi}"
            f" | N={rec['n']}"
        )

    lines.append("## Overall")
    lines.append(_fmt(rpt["overall"]))
    lines.append("")

    lines.append("## By Market")
    for mkt, rec in rpt["by_market"].items():
        lines.append(f"- **{mkt}**: {_fmt(rec)}")
    lines.append("")

    lines.append("## By Tier")
    for tier, rec in rpt["by_tier"].items():
        lines.append(f"- **{tier}**: {_fmt(rec)}")
    lines.append("")

    lines.append("## By Market × Tier")
    for mkt, subs in rpt["by_market_tier"].items():
        lines.append(f"### {mkt}")
        for tier, rec in subs.items():
            lines.append(f"- **{tier}**: {_fmt(rec)}")
        lines.append("")

    cal = rpt.get("calibration", [])
    if cal:
        lines.append("## Calibration (predicted confidence vs actual win rate)")
        lines.append("| Bin | N | Predicted Avg | Actual Win% |")
        lines.append("|-----|---|--------------|-------------|")
        for b in cal:
            lines.append(
                f"| {b['bin_lo']:.3f}–{b['bin_hi']:.3f} "
                f"| {b['n']} "
                f"| {b['predicted_avg']:.3f} "
                f"| {b['actual_win_rate']:.3f} |"
            )
    else:
        lines.append("## Calibration")
        lines.append("Not enough data for calibration bins.")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PickPulse NBA evaluation harness")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days (default: 30)")
    args = parser.parse_args()

    since = (date.today() - timedelta(days=args.days)).isoformat()
    print(f"Fetching live NBA picks since {since} ({args.days} days)...")

    picks = fetch_picks(since)
    print(f"  pick_snapshots rows: {len(picks)}")

    if not picks:
        print("No picks found. Nothing to evaluate.")
        sys.exit(0)

    results = fetch_results()
    print(f"  game_results rows:   {len(results)}")

    closing = fetch_closing_lines()
    print(f"  closing_lines eids:  {len(closing)}")

    # Enrich game_results with closing_lines odds where missing
    for eid in results:
        results[eid] = _enrich_result(results[eid], closing)

    # Grade
    graded: List[Dict[str, Any]] = []
    ungraded = 0
    for p in picks:
        eid = str(p.get("event_id", ""))
        r = results.get(eid)
        if not r:
            ungraded += 1
            continue
        g = grade_pick(p, r)
        if g is None:
            ungraded += 1
            continue
        graded.append(g)

    print(f"  graded: {len(graded)}  |  ungraded/skipped: {ungraded}")

    if not graded:
        print("No graded picks. Games may not have finished yet.")
        sys.exit(0)

    # Build report
    rpt = build_report(graded, args.days)

    # Print summary
    o = rpt["overall"]
    wp = f"{o['win_pct']}%" if o["win_pct"] is not None else "—"
    roi = f"{o['roi_pct']}%" if o["roi_pct"] is not None else "—"
    print(f"\n{'='*50}")
    print(f"OVERALL:  {o['wins']}W-{o['losses']}L ({o['pushes']}P)  |  Win%: {wp}  |  ROI: {roi}  |  Units: {o['units']:+.3f}  |  N={o['n']}")
    print(f"{'='*50}")

    for mkt, rec in rpt["by_market"].items():
        mwp = f"{rec['win_pct']}%" if rec["win_pct"] is not None else "—"
        mroi = f"{rec['roi_pct']}%" if rec["roi_pct"] is not None else "—"
        print(f"  {mkt:12s}  {rec['wins']}W-{rec['losses']}L  Win%: {mwp}  ROI: {mroi}  N={rec['n']}")

    print()
    for tier, rec in rpt["by_tier"].items():
        twp = f"{rec['win_pct']}%" if rec["win_pct"] is not None else "—"
        troi = f"{rec['roi_pct']}%" if rec["roi_pct"] is not None else "—"
        print(f"  {tier:14s}  {rec['wins']}W-{rec['losses']}L  Win%: {twp}  ROI: {troi}  N={rec['n']}")

    cal = rpt.get("calibration", [])
    if cal:
        print(f"\nCalibration ({len(cal)} bins):")
        for b in cal:
            print(f"  [{b['bin_lo']:.3f}–{b['bin_hi']:.3f}]  N={b['n']:3d}  pred={b['predicted_avg']:.3f}  actual={b['actual_win_rate']:.3f}")

    # Write files
    today = date.today().isoformat()
    os.makedirs("reports", exist_ok=True)
    json_path = f"reports/{today}_nba_eval.json"
    md_path = f"reports/{today}_nba_eval.md"

    with open(json_path, "w") as f:
        json.dump(rpt, f, indent=2)
    print(f"\nWrote: {json_path}")

    with open(md_path, "w") as f:
        f.write(report_to_markdown(rpt))
    print(f"Wrote: {md_path}")


if __name__ == "__main__":
    main()

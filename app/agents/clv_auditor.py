"""Agent 3: CLV Auditor — precise closing-line value computation.

Locked odds:  latest closing_lines snapshot with captured_at <= locked_at
Closing odds: latest closing_lines snapshot with captured_at <= game_start_time
Home/away mapping: uses outcome_name matched against home_team/away_team from
the closing_lines row itself (authoritative for the event).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ._supabase import fetch_locked_picks, fetch_closing_lines, since_date
from ._math import (
    clv_moneyline,
    clv_spread,
    resolve_side,
    safe_float,
)


# ---------------------------------------------------------------------------
# Time-filtered odds extraction from closing_lines snapshots
# ---------------------------------------------------------------------------

def _extract_odds_at(
    lines: List[Dict[str, Any]],
    cutoff_iso: Optional[str],
) -> Dict[str, Any]:
    """Extract ML/spread odds from the latest closing_lines snapshot <= cutoff.

    Returns dict with closing_ml_home, closing_ml_away,
    closing_spread_home_point, etc.  Empty dict if nothing available.
    """
    if not lines or not cutoff_iso:
        return {}

    # Filter to rows with captured_at <= cutoff, then pick the latest group
    eligible = []
    for cl in lines:
        cap = cl.get("captured_at")
        if cap and cap <= cutoff_iso:
            eligible.append(cl)

    if not eligible:
        return {}

    # Sort descending by captured_at so latest snapshot is first
    eligible.sort(key=lambda r: r.get("captured_at", ""), reverse=True)
    latest_ts = eligible[0].get("captured_at", "")

    # Take only rows from that single latest timestamp
    snapshot = [r for r in eligible if r.get("captured_at") == latest_ts]

    # Determine canonical home/away from closing_lines row
    home = ""
    away = ""
    for r in snapshot:
        h = (r.get("home_team") or "").strip()
        a = (r.get("away_team") or "").strip()
        if h:
            home = h
        if a:
            away = a
        if home and away:
            break

    home_lower = home.lower()
    away_lower = away.lower()
    if not home_lower or not away_lower:
        return {}

    out: Dict[str, Any] = {"_home_team": home, "_away_team": away}
    for r in snapshot:
        name = (r.get("outcome_name") or "").strip().lower()
        mkt = r.get("market", "")
        price = r.get("price")
        point = r.get("point")

        is_home = name == home_lower
        is_away = name == away_lower

        if mkt == "h2h":
            if is_home and "ml_home" not in out:
                out["ml_home"] = price
            elif is_away and "ml_away" not in out:
                out["ml_away"] = price
        elif mkt == "spreads":
            if is_home and "spread_home_point" not in out:
                out["spread_home_point"] = point
                out["spread_home_price"] = price
            elif is_away and "spread_away_point" not in out:
                out["spread_away_point"] = point
                out["spread_away_price"] = price

    return out


def _compute_pick_clv(
    pick: Dict[str, Any],
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Compute CLV for a single locked pick.

    Locked odds  = latest closing_lines snapshot with captured_at <= locked_at
                   (falls back to locked_ml_*/locked_spread_* from locked_picks)
    Closing odds = latest closing_lines snapshot with captured_at <= game_start_time
    """
    market = pick.get("market", "")
    locked_at = pick.get("locked_at")
    game_start = pick.get("game_start_time")

    locked_odds = _extract_odds_at(lines, locked_at)
    closing_odds = _extract_odds_at(lines, game_start)

    # Fallback: if no closing_lines snapshot exists at lock time,
    # use the locked_ml_*/locked_spread_* columns stored in locked_picks
    if not locked_odds:
        locked_odds = {
            "ml_home": pick.get("locked_ml_home"),
            "ml_away": pick.get("locked_ml_away"),
            "spread_home_point": pick.get("locked_spread_home_point"),
            "spread_home_price": pick.get("locked_spread_home_price"),
            "spread_away_point": pick.get("locked_spread_away_point"),
            "spread_away_price": pick.get("locked_spread_away_price"),
        }

    if not closing_odds:
        return None

    # Use the canonical home/away from closing_lines for side resolution
    home_team = closing_odds.get("_home_team") or pick.get("home_team", "")
    away_team = closing_odds.get("_away_team") or pick.get("away_team", "")
    side = resolve_side(pick, home_team, away_team)
    if side is None:
        return None

    rec: Dict[str, Any] = {
        "event_id": pick.get("event_id"),
        "market": market,
        "tier": pick.get("tier"),
        "confidence": pick.get("confidence"),
        "side": side,
        "run_date": pick.get("run_date"),
        "home_team": home_team,
        "away_team": away_team,
        "locked_at": locked_at,
        "game_start_time": game_start,
    }

    if market == "moneyline":
        clv = clv_moneyline(
            locked_ml_home=locked_odds.get("ml_home"),
            locked_ml_away=locked_odds.get("ml_away"),
            closing_ml_home=closing_odds.get("ml_home"),
            closing_ml_away=closing_odds.get("ml_away"),
            picked_side=side,
        )
        rec["clv"] = clv
        rec["clv_type"] = "moneyline_novig_prob"
        # Attach raw odds for debug
        rec["locked_ml_home"] = locked_odds.get("ml_home")
        rec["locked_ml_away"] = locked_odds.get("ml_away")
        rec["closing_ml_home"] = closing_odds.get("ml_home")
        rec["closing_ml_away"] = closing_odds.get("ml_away")

    elif market == "spread":
        side_key = "home" if side == "home" else "away"
        clv = clv_spread(
            locked_point=locked_odds.get(f"spread_{side_key}_point"),
            locked_price=locked_odds.get(f"spread_{side_key}_price"),
            closing_point=closing_odds.get(f"spread_{side_key}_point"),
            closing_price=closing_odds.get(f"spread_{side_key}_price"),
            picked_side=side,
        )
        rec["clv"] = clv
        rec["clv_type"] = "spread_composite"
        rec["locked_spread_point"] = locked_odds.get(f"spread_{side_key}_point")
        rec["locked_spread_price"] = locked_odds.get(f"spread_{side_key}_price")
        rec["closing_spread_point"] = closing_odds.get(f"spread_{side_key}_point")
        rec["closing_spread_price"] = closing_odds.get(f"spread_{side_key}_price")

    else:
        return None

    return rec if rec.get("clv") is not None else None


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _aggregate(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    clvs = [p["clv"] for p in picks if p.get("clv") is not None and math.isfinite(p["clv"])]
    if not clvs:
        return {"n": 0}
    clvs_sorted = sorted(clvs)
    n = len(clvs)
    median = clvs_sorted[n // 2] if n % 2 == 1 else (clvs_sorted[n // 2 - 1] + clvs_sorted[n // 2]) / 2
    return {
        "n": n,
        "mean": round(sum(clvs) / n, 5),
        "median": round(median, 5),
        "pct_positive": round(sum(1 for c in clvs if c > 0) / n * 100, 1),
        "min": round(min(clvs), 5),
        "max": round(max(clvs), 5),
    }


def _group_agg(picks: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for p in picks:
        k = str(p.get(key, "unknown"))
        groups.setdefault(k, []).append(p)
    return {k: _aggregate(v) for k, v in sorted(groups.items())}


def _confidence_buckets(picks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {"low": [], "mid": [], "high": []}
    for p in picks:
        conf = safe_float(p.get("confidence"))
        if conf is None:
            buckets["low"].append(p)
        elif conf >= 0.65:
            buckets["high"].append(p)
        elif conf >= 0.50:
            buckets["mid"].append(p)
        else:
            buckets["low"].append(p)
    return {k: _aggregate(v) for k, v in buckets.items() if v}


def _detect_leakage(picks: List[Dict[str, Any]]) -> List[str]:
    flags: List[str] = []
    agg = _aggregate(picks)
    if agg.get("n", 0) < 10:
        return flags

    if agg.get("mean", 0) < -0.01:
        flags.append(f"Overall mean CLV is negative ({agg['mean']:.4f}): systematic leakage")

    if agg.get("pct_positive", 50) < 40:
        flags.append(f"Only {agg['pct_positive']}% of picks have positive CLV")

    by_tier = _group_agg(picks, "tier")
    for tier, stats in by_tier.items():
        if stats.get("n", 0) >= 5 and stats.get("mean", 0) < -0.02:
            flags.append(f"Tier '{tier}' has mean CLV {stats['mean']:.4f} (n={stats['n']})")

    return flags


# ---------------------------------------------------------------------------
# Debug section builder
# ---------------------------------------------------------------------------

def _build_debug(clv_picks: List[Dict[str, Any]], n: int = 5) -> List[Dict[str, Any]]:
    """First N picks with full locked/closing odds detail for verification."""
    debug = []
    for p in clv_picks[:n]:
        entry: Dict[str, Any] = {
            "event_id": p.get("event_id"),
            "market": p.get("market"),
            "side": p.get("side"),
            "locked_at": p.get("locked_at"),
            "game_start_time": p.get("game_start_time"),
            "clv": p.get("clv"),
        }
        if p.get("market") == "moneyline":
            entry["locked_odds"] = {
                "ml_home": p.get("locked_ml_home"),
                "ml_away": p.get("locked_ml_away"),
            }
            entry["closing_odds"] = {
                "ml_home": p.get("closing_ml_home"),
                "ml_away": p.get("closing_ml_away"),
            }
        elif p.get("market") == "spread":
            entry["locked_odds"] = {
                "spread_point": p.get("locked_spread_point"),
                "spread_price": p.get("locked_spread_price"),
            }
            entry["closing_odds"] = {
                "spread_point": p.get("closing_spread_point"),
                "spread_price": p.get("closing_spread_price"),
            }
        debug.append(entry)
    return debug


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(days: int = 180, dry_run: bool = False) -> Dict[str, Any]:
    """Run CLV audit over the last N days of locked picks."""
    since = since_date(days)
    print(f"[clv_auditor] Fetching locked picks since {since}...")
    locked = fetch_locked_picks(since)
    print(f"[clv_auditor] Locked picks: {len(locked)}")

    print("[clv_auditor] Fetching closing lines (with captured_at)...")
    closing = fetch_closing_lines()
    print(f"[clv_auditor] Closing line events: {len(closing)}")

    # Compute per-pick CLV
    clv_picks: List[Dict[str, Any]] = []
    skipped = 0
    for pick in locked:
        eid = str(pick.get("event_id", ""))
        lines = closing.get(eid, [])
        rec = _compute_pick_clv(pick, lines)
        if rec:
            clv_picks.append(rec)
        else:
            skipped += 1

    print(f"[clv_auditor] CLV computed: {len(clv_picks)}, skipped: {skipped}")

    # Debug: show first 5 picks for verification
    debug_picks = _build_debug(clv_picks)
    if debug_picks:
        print(f"[clv_auditor] Debug sample (first {len(debug_picks)} picks):")
        for d in debug_picks:
            print(f"  {d['event_id']} | {d['market']} {d['side']} | "
                  f"locked_at={d['locked_at']} | "
                  f"locked={d.get('locked_odds')} | "
                  f"closing={d.get('closing_odds')} | "
                  f"CLV={d['clv']}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "n_picks": len(clv_picks),
        "n_skipped": skipped,
        "overall": _aggregate(clv_picks),
        "by_market": _group_agg(clv_picks, "market"),
        "by_tier": _group_agg(clv_picks, "tier"),
        "by_confidence_bucket": _confidence_buckets(clv_picks),
        "leakage_flags": _detect_leakage(clv_picks),
        "debug_sample": debug_picks,
        "picks": clv_picks,
    }

    return report

"""Orchestrator — sequences agents, applies champion/challenger gating.

Data flow:
  1. CLV Auditor  -> clv_report
  2. Error Attribution (uses clv_report) -> errors
  3. Feature Discovery (uses clv_report) -> features
  4. Calibration Agent -> calibration
  5. Strategy Tournament (uses features) -> tournament
  6. Gating: shadow report or deploy champion update

Two modes:
  - Shadow (default): writes report, does NOT touch champion config
  - Deploy (--deploy): requires all gating criteria to pass
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import clv_auditor
from . import error_attribution
from . import feature_discovery
from . import calibration_agent
from . import strategy_tournament


# ---------------------------------------------------------------------------
# Deployment gating
# ---------------------------------------------------------------------------

_GATE_MIN_SAMPLE = 200
_GATE_LOGLOSS_IMPROVEMENT_PCT = 2.0  # challenger must improve LL by >= 2%
_GATE_ROI_REGRESSION_MAX = 2.0  # units per 100 bets
_GATE_OVERCONFIDENCE_MAX = 0.62


def _check_gates(
    champion: Optional[Dict[str, Any]],
    challenger: Optional[Dict[str, Any]],
    calibration: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check all deployment gates. Returns {passed: bool, checks: [...]}."""
    checks: List[Dict[str, Any]] = []

    if champion is None or challenger is None:
        return {
            "passed": False,
            "checks": [{"gate": "data", "passed": False, "reason": "Missing champion or challenger data"}],
        }

    # Gate 1: Sample size >= 200 graded picks
    n = challenger.get("n_bets", 0)
    checks.append({
        "gate": "sample_size",
        "passed": n >= _GATE_MIN_SAMPLE,
        "value": n,
        "threshold": _GATE_MIN_SAMPLE,
    })

    # Gate 2: Challenger log-loss improves champion by >= 2%
    ch_ll = champion.get("logloss", float("inf"))
    cl_ll = challenger.get("logloss", float("inf"))
    if ch_ll > 0 and ch_ll != float("inf"):
        ll_improvement_pct = (ch_ll - cl_ll) / ch_ll * 100
    else:
        ll_improvement_pct = 0.0
    checks.append({
        "gate": "logloss_improvement",
        "passed": ll_improvement_pct >= _GATE_LOGLOSS_IMPROVEMENT_PCT,
        "champion_ll": ch_ll,
        "challenger_ll": cl_ll,
        "improvement_pct": round(ll_improvement_pct, 2),
        "threshold_pct": _GATE_LOGLOSS_IMPROVEMENT_PCT,
    })

    # Gate 3: CLV gate — mean CLV > 0 OR pct positive CLV >= 52%
    cl_clv = challenger.get("mean_clv", 0)
    cl_pct = challenger.get("pct_positive_clv", 0)
    clv_passed = cl_clv > 0 or cl_pct >= 52.0
    checks.append({
        "gate": "clv",
        "passed": clv_passed,
        "mean_clv": cl_clv,
        "pct_positive_clv": cl_pct,
        "rule": "mean_clv > 0 OR pct_positive_clv >= 52%",
    })

    # Gate 4: ROI not worse than champion by > 2 units per 100 bets
    ch_roi = champion.get("roi_pct", 0)
    cl_roi = challenger.get("roi_pct", 0)
    roi_regression = ch_roi - cl_roi
    checks.append({
        "gate": "roi_regression",
        "passed": roi_regression <= _GATE_ROI_REGRESSION_MAX,
        "champion_roi": ch_roi,
        "challenger_roi": cl_roi,
        "regression": round(roi_regression, 2),
        "max_allowed": _GATE_ROI_REGRESSION_MAX,
    })

    # Gate 5: Overconfidence — avg predicted confidence <= 0.62
    # unless backed by actual win rate within 3pp
    cl_win_pct = challenger.get("win_pct")
    cl_avg_conf = None
    if calibration and calibration.get("metrics"):
        cl_avg_conf = calibration["metrics"].get("avg_confidence")
    if cl_avg_conf is None:
        # Fall back: estimate from n_wins / n_bets
        n_wins = challenger.get("n_wins", 0)
        n_bets_c = challenger.get("n_bets", 1)
        cl_avg_conf = n_wins / n_bets_c if n_bets_c > 0 else 0.5

    conf_ok = cl_avg_conf <= _GATE_OVERCONFIDENCE_MAX
    if not conf_ok and cl_win_pct is not None:
        # Allow if win rate backs it up (within 3pp)
        conf_ok = abs(cl_avg_conf - cl_win_pct / 100.0) <= 0.03
    checks.append({
        "gate": "overconfidence",
        "passed": conf_ok,
        "avg_confidence": round(cl_avg_conf, 4) if cl_avg_conf else None,
        "threshold": _GATE_OVERCONFIDENCE_MAX,
        "win_pct": cl_win_pct,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"passed": all_passed, "checks": checks}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _build_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Agent Improvement Loop Report")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append(f"Lookback: {report['lookback_days']} days")
    lines.append(f"Mode: {report['mode']}")
    lines.append("")

    # CLV summary
    clv = report.get("clv_auditor", {}).get("overall", {})
    if clv.get("n"):
        lines.append("## CLV Auditor")
        lines.append(f"- Picks analyzed: {clv['n']}")
        lines.append(f"- Mean CLV: {clv.get('mean', 'N/A')}")
        lines.append(f"- Median CLV: {clv.get('median', 'N/A')}")
        lines.append(f"- % Positive: {clv.get('pct_positive', 'N/A')}%")
        leakage = report.get("clv_auditor", {}).get("leakage_flags", [])
        if leakage:
            lines.append("- **Leakage flags:**")
            for f in leakage:
                lines.append(f"  - {f}")
        lines.append("")

    # Error attribution
    errors = report.get("error_attribution", {})
    if errors.get("n_losses"):
        lines.append("## Error Attribution")
        lines.append(f"- Total losses: {errors['n_losses']}")
        for cat, cnt in errors.get("summary", {}).items():
            lines.append(f"  - {cat}: {cnt}")
        recs = errors.get("recommendations", [])
        if recs:
            lines.append("- **Recommendations:**")
            for r in recs:
                lines.append(f"  - {r}")
        lines.append("")

    # Feature discovery
    features = report.get("feature_discovery", {})
    patterns = features.get("patterns", [])
    if patterns:
        lines.append("## Feature Discovery")
        lines.append(f"- Patterns found: {len(patterns)}")
        lines.append("- Top patterns:")
        for p in patterns[:10]:
            dev = p.get("deviation_from_overall")
            dev_str = f"{dev:+.1f}pp" if dev is not None else "N/A"
            lines.append(
                f"  - **{p['segment']}**: n={p['n_graded']}, "
                f"win%={p.get('win_pct', 'N/A')}, "
                f"CLV={p.get('mean_clv', 'N/A')}, "
                f"dev={dev_str}"
            )
        lines.append("")

    # Calibration
    cal = report.get("calibration_agent", {})
    metrics = cal.get("metrics", {})
    if metrics.get("n"):
        lines.append("## Calibration")
        lines.append(f"- Samples: {metrics['n']}")
        lines.append(f"- LogLoss: {metrics.get('logloss', 'N/A')}")
        lines.append(f"- Brier: {metrics.get('brier', 'N/A')}")
        lines.append(f"- Avg confidence: {metrics.get('avg_confidence', 'N/A')}")
        lines.append(f"- Avg win rate: {metrics.get('avg_win_rate', 'N/A')}")
        cand = cal.get("candidate_curve")
        if cand:
            lines.append(f"- Candidate curve fitted (improvement: LL={cand.get('improvement_logloss', 'N/A')}, Brier={cand.get('improvement_brier', 'N/A')})")
        lines.append("")

    # Tournament
    tourney = report.get("strategy_tournament", {})
    top5 = tourney.get("top_5", [])
    if top5:
        lines.append("## Model Tournament")
        champ = tourney.get("champion")
        if champ:
            lines.append(f"- Champion: C={champ['C']}, MIN_EDGE={champ['MIN_EDGE']} -> LL={champ['logloss']}, CLV={champ['mean_clv']}, ROI={champ['roi_pct']}%")
        lines.append("- Top 5 variants:")
        for i, v in enumerate(top5, 1):
            lines.append(
                f"  {i}. C={v['C']}, ME={v['MIN_EDGE']} "
                f"-> LL={v['logloss']}, CLV={v['mean_clv']}, ROI={v['roi_pct']}%, "
                f"n={v['n_bets']}"
            )
        lines.append("")

    # Gating
    gating = report.get("gating", {})
    if gating:
        status = "PASSED" if gating.get("passed") else "BLOCKED"
        lines.append(f"## Deployment Gating: {status}")
        for c in gating.get("checks", []):
            mark = "pass" if c["passed"] else "FAIL"
            lines.append(f"  - [{mark}] {c['gate']}: {json.dumps({k: v for k, v in c.items() if k not in ('gate', 'passed')})}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run(
    days: int = 180,
    deploy: bool = False,
    agent: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run the full 5-agent improvement loop.

    Args:
        days: lookback window
        deploy: if True, attempt champion update (requires all gates to pass)
        agent: if set, run only this agent (e.g. 'clv_auditor')
        dry_run: if True, no file writes
    """
    mode = "deploy" if deploy else "shadow"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"\n{'='*60}")
    print(f"  Agent Improvement Loop — {mode} mode")
    print(f"  Lookback: {days} days | Timestamp: {ts}")
    print(f"{'='*60}\n")

    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "mode": mode,
        "timestamp": ts,
    }

    single = agent is not None

    # --- Agent 3: CLV Auditor ---
    clv_report = None
    if not single or agent == "clv_auditor":
        print("\n--- Agent 3: CLV Auditor ---")
        clv_report = clv_auditor.run(days=days, dry_run=dry_run)
        report["clv_auditor"] = {
            k: v for k, v in clv_report.items() if k != "picks"
        }
        # Keep picks in memory for downstream agents
        print(f"[orchestrator] CLV: {clv_report['overall'].get('n', 0)} picks, "
              f"mean={clv_report['overall'].get('mean', 'N/A')}")

    if single and agent == "clv_auditor":
        return _finalize(report, ts, dry_run)

    # --- Agent 5: Error Attribution ---
    if not single or agent == "error_attribution":
        print("\n--- Agent 5: Error Attribution ---")
        errors = error_attribution.run(days=days, clv_data=clv_report, dry_run=dry_run)
        report["error_attribution"] = errors
        print(f"[orchestrator] Errors: {errors['n_losses']} losses categorized")

    if single and agent == "error_attribution":
        return _finalize(report, ts, dry_run)

    # --- Agent 1: Feature Discovery ---
    features_report = None
    if not single or agent == "feature_discovery":
        print("\n--- Agent 1: Feature Discovery ---")
        features_report = feature_discovery.run(days=days, clv_data=clv_report, dry_run=dry_run)
        report["feature_discovery"] = {
            k: v for k, v in features_report.items()
            if k != "proposed_feature_tests"
        }
        report["feature_discovery"]["n_proposed_tests"] = len(
            features_report.get("proposed_feature_tests", [])
        )
        print(f"[orchestrator] Features: {len(features_report.get('patterns', []))} patterns found")

    if single and agent == "feature_discovery":
        return _finalize(report, ts, dry_run)

    # --- Agent 4: Calibration ---
    if not single or agent == "calibration_agent":
        print("\n--- Agent 4: Calibration Agent ---")
        cal = calibration_agent.run(days=days, dry_run=dry_run)
        report["calibration_agent"] = cal
        print(f"[orchestrator] Calibration: n={cal.get('n_usable', 0)}, "
              f"LL={cal.get('metrics', {}).get('logloss', 'N/A')}")

    if single and agent == "calibration_agent":
        return _finalize(report, ts, dry_run)

    # --- Agent 2: Strategy Tournament ---
    if not single or agent == "strategy_tournament":
        print("\n--- Agent 2: Strategy Tournament ---")
        tourney = strategy_tournament.run(
            days=days, features_data=features_report, dry_run=dry_run
        )
        report["strategy_tournament"] = {
            k: v for k, v in tourney.items() if k != "all_results"
        }
        print(f"[orchestrator] Tournament: {tourney['n_variants']} variants tested")

        # --- Gating ---
        champion = tourney.get("champion")
        top = tourney.get("top_5", [None])[0]
        gating = _check_gates(champion, top, report.get("calibration_agent"))
        report["gating"] = gating

        if deploy and gating["passed"] and top:
            print("\n[orchestrator] ALL GATES PASSED — deploying challenger")
            config = {
                "C": top["C"],
                "MIN_EDGE": top["MIN_EDGE"],
                "deployed_at": datetime.now(timezone.utc).isoformat(),
                "metrics": {
                    "logloss": top["logloss"],
                    "mean_clv": top["mean_clv"],
                    "pct_positive_clv": top["pct_positive_clv"],
                    "roi_pct": top["roi_pct"],
                    "n_bets": top["n_bets"],
                    "win_pct": top.get("win_pct"),
                },
            }
            if not dry_run:
                os.makedirs("artifacts", exist_ok=True)
                with open("artifacts/champion_model.json", "w") as f:
                    json.dump(config, f, indent=2)
                print("[orchestrator] Wrote artifacts/champion_model.json")
            report["deployed_config"] = config
        elif deploy:
            print("\n[orchestrator] GATES BLOCKED — no deployment")
            failed = [c for c in gating.get("checks", []) if not c["passed"]]
            for f in failed:
                print(f"  FAIL: {f['gate']}")

    if single and agent == "strategy_tournament":
        return _finalize(report, ts, dry_run)

    return _finalize(report, ts, dry_run)


def _finalize(report: Dict[str, Any], ts: str, dry_run: bool) -> Dict[str, Any]:
    """Write report files."""
    if dry_run:
        print("\n[orchestrator] Dry run — no files written")
        return report

    out_dir = f"reports/agent_runs/{ts}"
    os.makedirs(out_dir, exist_ok=True)

    json_path = f"{out_dir}/report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n[orchestrator] Wrote {json_path}")

    md_path = f"{out_dir}/report.md"
    with open(md_path, "w") as f:
        f.write(_build_markdown(report))
    print(f"[orchestrator] Wrote {md_path}")

    return report

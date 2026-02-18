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

_GATE_MIN_SAMPLE = 100


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

    # Gate 1: Sample size >= 100
    n = challenger.get("n_bets", 0)
    checks.append({
        "gate": "sample_size",
        "passed": n >= _GATE_MIN_SAMPLE,
        "value": n,
        "threshold": _GATE_MIN_SAMPLE,
    })

    # Gate 2: Challenger mean CLV > champion mean CLV
    ch_clv = champion.get("mean_clv", 0)
    cl_clv = challenger.get("mean_clv", 0)
    checks.append({
        "gate": "mean_clv",
        "passed": cl_clv > ch_clv,
        "champion": ch_clv,
        "challenger": cl_clv,
    })

    # Gate 3: Challenger % positive CLV > champion
    ch_pct = champion.get("pct_positive_clv", 0)
    cl_pct = challenger.get("pct_positive_clv", 0)
    checks.append({
        "gate": "pct_positive_clv",
        "passed": cl_pct > ch_pct,
        "champion": ch_pct,
        "challenger": cl_pct,
    })

    # Gate 4: Challenger logloss <= champion logloss
    ch_ll = champion.get("logloss", float("inf"))
    cl_ll = challenger.get("logloss", float("inf"))
    checks.append({
        "gate": "logloss",
        "passed": cl_ll <= ch_ll,
        "champion": ch_ll,
        "challenger": cl_ll,
    })

    # Gate 5: Challenger ROI >= champion ROI - 5%
    ch_roi = champion.get("roi_pct", 0)
    cl_roi = challenger.get("roi_pct", 0)
    checks.append({
        "gate": "roi_regression",
        "passed": cl_roi >= ch_roi - 5.0,
        "champion": ch_roi,
        "challenger": cl_roi,
        "threshold": ch_roi - 5.0,
    })

    # Gate 6: Rolling window check (placeholder — requires 30/90 day sub-runs)
    # For now, auto-pass if other gates pass. Full implementation needs
    # sub-window tournament runs.
    checks.append({
        "gate": "rolling_window",
        "passed": True,
        "note": "Rolling window check requires sub-period tournament runs (future enhancement)",
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
        lines.append("## Strategy Tournament")
        champ = tourney.get("champion")
        if champ:
            lines.append(f"- Champion: K={champ['K']}, HFA={champ['HFA']}, MIN_EDGE={champ['MIN_EDGE']} -> LL={champ['logloss']}, CLV={champ['mean_clv']}, ROI={champ['roi_pct']}%")
        lines.append("- Top 5 variants:")
        for i, v in enumerate(top5, 1):
            lines.append(
                f"  {i}. K={v['K']}, HFA={v['HFA']}, ME={v['MIN_EDGE']} "
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
                "K": top["K"],
                "HFA": top["HFA"],
                "MIN_EDGE": top["MIN_EDGE"],
                "deployed_at": datetime.now(timezone.utc).isoformat(),
                "metrics": {
                    "logloss": top["logloss"],
                    "mean_clv": top["mean_clv"],
                    "roi_pct": top["roi_pct"],
                    "n_bets": top["n_bets"],
                },
            }
            if not dry_run:
                os.makedirs("artifacts", exist_ok=True)
                with open("artifacts/champion_config.json", "w") as f:
                    json.dump(config, f, indent=2)
                print("[orchestrator] Wrote artifacts/champion_config.json")
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

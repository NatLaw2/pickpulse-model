"""CLI entrypoint for the 5-agent improvement loop.

Usage:
    python -m app.agents.run --days 180
    python -m app.agents.run --days 180 --dry-run
    python -m app.agents.run --days 180 --agent clv_auditor
    python -m app.agents.run --days 180 --deploy
"""
from __future__ import annotations

import argparse
import json
import sys

from .orchestrator import run

VALID_AGENTS = [
    "clv_auditor",
    "error_attribution",
    "feature_discovery",
    "calibration_agent",
    "strategy_tournament",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PickPulse 5-Agent Improvement Loop (NBA)"
    )
    parser.add_argument(
        "--days", type=int, default=180,
        help="Lookback window in days (default: 180)",
    )
    parser.add_argument(
        "--deploy", action="store_true",
        help="Deploy mode: update champion config if all gates pass",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Dry run: no file writes",
    )
    parser.add_argument(
        "--agent", type=str, default=None, choices=VALID_AGENTS,
        help="Run a single agent only",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print full report as JSON to stdout",
    )
    args = parser.parse_args()

    report = run(
        days=args.days,
        deploy=args.deploy,
        agent=args.agent,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))

    # Print summary
    mode = report.get("mode", "shadow")
    print(f"\nDone. Mode={mode}, lookback={args.days}d")

    gating = report.get("gating")
    if gating:
        status = "PASSED" if gating["passed"] else "BLOCKED"
        print(f"Gating: {status}")

    deployed = report.get("deployed_config")
    if deployed:
        print(f"Deployed: K={deployed['K']}, HFA={deployed['HFA']}, MIN_EDGE={deployed['MIN_EDGE']}")


if __name__ == "__main__":
    main()

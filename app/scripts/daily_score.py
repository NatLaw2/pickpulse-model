"""Daily batch scoring script for the Churn Risk Engine.

Usage:
    python -m app.scripts.daily_score

Cron (daily at 6 AM):
    0 6 * * * cd /path/to/pickpulse-model && .venv/bin/python -m app.scripts.daily_score >> /var/log/churn_daily.log 2>&1
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pandas as pd

from app.engine.config import get_module
from app.engine.predict import predict

MODULE = "churn"
DATA_PATH = os.path.join("data", "sample", "churn_customers.csv")


def main() -> None:
    mod = get_module(MODULE)
    model_path = os.path.join(mod.artifact_dir, "model.joblib")

    if not os.path.exists(DATA_PATH):
        print(f"[SKIP] No dataset at {DATA_PATH}")
        sys.exit(1)
    if not os.path.exists(model_path):
        print(f"[SKIP] No trained model at {model_path}. Run retrain first.")
        sys.exit(1)

    df = pd.read_csv(DATA_PATH)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting daily scoring ({len(df)} rows)...")

    scored = predict(df, mod)

    total = len(scored)
    high = len(scored[scored["churn_risk_pct"] >= 70])
    med = len(scored[(scored["churn_risk_pct"] >= 40) & (scored["churn_risk_pct"] < 70)])
    arr_at_risk = scored["arr_at_risk"].sum() if "arr_at_risk" in scored.columns else 0

    print(f"  Scored {total} accounts — High: {high}, Med: {med}")
    print(f"  Total ARR at Risk: ${arr_at_risk:,.0f}")

    # Save timestamped snapshot
    os.makedirs("outputs", exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    snapshot_path = os.path.join("outputs", f"churn_scored_{ts}.csv")
    scored.to_csv(snapshot_path, index=False)
    print(f"  Snapshot saved: {snapshot_path}")

    print(f"[{datetime.now(timezone.utc).isoformat()}] Daily scoring complete.")


if __name__ == "__main__":
    main()

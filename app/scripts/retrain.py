"""Monthly retraining script for the Churn Risk Engine.

Usage:
    python -m app.scripts.retrain

Cron (1st of each month at 2 AM):
    0 2 1 * * cd /path/to/pickpulse-model && .venv/bin/python -m app.scripts.retrain >> /var/log/churn_retrain.log 2>&1
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pandas as pd

from app.engine.config import get_module
from app.engine.train import train_model
from app.engine.evaluate import evaluate_model

MODULE = "churn"
DATA_PATH = os.path.join("data", "sample", "churn_customers.csv")


def main() -> None:
    mod = get_module(MODULE)
    if not os.path.exists(DATA_PATH):
        print(f"[SKIP] No dataset found at {DATA_PATH}")
        sys.exit(1)

    df = pd.read_csv(DATA_PATH)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting retrain ({len(df)} rows)...")

    # Train
    meta = train_model(df, mod)
    version = meta.get("version", "unknown")
    val_auc = meta.get("val_auc")
    print(f"  Trained {version} — Val AUC: {val_auc}")

    # Evaluate (use validation split)
    val_path = os.path.join(mod.artifact_dir, "val.csv")
    if os.path.exists(val_path):
        val_df = pd.read_csv(val_path)
    else:
        val_df = df  # fallback
    metrics = evaluate_model(val_df, mod)
    auc = metrics.get("auc")
    brier = metrics.get("brier")
    lift = metrics.get("lift_at_top10")
    print(f"  Eval — AUC: {auc}, Brier: {brier}, Lift@10: {lift}")

    # Guard: refuse to deploy a model worse than 0.60 AUC
    if auc is not None and auc < 0.60:
        print(f"  [WARN] AUC {auc} below 0.60 threshold. Review before using.")
        sys.exit(2)

    print(f"[{datetime.now(timezone.utc).isoformat()}] Retrain complete: {version}")


if __name__ == "__main__":
    main()

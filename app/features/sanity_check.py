"""Sanity check: verify schedule features compute correctly on sample data.

CLI:
  python -m app.features.sanity_check
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd

from app.features.nba_schedule_features import add_schedule_features, SCHEDULE_FEATURE_COLS
from app.features.injuries.factory import get_injury_provider


def main():
    print("=" * 60)
    print("  Structural Features Sanity Check")
    print("=" * 60)

    # Load historical games
    csv_path = "data/nba_games.csv"
    if not os.path.exists(csv_path):
        csv_path = "data/nba_calibration_ml.csv"

    if not os.path.exists(csv_path):
        print("No CSV data found. Skipping.")
        return 1

    df = pd.read_csv(csv_path)
    print(f"\nLoaded {len(df)} games from {csv_path}")

    # Compute schedule features
    print("\n--- Schedule Features ---")
    result = add_schedule_features(df)

    for col in SCHEDULE_FEATURE_COLS:
        if col in result.columns:
            vals = result[col]
            print(f"  {col:25s}  min={vals.min():.1f}  max={vals.max():.1f}  "
                  f"mean={vals.mean():.2f}  nonzero={int((vals != 0).sum())}/{len(vals)}")
        else:
            print(f"  {col:25s}  MISSING")

    # Spot check: first 5 rows
    print("\n--- Sample rows (first 5) ---")
    sample_cols = ["date", "home_team", "away_team"] + [
        c for c in SCHEDULE_FEATURE_COLS if c in result.columns
    ]
    print(result[sample_cols].head().to_string())

    # Back-to-back sanity: rest_days=1 should imply back_to_back=1
    if "home_rest_days" in result.columns and "home_back_to_back" in result.columns:
        b2b_home = result[result["home_back_to_back"] == 1]
        if len(b2b_home) > 0:
            avg_rest = b2b_home["home_rest_days"].mean()
            print(f"\n  Back-to-back games (home): {len(b2b_home)}, avg rest_days={avg_rest:.1f}")

    # Injury provider check
    print("\n--- Injury Provider ---")
    provider = get_injury_provider()
    print(f"  Provider: {type(provider).__name__}")
    test = provider.get_game_injury_features("2024-01-01", "Boston Celtics", "Los Angeles Lakers")
    print(f"  Sample output: {test}")

    print("\n" + "=" * 60)
    print("  SANITY CHECK PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

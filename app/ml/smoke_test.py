"""Smoke test: verify ML model artifacts load and produce predictions.

CLI:
  python -m app.ml.smoke_test

Prints clearly whether the ML model path or Elo fallback was used.
"""
from __future__ import annotations

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main():
    print("=" * 60)
    print("  ML Model Smoke Test")
    print("=" * 60)

    # Step 1: Check artifact files exist
    artifacts = {
        "ml_model.joblib": "artifacts/ml_model.joblib",
        "ml_calibrator.joblib": "artifacts/ml_calibrator.joblib",
        "ml_metadata.json": "artifacts/ml_metadata.json",
    }

    print("\n--- Artifact Check ---")
    all_exist = True
    for name, path in artifacts.items():
        exists = os.path.exists(path)
        status = "FOUND" if exists else "MISSING"
        size = f"({os.path.getsize(path)} bytes)" if exists else ""
        print(f"  {name:30s} {status} {size}")
        if not exists:
            all_exist = False

    if not all_exist:
        print("\nSome artifacts missing. Run: python -m app.ml.train --csv data/nba_calibration_ml.csv")

    # Step 2: Test the predict module
    print("\n--- ML Predict Module ---")
    from app.ml.predict import is_available, predict_win_prob

    available = is_available()
    print(f"  is_available(): {available}")

    if available:
        # Synthetic test: home favorite (-200 / +170 ≈ 0.667 / 0.333 no-vig)
        p_home = predict_win_prob(locked_home_nv=0.667, locked_away_nv=0.333, is_home=1)
        p_away = predict_win_prob(locked_home_nv=0.667, locked_away_nv=0.333, is_home=0)
        print(f"  Test: home_nv=0.667, away_nv=0.333")
        print(f"    predict(is_home=1) = {p_home:.4f}")
        print(f"    predict(is_home=0) = {p_away:.4f}")

        # Even match (-110 / -110 ≈ 0.50 / 0.50)
        p_even = predict_win_prob(locked_home_nv=0.50, locked_away_nv=0.50, is_home=1)
        print(f"  Test: even match (0.50/0.50)")
        print(f"    predict(is_home=1) = {p_even:.4f}")

    # Step 3: Test the full model_nba path with a synthetic game
    print("\n--- Full Model Path Test ---")
    try:
        from app.schema import GameIn
        from app.model_nba import ml_reco

        synthetic_game = GameIn(**{
            "id": "smoke_test_001",
            "sport": "basketball_nba",
            "startTime": "2025-02-18T00:00:00Z",
            "homeTeam": {"name": "Boston Celtics", "abbreviation": "BOS"},
            "awayTeam": {"name": "Los Angeles Lakers", "abbreviation": "LAL"},
            "odds": {
                "moneyline": {"home": -200, "away": 170},
                "spread": None,
                "total": None,
            },
        })

        result = ml_reco(synthetic_game)
        print(f"  Result: {result}")

        if "ML win probability" in str(result.get("rationale", [])):
            print("\n  >>> ML model used <<<")
        elif "Elo" in str(result.get("rationale", [])):
            print("\n  >>> Elo fallback used <<<")
        else:
            print(f"\n  >>> Path: {result.get('status', 'unknown')} <<<")

    except Exception as e:
        print(f"  Error in full path test: {e}")
        import traceback
        traceback.print_exc()

    # Step 4: Print metadata summary if available
    meta_path = "artifacts/ml_metadata.json"
    if os.path.exists(meta_path):
        import json
        with open(meta_path) as f:
            meta = json.load(f)
        print("\n--- Model Metadata ---")
        print(f"  Version:     {meta.get('version')}")
        print(f"  Trained at:  {meta.get('trained_at')}")
        print(f"  Data source: {meta.get('data_source')}")
        print(f"  Features:    {meta.get('features')}")
        print(f"  N train:     {meta.get('n_train')}")
        print(f"  N val:       {meta.get('n_val')}")
        print(f"  Train range: {meta.get('train_range')}")
        print(f"  Val range:   {meta.get('val_range')}")
        train_cal = meta.get("train_metrics_calibrated", {})
        val_cal = meta.get("val_metrics_calibrated", {})
        if train_cal:
            print(f"  Train LL:    {train_cal.get('logloss')}")
            print(f"  Train Brier: {train_cal.get('brier')}")
        if val_cal:
            print(f"  Val LL:      {val_cal.get('logloss')}")
            print(f"  Val Brier:   {val_cal.get('brier')}")

    print("\n" + "=" * 60)
    if available:
        print("  SMOKE TEST PASSED")
    else:
        print("  SMOKE TEST FAILED — no ML artifacts")
    print("=" * 60)

    return 0 if available else 1


if __name__ == "__main__":
    sys.exit(main())

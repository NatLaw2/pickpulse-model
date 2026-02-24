# Migration Guide: PickPulse → Predictive Engine OS

## Overview

The Predictive Engine OS (PEOS) is built alongside the existing PickPulse NBA pipeline.
No existing code was modified or broken. The new engine lives in `app/engine/` and `app/modules/`.

## Directory Structure

```
app/
├── engine/              # NEW — Generic prediction engine
│   ├── config.py        # Module configs, tier definitions, calibration settings
│   ├── schema.py        # Dataset validation
│   ├── features.py      # Generic feature engineering
│   ├── train.py         # Model training (LogReg / HistGBM + Platt calibration)
│   ├── predict.py       # Scoring and tier classification
│   ├── evaluate.py      # Full evaluation (AUC, lift, calibration, PDF)
│   └── sample_data.py   # Synthetic data generators
├── modules/             # NEW — Vertical adapters
│   ├── sales/adapter.py # Sales deal close prediction
│   └── churn/adapter.py # Customer churn prediction
├── console_api.py       # NEW — FastAPI backend for the Console UI
├── console.py           # NEW — Entry point for the console
├── ml/                  # UNCHANGED — Original NBA ML pipeline
├── model_nba.py         # UNCHANGED — NBA prediction logic
├── main.py              # UNCHANGED — Original FastAPI for NBA
└── ...                  # All other existing code unchanged
```

## Key Differences

| Aspect | PickPulse (NBA) | Predictive Engine OS |
|--------|----------------|---------------------|
| Model | Logistic Regression | LogReg or HistGradientBoosting (auto) |
| Calibration | Isotonic (overfit-prone) | Platt/Sigmoid via CalibratedClassifierCV (cv=5) |
| Prob range | [0.01, 0.99] | [0.05, 0.95] |
| Score | `clamp_int(win_prob * 100)` | Probability stays as float; tier = threshold-based |
| Tiers | top_pick/strong_lean/watchlist | Configurable per module |
| Features | Hardcoded 18 features | Auto-detected from CSV columns |
| Storage | Supabase game_results, locked_picks | New generic tables (model_runs, etc.) |

## Running Both

The original NBA pipeline and the new engine run independently:

```bash
# Original NBA model API (port 10000)
uvicorn app.main:app --port 10000

# New Console API (port 8000)
python -m app.console --port 8000
```

## Adding a New Vertical

1. Create `app/modules/<name>/adapter.py` with:
   - `get_config()` returning a `ModuleConfig`
   - `normalize_columns(df)` for column aliasing
   - `add_derived_features(df)` for domain-specific features

2. Add the config to `app/engine/config.py` `MODULES` dict

3. Add the adapter import to `app/console_api.py` `_get_adapter()`

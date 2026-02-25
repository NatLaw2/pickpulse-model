# Predictive Engine OS — Console

A plug-and-play predictive decision engine for B2B use cases. Upload data, train a model, view metrics, generate predictions, and export reports — all from a single console.

## Modules

- **Sales — Deal Close Probability**: Predict which deals will close. Prioritize pipeline by probability and deal value.
- **Churn — Customer Risk**: Identify at-risk customers before they leave. Prioritize outreach by ARR at risk.

## Quick Start

### 1. Backend

```bash
# From repo root
source .venv/bin/activate
pip install -r requirements.txt

# Start the API server
python -m app.console --port 8000
```

### 2. Frontend

```bash
cd console-frontend
npm install
npm run dev
```

Open http://localhost:5173

### 3. Demo Walkthrough

1. **Dashboard** — Overview of modules and metrics
2. **Datasets** — Click "Load Sample" for sales or churn
3. **Train** — Click "Train Model" (takes ~5 seconds)
4. **Evaluate** — View AUC, lift chart, calibration, tier breakdown
5. **Predict** — Generate scored predictions with tiers
6. **Reports** — Download PDF performance report
7. **API** — See endpoint docs and curl examples
8. **Onboarding** — Walk through 21-day implementation checklist

## Architecture

```
┌─────────────────┐     ┌──────────────────┐
│  React Frontend │────▶│  FastAPI Backend  │
│  (Vite + TW)    │     │  (console_api.py) │
│  localhost:5173  │     │  localhost:8000   │
└─────────────────┘     └────────┬─────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              app/engine/   app/modules/   artifacts/
              (generic ML)  (sales,churn)  (saved models)
```

## Key Files

| File | Purpose |
|------|---------|
| `app/engine/config.py` | Module definitions, tier thresholds, calibration settings |
| `app/engine/train.py` | Generic training (LogReg/GBM + Platt calibration) |
| `app/engine/predict.py` | Score data, classify tiers, rank |
| `app/engine/evaluate.py` | AUC, lift, calibration, PDF reports |
| `app/modules/sales/adapter.py` | Sales column mapping and derived features |
| `app/modules/churn/adapter.py` | Churn column mapping and derived features |
| `app/console_api.py` | FastAPI routes for the console UI |
| `console-frontend/` | React + Vite + Tailwind frontend |

## API Endpoints

```
GET  /api/health                      Health check
GET  /api/modules                     List modules
GET  /api/dashboard                   Dashboard summary
POST /api/datasets/{mod}/upload       Upload CSV
POST /api/datasets/{mod}/sample       Load sample data
POST /api/train/{mod}                 Train model
GET  /api/evaluate/{mod}              Get metrics
POST /api/evaluate/{mod}/report       Download PDF
POST /api/predict/{mod}               Generate predictions
GET  /api/predict/{mod}/export        Export CSV
GET  /api/onboarding                  Onboarding steps
```

## Adding a New Module

1. Create `app/modules/<name>/adapter.py`
2. Add config to `app/engine/config.py`
3. Add adapter import to `app/console_api.py`

See `docs/migration_guide.md` for details.

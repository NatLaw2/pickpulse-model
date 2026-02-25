# Agent Improvement Loop Report
Generated: 2026-02-18T19:15:42.171289+00:00
Lookback: 180 days
Mode: shadow

## CLV Auditor
- Picks analyzed: 20
- Mean CLV: 0.0
- Median CLV: 0.0
- % Positive: 0.0%
- **Leakage flags:**
  - Only 0.0% of picks have positive CLV

## Error Attribution
- Total losses: 15
  - calibration_gap: 15
- **Recommendations:**
  - 15 losses (100%) show calibration_gap (confidence >> actual win rate). The confidence curve may need re-fitting with more recent data.

## Feature Discovery
- Patterns found: 12
- Top patterns:
  - **tier:watchlist**: n=5, win%=0.0, CLV=0.0, dev=-16.7pp
  - **tier_market:watchlist_moneyline**: n=5, win%=0.0, CLV=0.0, dev=-16.7pp
  - **slot:early**: n=5, win%=0.0, CLV=0.0, dev=-16.7pp
  - **score:65-74**: n=5, win%=0.0, CLV=0.0, dev=-16.7pp
  - **tier:strong_lean**: n=11, win%=27.3, CLV=0.0, dev=+10.6pp
  - **tier_market:strong_lean_moneyline**: n=11, win%=27.3, CLV=0.0, dev=+10.6pp
  - **score:75+**: n=11, win%=27.3, CLV=0.0, dev=+10.6pp
  - **slot:late**: n=13, win%=23.1, CLV=0.0, dev=+6.4pp
  - **side:away**: n=8, win%=12.5, CLV=0.0, dev=-4.2pp
  - **side:home**: n=10, win%=20.0, CLV=0.0, dev=+3.3pp

## Calibration
- Samples: 18
- LogLoss: 4.02626
- Brier: 0.57408
- Avg confidence: 0.8133
- Avg win rate: 0.1667

## Model Tournament
- Champion: C=1.0, MIN_EDGE=0.03 -> LL=0.50705, CLV=0.0, ROI=-58.25%
- Top 5 variants:
  1. C=1.0, ME=0.04 -> LL=0.50685, CLV=0.0, ROI=-55.04%, n=13
  2. C=1.0, ME=0.03 -> LL=0.50705, CLV=0.0, ROI=-58.25%, n=14
  3. C=1.0, ME=0.02 -> LL=0.51142, CLV=0.0, ROI=-61.04%, n=15
  4. C=10.0, ME=0.02 -> LL=0.54279, CLV=0.0, ROI=-35.06%, n=9
  5. C=10.0, ME=0.03 -> LL=0.5745, CLV=0.0, ROI=-63.89%, n=4

## Deployment Gating: BLOCKED
  - [FAIL] sample_size: {"value": 13, "threshold": 200}
  - [FAIL] logloss_improvement: {"champion_ll": 0.50705, "challenger_ll": 0.50685, "improvement_pct": 0.04, "threshold_pct": 2.0}
  - [FAIL] clv: {"mean_clv": 0.0, "pct_positive_clv": 0.0, "rule": "mean_clv > 0 OR pct_positive_clv >= 52%"}
  - [pass] roi_regression: {"champion_roi": -58.25, "challenger_roi": -55.04, "regression": -3.21, "max_allowed": 2.0}
  - [FAIL] overconfidence: {"avg_confidence": 0.8133, "threshold": 0.62, "win_pct": 15.4}

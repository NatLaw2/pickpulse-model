# Agent Improvement Loop Report
Generated: 2026-02-18T16:27:56.442515+00:00
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

## Strategy Tournament
- Champion: K=10, HFA=40, MIN_EDGE=0.03 -> LL=0.76986, CLV=0.0, ROI=-54.0%
- Top 5 variants:
  1. K=12, HFA=35, ME=0.02 -> LL=0.75723, CLV=0.0, ROI=-57.07%, n=15
  2. K=12, HFA=35, ME=0.03 -> LL=0.75723, CLV=0.0, ROI=-57.07%, n=15
  3. K=10, HFA=35, ME=0.02 -> LL=0.7574, CLV=0.0, ROI=-57.07%, n=15
  4. K=10, HFA=35, ME=0.03 -> LL=0.7574, CLV=0.0, ROI=-57.07%, n=15
  5. K=8, HFA=35, ME=0.02 -> LL=0.75757, CLV=0.0, ROI=-57.07%, n=15

## Deployment Gating: BLOCKED
  - [FAIL] sample_size: {"value": 15, "threshold": 100}
  - [FAIL] mean_clv: {"champion": 0.0, "challenger": 0.0}
  - [FAIL] pct_positive_clv: {"champion": 0.0, "challenger": 0.0}
  - [pass] logloss: {"champion": 0.76986, "challenger": 0.75723}
  - [pass] roi_regression: {"champion": -54.0, "challenger": -57.07, "threshold": -59.0}
  - [pass] rolling_window: {"note": "Rolling window check requires sub-period tournament runs (future enhancement)"}

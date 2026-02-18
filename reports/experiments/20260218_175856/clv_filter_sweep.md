# CLV Filter Sweep

**Timestamp:** 2026-02-18T23:58:56.268336+00:00
**Lookback:** 90 days, 20 picks

## Snapshot Coverage

- **Lock Snap:** 20/20 (100%)
- **Close Snap:** 20/20 (100%)
- **Both:** 20/20 (100%)
- **Clv:** 20/20 (100%)
- **Steam:** 0/20 (0%)

## Filter Results

| Filter | N | Mean CLV | % CLV+ | N Graded | Win Rate | ROI |
|--------|---|----------|--------|----------|----------|-----|
| baseline | 20 | 0.0000 | 0% | 18 | 17% | -56.2% |
| steam_15m >= 0 | 0 | — | — | — | — | — |
| steam_15m >= 0.005 | 0 | — | — | — | — | — |
| range_30m <= 0.03 | 0 | — | — | — | — | — |
| range_30m <= 0.02 | 0 | — | — | — | — | — |
| snap_gap_close <= 300s | 0 | — | — | — | — | — |
| snap_gap_close <= 120s | 0 | — | — | — | — | — |
| clv_prob > 0 | 0 | — | — | — | — | — |
| clv_prob > 0.01 | 0 | — | — | — | — | — |

# CLV Timing Features Summary

## Snapshot Coverage

| Metric | Count | % |
|--------|-------|---|
| Lock Snap | 20 | 100.0% |
| Close Snap | 20 | 100.0% |
| Both | 20 | 100.0% |
| Clv | 20 | 100.0% |
| Steam | 0 | 0.0% |
| **Total Picks** | **20** | |

## Feature Distributions

| Feature | N | Mean | Median | Std | Min | Max |
|---------|---|------|--------|-----|-----|-----|
| CLV (prob) | 20 | 0.00000 | 0.00000 | 0.00000 | 0.00000 | 0.00000 |
| P(lock) | 20 | 0.37522 | 0.36570 | 0.14505 | 0.16303 | 0.66598 |
| P(close) | 20 | 0.37522 | 0.36570 | 0.14505 | 0.16303 | 0.66598 |
| Steam 5m | 0 | — | — | — | — | — |
| Steam 15m | 0 | — | — | — | — | — |
| Velocity 30m | 0 | — | — | — | — | — |
| Range 30m | 0 | — | — | — | — | — |
| Std 30m | 0 | — | — | — | — | — |
| Snap Gap Lock (s) | 20 | 25973.61000 | 25913.40000 | 12999.48819 | 4464.30000 | 51564.20000 |
| Snap Gap Close (s) | 20 | 42604.70000 | 45922.50000 | 10507.82801 | 20663.00000 | 54863.00000 |

**CLV Summary:** mean=0.00000, pct_positive=0.0% (n=20)


*Shadow mode only. Do not deploy filters without further validation.*

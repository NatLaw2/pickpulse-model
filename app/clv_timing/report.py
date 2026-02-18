"""CLV timing feature distribution summary.

Generates a markdown summary of timing features across a batch of picks.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def summarize_features(
    features: List[Dict[str, Any]],
    coverage: Dict[str, int],
) -> str:
    """Produce a markdown summary of CLV timing features."""
    lines = []
    lines.append("# CLV Timing Features Summary")
    lines.append("")

    total = coverage.get("total", 0)
    if total == 0:
        lines.append("No picks to analyze.")
        return "\n".join(lines)

    # Coverage table
    lines.append("## Snapshot Coverage")
    lines.append("")
    lines.append("| Metric | Count | % |")
    lines.append("|--------|-------|---|")
    for key in ["has_lock_snap", "has_close_snap", "has_both", "has_clv", "has_steam"]:
        count = coverage.get(key, 0)
        pct = count / total * 100 if total > 0 else 0
        label = key.replace("has_", "").replace("_", " ").title()
        lines.append(f"| {label} | {count} | {pct:.1f}% |")
    lines.append(f"| **Total Picks** | **{total}** | |")
    lines.append("")

    # Feature distributions
    feat_keys = [
        ("clv_prob", "CLV (prob)"),
        ("p_lock", "P(lock)"),
        ("p_close", "P(close)"),
        ("steam_5m", "Steam 5m"),
        ("steam_15m", "Steam 15m"),
        ("velocity_30m", "Velocity 30m"),
        ("range_30m", "Range 30m"),
        ("std_30m", "Std 30m"),
        ("snap_gap_lock_sec", "Snap Gap Lock (s)"),
        ("snap_gap_close_sec", "Snap Gap Close (s)"),
    ]

    lines.append("## Feature Distributions")
    lines.append("")
    lines.append("| Feature | N | Mean | Median | Std | Min | Max |")
    lines.append("|---------|---|------|--------|-----|-----|-----|")

    for key, label in feat_keys:
        vals = [f[key] for f in features if f.get(key) is not None and math.isfinite(f[key])]
        if not vals:
            lines.append(f"| {label} | 0 | — | — | — | — | — |")
            continue
        n = len(vals)
        mean = sum(vals) / n
        vals_sorted = sorted(vals)
        median = vals_sorted[n // 2] if n % 2 == 1 else (vals_sorted[n // 2 - 1] + vals_sorted[n // 2]) / 2
        variance = sum((v - mean) ** 2 for v in vals) / n if n > 1 else 0
        std = math.sqrt(variance)
        lines.append(
            f"| {label} | {n} | {mean:.5f} | {median:.5f} | "
            f"{std:.5f} | {min(vals):.5f} | {max(vals):.5f} |"
        )

    # CLV positive rate
    clvs = [f["clv_prob"] for f in features if f.get("clv_prob") is not None and math.isfinite(f["clv_prob"])]
    if clvs:
        pct_pos = sum(1 for c in clvs if c > 0) / len(clvs) * 100
        mean_clv = sum(clvs) / len(clvs)
        lines.append("")
        lines.append(f"**CLV Summary:** mean={mean_clv:.5f}, pct_positive={pct_pos:.1f}% (n={len(clvs)})")

    lines.append("")
    return "\n".join(lines)

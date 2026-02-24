"""Full evaluation — metrics, lift, calibration, PDF report generation."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import ModuleConfig
from .predict import load_model, predict


def evaluate_model(
    df: pd.DataFrame,
    module: ModuleConfig,
    output_dir: str = "outputs",
) -> Dict[str, Any]:
    """Run full evaluation on a labeled dataset.

    Args:
        df: DataFrame with labels (typically the validation/test split).
        module: Module configuration.
        output_dir: Directory to write output files.

    Returns:
        Evaluation report dict.
    """
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, brier_score_loss, log_loss,
        confusion_matrix, classification_report, precision_recall_curve, f1_score,
    )

    print(f"\n{'=' * 60}")
    print(f"  Evaluating: {module.display_name}")
    print(f"{'=' * 60}\n")

    # Score the dataset
    scored = predict(df, module)
    # Reset index so scored and arrays align
    scored = scored.reset_index(drop=True)

    probs = scored["probability"].values
    y = scored[module.label_column].astype(int).values
    n = len(y)

    # Core metrics
    eps = 1e-15
    probs_clipped = np.clip(probs, eps, 1 - eps)

    metrics: Dict[str, Any] = {
        "module": module.name,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "n": n,
        "base_rate": round(float(y.mean()), 4),
    }

    try:
        metrics["auc"] = round(float(roc_auc_score(y, probs)), 5)
    except ValueError:
        metrics["auc"] = None

    try:
        metrics["pr_auc"] = round(float(average_precision_score(y, probs)), 5)
    except ValueError:
        metrics["pr_auc"] = None

    metrics["brier"] = round(float(brier_score_loss(y, probs)), 5)
    metrics["logloss"] = round(float(log_loss(y, probs_clipped)), 5)

    # Find optimal threshold by maximizing F1
    if int(y.sum()) > 0:
        pr_vals, rc_vals, thresholds = precision_recall_curve(y, probs)
        # F1 for each threshold (pr_vals and rc_vals have len = thresholds + 1)
        f1_scores = np.where(
            (pr_vals[:-1] + rc_vals[:-1]) > 0,
            2 * pr_vals[:-1] * rc_vals[:-1] / (pr_vals[:-1] + rc_vals[:-1]),
            0.0,
        )
        best_idx = int(np.argmax(f1_scores))
        best_threshold = float(thresholds[best_idx])
    else:
        best_threshold = 0.5

    metrics["threshold"] = round(best_threshold, 4)

    # Confusion matrix using optimal threshold
    preds = (probs >= best_threshold).astype(int)
    cm = confusion_matrix(y, preds, labels=[0, 1])
    metrics["confusion_matrix"] = cm.tolist()
    tn, fp, fn, tp = cm.ravel()
    metrics["accuracy"] = round(float((tp + tn) / n), 4)
    metrics["precision"] = round(float(tp / (tp + fp)), 4) if (tp + fp) > 0 else 0.0
    metrics["recall"] = round(float(tp / (tp + fn)), 4) if (tp + fn) > 0 else 0.0
    metrics["f1"] = round(float(f1_score(y, preds)), 4) if int(y.sum()) > 0 else 0.0

    # Calibration bins
    n_bins = min(10, max(3, n // 50))
    sorted_idx = np.argsort(probs)
    chunk = max(1, n // n_bins)
    calibration_bins = []
    for i in range(0, n, chunk):
        sl = sorted_idx[i:i + chunk]
        if len(sl) == 0:
            continue
        calibration_bins.append({
            "bin_lo": round(float(probs[sl].min()), 4),
            "bin_hi": round(float(probs[sl].max()), 4),
            "n": int(len(sl)),
            "predicted_avg": round(float(probs[sl].mean()), 4),
            "actual_rate": round(float(y[sl].mean()), 4),
            "delta": round(float(probs[sl].mean() - y[sl].mean()), 4),
        })
    metrics["calibration_bins"] = calibration_bins
    metrics["calibration_error"] = round(
        float(np.mean([abs(b["delta"]) for b in calibration_bins])), 4
    )

    # Lift / decile table
    lift_table = _compute_lift_table(probs, y)
    metrics["lift_table"] = lift_table
    if lift_table:
        metrics["lift_at_top10"] = lift_table[0]["lift"]
        top_decile = lift_table[0]
        metrics["capture_at_top10"] = top_decile["cumulative_capture"]

    # Tier breakdown
    tier_breakdown = {}
    for tier_label in [module.tiers.high_label, module.tiers.medium_label, module.tiers.low_label]:
        mask = (scored["tier"] == tier_label).values
        if mask.sum() == 0:
            continue
        tier_y = y[mask]
        tier_p = probs[mask]
        tier_breakdown[tier_label] = {
            "count": int(mask.sum()),
            "actual_rate": round(float(tier_y.mean()), 4),
            "avg_probability": round(float(tier_p.mean()), 4),
        }
        if module.value_column and module.value_column in scored.columns:
            tier_vals = scored.loc[mask, module.value_column].values.astype(float)
            tier_breakdown[tier_label]["total_value"] = round(float(tier_vals.sum()), 2)
            tier_breakdown[tier_label]["value_at_risk"] = round(
                float((tier_vals * tier_p).sum()), 2
            )
    metrics["tier_breakdown"] = tier_breakdown

    # Business impact summary
    if module.value_column and module.value_column in scored.columns:
        total_value = scored[module.value_column].sum()
        # Value captured in top decile
        top_n = max(1, n // 10)
        top_idx = np.argsort(-probs)[:top_n]
        top_value = scored.iloc[top_idx][module.value_column].sum()
        top_positives = int(y[top_idx].sum())
        # ARR at risk in top decile
        arr_at_risk_top = float((scored.iloc[top_idx][module.value_column] * probs[top_idx]).sum())
        total_arr_at_risk = float((scored[module.value_column] * probs).sum())
        metrics["business_impact"] = {
            "total_value": round(float(total_value), 2),
            "value_in_top_decile": round(float(top_value), 2),
            "arr_at_risk_top_decile": round(arr_at_risk_top, 2),
            "total_arr_at_risk": round(total_arr_at_risk, 2),
            "positives_in_top_decile": top_positives,
            "total_positives": int(y.sum()),
        }

    # Write outputs
    os.makedirs(output_dir, exist_ok=True)

    report_path = os.path.join(output_dir, f"{module.name}_evaluation.json")
    with open(report_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"[eval] Saved report -> {report_path}")

    # Scored CSV
    scored_path = os.path.join(output_dir, f"{module.name}_scored.csv")
    scored.to_csv(scored_path, index=False)
    print(f"[eval] Saved scored data -> {scored_path}")

    # Print summary
    print(f"\n  AUC:          {metrics.get('auc', 'N/A')}")
    print(f"  PR-AUC:       {metrics.get('pr_auc', 'N/A')}")
    print(f"  Brier:        {metrics['brier']}")
    print(f"  LogLoss:      {metrics['logloss']}")
    print(f"  Calibration:  {metrics['calibration_error']} avg |delta|")
    if metrics.get("lift_at_top10"):
        print(f"  Lift@Top10%:  {metrics['lift_at_top10']}x")
    print()

    return metrics


def _compute_lift_table(probs: np.ndarray, y: np.ndarray) -> List[Dict[str, Any]]:
    """Compute lift/decile table."""
    n = len(y)
    n_deciles = min(10, max(2, n // 20))
    sorted_idx = np.argsort(-probs)
    chunk = max(1, n // n_deciles)
    base_rate = float(y.mean())
    table = []
    cumulative_positives = 0
    total_positives = int(y.sum())

    for i in range(0, n, chunk):
        sl = sorted_idx[i:i + chunk]
        if len(sl) == 0:
            continue
        decile = len(table) + 1
        actual_rate = float(y[sl].mean())
        cumulative_positives += int(y[sl].sum())
        capture_rate = cumulative_positives / total_positives if total_positives > 0 else 0.0
        lift = actual_rate / base_rate if base_rate > 0 else 0.0
        table.append({
            "decile": decile,
            "n": int(len(sl)),
            "avg_prob": round(float(probs[sl].mean()), 4),
            "actual_rate": round(actual_rate, 4),
            "lift": round(lift, 2),
            "cumulative_capture": round(capture_rate, 4),
        })

    return table


def generate_pdf_report(
    metrics: Dict[str, Any],
    module: ModuleConfig,
    output_path: str = "outputs/report.pdf",
) -> str:
    """Generate a PDF performance report."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        print("[eval] reportlab not installed. Skipping PDF generation.")
        print("[eval] Install with: pip install reportlab")
        return ""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"],
        fontSize=20, spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        "CustomHeading", parent=styles["Heading2"],
        fontSize=14, spaceBefore=15, spaceAfter=8,
    )

    elements = []

    # Title
    report_title = "Churn Risk Report" if module.name == "churn" else "Predictive Performance Report"
    elements.append(Paragraph(report_title, title_style))
    elements.append(Paragraph(module.display_name, styles["Heading3"]))
    elements.append(Paragraph(
        f"Generated: {metrics.get('evaluated_at', 'N/A')}", styles["Normal"]
    ))
    elements.append(Spacer(1, 20))

    # Key Metrics
    elements.append(Paragraph("Key Metrics", heading_style))
    metric_data = [
        ["Metric", "Value"],
        ["Samples", str(metrics.get("n", ""))],
        ["AUC", str(metrics.get("auc", "N/A"))],
        ["PR-AUC", str(metrics.get("pr_auc", "N/A"))],
        ["Brier Score", str(metrics.get("brier", ""))],
        ["Log Loss", str(metrics.get("logloss", ""))],
        ["Calibration Error", str(metrics.get("calibration_error", ""))],
        ["Accuracy", str(metrics.get("accuracy", ""))],
        ["Precision", str(metrics.get("precision", ""))],
        ["Recall", str(metrics.get("recall", ""))],
    ]
    if metrics.get("lift_at_top10"):
        metric_data.append(["Lift @ Top 10%", f"{metrics['lift_at_top10']}x"])

    t = Table(metric_data, colWidths=[2.5 * inch, 2.5 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8fc")]),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15))

    # Lift Table
    lift_table = metrics.get("lift_table", [])
    if lift_table:
        elements.append(Paragraph("Lift by Decile", heading_style))
        lift_data = [["Decile", "N", "Avg Prob", "Actual Rate", "Lift", "Cum. Capture"]]
        for row in lift_table:
            lift_data.append([
                str(row["decile"]),
                str(row["n"]),
                f"{row['avg_prob']:.3f}",
                f"{row['actual_rate']:.3f}",
                f"{row['lift']:.2f}x",
                f"{row['cumulative_capture']:.1%}",
            ])
        t = Table(lift_data, colWidths=[0.7*inch, 0.7*inch, 1.0*inch, 1.0*inch, 0.8*inch, 1.2*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8fc")]),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 15))

    # Tier Breakdown
    tier_breakdown = metrics.get("tier_breakdown", {})
    if tier_breakdown:
        elements.append(Paragraph("Tier Breakdown", heading_style))
        tier_data = [["Tier", "Count", "Actual Rate", "Avg Probability"]]
        for tier_name, info in tier_breakdown.items():
            tier_data.append([
                tier_name,
                str(info["count"]),
                f"{info['actual_rate']:.1%}",
                f"{info['avg_probability']:.3f}",
            ])
        t = Table(tier_data, colWidths=[1.5*inch, 1.0*inch, 1.2*inch, 1.5*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8fc")]),
        ]))
        elements.append(t)

    # Business Impact Summary
    biz = metrics.get("business_impact", {})
    if biz:
        elements.append(Paragraph("Business Impact", heading_style))
        biz_data = [
            ["Metric", "Value"],
            ["Total ARR", f"${biz.get('total_value', 0):,.0f}"],
            ["Total ARR at Risk", f"${biz.get('total_arr_at_risk', 0):,.0f}"],
            ["ARR at Risk (Top 10%)", f"${biz.get('arr_at_risk_top_decile', 0):,.0f}"],
            ["Churned Accounts (Top 10%)", str(biz.get('positives_in_top_decile', ''))],
            ["Total Churned", str(biz.get('total_positives', ''))],
        ]
        t = Table(biz_data, colWidths=[2.5 * inch, 2.5 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8fc")]),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 15))

    # Footer
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(
        "Generated by Churn Risk Engine",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
    ))

    doc.build(elements)
    print(f"[eval] PDF report saved -> {output_path}")
    return output_path

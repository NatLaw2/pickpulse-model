"""Churn Risk Engine — Console API (FastAPI backend)."""
from __future__ import annotations

import json
import os
import shutil
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .engine.config import MODULES, get_module, ModuleConfig
from .engine.schema import validate_dataset, ValidationResult
from .engine.sample_data import generate_churn_dataset
from .engine.train import train_model
from .engine.evaluate import evaluate_model, generate_pdf_report
from .engine.predict import predict, load_model

app = FastAPI(title="Churn Risk Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Persistent dataset state — survives server restarts
# On Render, DATA_DIR points to a persistent disk mount (e.g. /data).
# Locally it defaults to the repo-relative "data/" directory.
# ---------------------------------------------------------------------------
DATA_DIR = os.environ.get("DATA_DIR", "data")
DATASET_STATE_PATH = os.path.join(DATA_DIR, ".dataset_state.json")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
SAMPLE_DIR = os.path.join(DATA_DIR, "sample")
MODULE_NAME = "churn"

# Ensure data directories exist at startup
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SAMPLE_DIR, exist_ok=True)


def _load_persisted_datasets() -> Dict[str, Any]:
    """Load dataset registry from disk."""
    if os.path.exists(DATASET_STATE_PATH):
        try:
            with open(DATASET_STATE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_persisted_datasets(datasets: Dict[str, Any]) -> None:
    """Save dataset registry to disk."""
    os.makedirs(os.path.dirname(DATASET_STATE_PATH) or ".", exist_ok=True)
    with open(DATASET_STATE_PATH, "w") as f:
        json.dump(datasets, f, indent=2)


# In-memory state (with persistent dataset layer)
_state: Dict[str, Any] = {
    "datasets": _load_persisted_datasets(),
    "train_logs": {},
    "metrics": {},
    "predictions": {},
    "account_statuses": {},  # customer_id -> status string
}


def _register_dataset(module_name: str, info: Dict[str, Any]) -> None:
    """Register a dataset in both memory and on disk."""
    _state["datasets"][module_name] = info
    _save_persisted_datasets(_state["datasets"])


def _get_dataset(module_name: str) -> Optional[Dict[str, Any]]:
    """Get dataset info, validating the file still exists on disk."""
    ds = _state["datasets"].get(module_name)
    if ds and os.path.exists(ds["path"]):
        return ds
    return None


# -----------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "service": "Churn Risk Engine"}


# -----------------------------------------------------------------------
# Modules
# -----------------------------------------------------------------------
@app.get("/api/modules")
def list_modules():
    result = []
    for name, mod in MODULES.items():
        has_model = os.path.exists(os.path.join(mod.artifact_dir, "model.joblib"))
        metadata = None
        if has_model:
            meta_path = os.path.join(mod.artifact_dir, "metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    metadata = json.load(f)

        ds = _get_dataset(name)
        result.append({
            "name": name,
            "display_name": mod.display_name,
            "has_model": has_model,
            "has_dataset": ds is not None,
            "metadata": metadata,
            "required_columns": mod.required_columns,
            "optional_columns": mod.optional_columns,
            "tiers": {
                "high": mod.tiers.high_label,
                "medium": mod.tiers.medium_label,
                "low": mod.tiers.low_label,
            },
        })
    return result


@app.get("/api/modules/{module_name}")
def get_module_detail(module_name: str):
    mod = get_module(module_name)
    has_model = os.path.exists(os.path.join(mod.artifact_dir, "model.joblib"))

    metadata = None
    if has_model:
        meta_path = os.path.join(mod.artifact_dir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                metadata = json.load(f)

    ds = _get_dataset(mod.name)
    return {
        "name": mod.name,
        "display_name": mod.display_name,
        "has_model": has_model,
        "has_dataset": ds is not None,
        "dataset_info": ds,
        "metadata": metadata,
        "metrics": _state["metrics"].get(mod.name),
        "required_columns": mod.required_columns,
        "optional_columns": mod.optional_columns,
    }


# -----------------------------------------------------------------------
# Dataset upload
# -----------------------------------------------------------------------
@app.post("/api/datasets/{module_name}/upload")
async def upload_dataset(module_name: str, file: UploadFile = File(...)):
    mod = get_module(module_name)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    filename = f"{module_name}_{uuid.uuid4().hex[:8]}.csv"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        os.remove(filepath)
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    adapter = _get_adapter(module_name)
    if adapter:
        df = adapter.normalize_columns(df)
        df.to_csv(filepath, index=False)

    validation = validate_dataset(df, mod)

    ds_info = {
        "path": filepath,
        "name": file.filename,
        "rows": len(df),
        "columns": len(df.columns),
        "is_demo": False,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }
    _register_dataset(module_name, ds_info)

    return {
        "status": "uploaded",
        "file": filename,
        "validation": _validation_to_dict(validation),
        "dataset_info": ds_info,
    }


@app.post("/api/datasets/{module_name}/sample")
def load_sample_dataset(module_name: str):
    mod = get_module(module_name)
    os.makedirs(SAMPLE_DIR, exist_ok=True)

    if module_name != "churn":
        raise HTTPException(status_code=400, detail="Only churn module is available")

    df = generate_churn_dataset()
    filepath = os.path.join(SAMPLE_DIR, f"{module_name}_sample.csv")
    df.to_csv(filepath, index=False)

    validation = validate_dataset(df, mod)

    ds_info = {
        "path": filepath,
        "name": f"{module_name}_sample.csv",
        "rows": len(df),
        "columns": len(df.columns),
        "is_demo": True,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }
    _register_dataset(module_name, ds_info)

    return {
        "status": "loaded",
        "validation": _validation_to_dict(validation),
        "dataset_info": ds_info,
    }


@app.get("/api/datasets/{module_name}/current")
def get_current_dataset(module_name: str):
    """Return metadata for the currently loaded dataset (or 404)."""
    get_module(module_name)  # validate module name
    ds = _get_dataset(module_name)
    if not ds:
        raise HTTPException(status_code=404, detail="No dataset loaded.")
    return ds


@app.get("/api/datasets/{module_name}/validate")
def validate_current_dataset(module_name: str):
    mod = get_module(module_name)
    ds = _get_dataset(module_name)
    if not ds:
        raise HTTPException(status_code=404, detail="No dataset loaded.")

    df = pd.read_csv(ds["path"])
    validation = validate_dataset(df, mod)
    return _validation_to_dict(validation)


# -----------------------------------------------------------------------
# Training
# -----------------------------------------------------------------------
@app.post("/api/train/{module_name}")
def train_module(module_name: str, val_frac: float = Query(0.2)):
    mod = get_module(module_name)
    ds = _get_dataset(module_name)
    if not ds:
        raise HTTPException(status_code=400, detail="No dataset loaded. Upload or load sample first.")

    try:
        df = pd.read_csv(ds["path"])

        adapter = _get_adapter(module_name)
        if adapter:
            df = adapter.normalize_columns(df)
            df = adapter.add_derived_features(df)

        metadata = train_model(df, mod, val_frac=val_frac)

        if "error" in metadata:
            raise HTTPException(status_code=400, detail=metadata.get("message", metadata["error"]))

        # Auto-evaluate on val split
        ts_col = mod.timestamp_column
        if ts_col in df.columns:
            df_sorted = df.copy()
            df_sorted["_ts"] = pd.to_datetime(df_sorted[ts_col], errors="coerce")
            df_sorted = df_sorted.sort_values("_ts").drop(columns=["_ts"])
            split_idx = int(len(df_sorted) * (1 - val_frac))
            val_df = df_sorted.iloc[split_idx:]
            if adapter:
                val_df = adapter.add_derived_features(val_df)
            if len(val_df) >= 10:
                metrics = evaluate_model(val_df, mod)
                _state["metrics"][module_name] = metrics
        elif metadata.get("val_metrics"):
            _state["metrics"][module_name] = metadata["val_metrics"]

        return {
            "status": "trained",
            "metadata": metadata,
            "metrics": _state["metrics"].get(module_name),
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# Evaluation
# -----------------------------------------------------------------------
@app.get("/api/evaluate/{module_name}")
def get_evaluation(module_name: str):
    mod = get_module(module_name)
    metrics = _state["metrics"].get(module_name)

    if not metrics:
        report_path = os.path.join("outputs", f"{module_name}_evaluation.json")
        if os.path.exists(report_path):
            with open(report_path) as f:
                metrics = json.load(f)
            _state["metrics"][module_name] = metrics

    if not metrics:
        meta_path = os.path.join(mod.artifact_dir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                metadata = json.load(f)
            metrics = metadata.get("val_metrics")
            if metrics:
                _state["metrics"][module_name] = metrics

    if not metrics:
        raise HTTPException(status_code=404, detail="No evaluation results. Train a model first.")

    return metrics


@app.post("/api/evaluate/{module_name}/report")
def generate_report(module_name: str):
    mod = get_module(module_name)
    metrics = _state["metrics"].get(module_name)
    if not metrics:
        raise HTTPException(status_code=404, detail="No evaluation metrics. Train first.")

    output_path = os.path.join("outputs", f"{module_name}_report.pdf")
    result = generate_pdf_report(metrics, mod, output_path)
    if not result:
        raise HTTPException(status_code=500, detail="PDF generation failed (reportlab not installed).")

    return FileResponse(output_path, media_type="application/pdf",
                        filename="churn_risk_report.pdf")


# -----------------------------------------------------------------------
# Predictions
# -----------------------------------------------------------------------
@app.post("/api/predict/{module_name}")
def predict_module(
    module_name: str,
    limit: int = Query(100),
    include_archived: bool = Query(False),
):
    """Generate predictions on the loaded dataset."""
    mod = get_module(module_name)
    ds = _get_dataset(module_name)
    if not ds:
        raise HTTPException(status_code=400, detail="No dataset loaded.")

    if not os.path.exists(os.path.join(mod.artifact_dir, "model.joblib")):
        raise HTTPException(status_code=400, detail="No trained model. Train first.")

    try:
        df = pd.read_csv(ds["path"])
        adapter = _get_adapter(module_name)
        if adapter:
            df = adapter.normalize_columns(df)
            df = adapter.add_derived_features(df)

        scored = predict(df, mod)

        # Apply any manual status overrides
        for cid, status in _state["account_statuses"].items():
            mask = scored[mod.id_column] == cid
            if mask.any():
                scored.loc[mask, "account_status"] = status

        # Save full scored output for export
        os.makedirs("outputs", exist_ok=True)
        scored.to_csv(os.path.join("outputs", f"{module_name}_scored.csv"), index=False)

        # Filter archived unless requested
        if not include_archived and "account_status" in scored.columns:
            scored_display = scored[scored["account_status"] == "active"].copy()
        else:
            scored_display = scored.copy()

        # Build display columns for churn
        display_cols = [
            mod.id_column, "churn_risk_pct", "urgency_score",
            "renewal_window_label", "days_until_renewal", "auto_renew_flag",
            "arr", "arr_at_risk", "recommended_action", "account_status", "tier", "rank",
        ]
        # Fall back to generic cols if churn-specific ones aren't present
        display_cols = [c for c in display_cols if c in scored_display.columns]
        if not display_cols:
            display_cols = [mod.id_column, "probability", "tier", "rank"]
            if mod.value_column and mod.value_column in scored_display.columns:
                display_cols.insert(1, mod.value_column)
            if "value_at_risk" in scored_display.columns:
                display_cols.append("value_at_risk")
            display_cols = [c for c in display_cols if c in scored_display.columns]

        records = scored_display[display_cols].head(limit).to_dict(orient="records")
        _state["predictions"][module_name] = records

        # Tier counts (from full active set)
        tier_counts = scored_display["tier"].value_counts().to_dict()

        # Summary stats for dashboard
        summary = {}
        if "arr_at_risk" in scored_display.columns:
            summary["total_arr_at_risk"] = round(float(scored_display["arr_at_risk"].sum()), 2)
        if "renewal_window_90d" in scored.columns:
            summary["renewing_90d"] = int(scored[scored["account_status"] == "active"]["renewal_window_90d"].sum()) if "account_status" in scored.columns else int(scored["renewal_window_90d"].sum())
        if "churn_risk_pct" in scored_display.columns and "renewal_window_90d" in scored.columns:
            high_in_window = scored_display[
                (scored_display["churn_risk_pct"] >= 70) &
                (scored.loc[scored_display.index, "renewal_window_90d"] == 1 if "renewal_window_90d" in scored.columns else False)
            ]
            summary["high_risk_in_window"] = len(high_in_window)

        return {
            "predictions": records,
            "total": len(scored),
            "showing": min(limit, len(scored_display)),
            "active_count": len(scored_display),
            "archived_count": len(scored) - len(scored_display),
            "tier_counts": tier_counts,
            "summary": summary,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/predict/{module_name}/export")
def export_predictions(module_name: str):
    mod = get_module(module_name)
    scored_path = os.path.join("outputs", f"{module_name}_scored.csv")
    if not os.path.exists(scored_path):
        raise HTTPException(status_code=404, detail="No scored predictions. Run predict first.")

    return FileResponse(scored_path, media_type="text/csv",
                        filename="churn_predictions.csv")


# -----------------------------------------------------------------------
# Account status management
# -----------------------------------------------------------------------
@app.post("/api/accounts/{customer_id}/status")
def update_account_status(customer_id: str, status: str = Query(...)):
    """Update account lifecycle status.

    Valid statuses: active, at_risk, save_in_progress, renewed, churned,
                    archived_renewed, archived_cancelled
    """
    valid = ["active", "at_risk", "save_in_progress", "renewed", "churned",
             "archived_renewed", "archived_cancelled"]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")

    _state["account_statuses"][customer_id] = status
    return {"customer_id": customer_id, "status": status}


@app.get("/api/accounts")
def list_accounts(status: Optional[str] = Query(None)):
    """List accounts with optional status filter."""
    predictions = _state["predictions"].get(MODULE_NAME, [])
    if status:
        # Filter by status from overrides or from predictions
        filtered = []
        for p in predictions:
            acct_status = _state["account_statuses"].get(
                p.get("customer_id"), p.get("account_status", "active")
            )
            if acct_status == status:
                filtered.append({**p, "account_status": acct_status})
        return {"accounts": filtered, "count": len(filtered)}

    return {"accounts": predictions, "count": len(predictions)}


# -----------------------------------------------------------------------
# API docs
# -----------------------------------------------------------------------
@app.get("/api/api-docs")
def api_docs_meta():
    return {
        "base_url": "http://localhost:8000",
        "endpoints": [
            {
                "method": "POST",
                "path": "/api/predict/churn",
                "description": "Score dataset and return churn risk predictions",
                "curl": 'curl -X POST http://localhost:8000/api/predict/churn',
                "response_example": {
                    "predictions": [
                        {"customer_id": "CUST-20042", "churn_risk_pct": 82.3,
                         "urgency_score": 91.5, "arr": 85000, "arr_at_risk": 69955,
                         "renewal_window_label": "<30d", "tier": "High Risk",
                         "recommended_action": "Executive save plan + renewal call this week"},
                    ],
                    "total": 2000,
                    "tier_counts": {"High Risk": 320, "Medium Risk": 580, "Low Risk": 1100},
                },
            },
            {
                "method": "POST",
                "path": "/api/train/churn",
                "description": "Train the churn risk model",
                "curl": 'curl -X POST "http://localhost:8000/api/train/churn?val_frac=0.2"',
                "response_example": {
                    "status": "trained",
                    "metadata": {"module": "churn", "version": "churn_v1",
                                 "n_train": 1600, "n_val": 400},
                },
            },
            {
                "method": "GET",
                "path": "/api/evaluate/churn",
                "description": "Get evaluation metrics for the trained model",
                "curl": "curl http://localhost:8000/api/evaluate/churn",
                "response_example": {
                    "auc": 0.812, "pr_auc": 0.785, "brier": 0.18,
                    "calibration_error": 0.03, "lift_at_top10": 5.2,
                },
            },
            {
                "method": "POST",
                "path": "/api/datasets/churn/sample",
                "description": "Load built-in sample churn dataset (2,000 accounts)",
                "curl": "curl -X POST http://localhost:8000/api/datasets/churn/sample",
            },
            {
                "method": "POST",
                "path": "/api/datasets/churn/upload",
                "description": "Upload a CSV dataset",
                "curl": 'curl -X POST -F "file=@customers.csv" http://localhost:8000/api/datasets/churn/upload',
            },
            {
                "method": "GET",
                "path": "/api/datasets/churn/current",
                "description": "Get metadata for the currently loaded dataset",
                "curl": "curl http://localhost:8000/api/datasets/churn/current",
                "response_example": {
                    "name": "churn_sample.csv", "rows": 2000, "columns": 16,
                    "is_demo": True, "loaded_at": "2026-02-23T21:00:00+00:00",
                },
            },
            {
                "method": "POST",
                "path": "/api/evaluate/churn/report",
                "description": "Download PDF churn risk report",
                "curl": "curl -o report.pdf -X POST http://localhost:8000/api/evaluate/churn/report",
            },
            {
                "method": "POST",
                "path": "/api/accounts/{customer_id}/status",
                "description": "Update account lifecycle status",
                "curl": 'curl -X POST "http://localhost:8000/api/accounts/CUST-20042/status?status=save_in_progress"',
            },
            {
                "method": "GET",
                "path": "/api/accounts",
                "description": "List accounts with optional status filter",
                "curl": "curl http://localhost:8000/api/accounts?status=at_risk",
            },
        ],
    }


# -----------------------------------------------------------------------
# Onboarding
# -----------------------------------------------------------------------
ONBOARDING_STEPS = [
    {"id": "kickoff", "label": "Kickoff Call", "description": "Align on goals, data requirements, and timeline"},
    {"id": "template", "label": "Data Template Sent", "description": "CSV template with required customer fields"},
    {"id": "data_received", "label": "Data Received", "description": "Customer uploads their churn dataset"},
    {"id": "validation", "label": "Validation Complete", "description": "Data quality and schema checks passed"},
    {"id": "trained", "label": "Model Trained", "description": "Churn model trained and evaluated on your data"},
    {"id": "backtest", "label": "Backtest Delivered", "description": "Performance report shared with stakeholders"},
    {"id": "deployment", "label": "Deployment Mode Chosen", "description": "Batch scoring or API integration"},
    {"id": "live", "label": "Live Scoring Enabled", "description": "Churn predictions running in production"},
    {"id": "retraining", "label": "Monthly Retraining Scheduled", "description": "Automated model refresh cadence set"},
]

_onboarding_state: Dict[str, str] = {}


@app.get("/api/onboarding")
def get_onboarding():
    steps = []
    for step in ONBOARDING_STEPS:
        steps.append({
            **step,
            "status": _onboarding_state.get(step["id"], "pending"),
        })
    return {"steps": steps}


@app.post("/api/onboarding/{step_id}/complete")
def complete_onboarding_step(step_id: str):
    valid_ids = [s["id"] for s in ONBOARDING_STEPS]
    if step_id not in valid_ids:
        raise HTTPException(status_code=404, detail=f"Unknown step: {step_id}")
    _onboarding_state[step_id] = "complete"
    return {"step_id": step_id, "status": "complete"}


@app.post("/api/onboarding/{step_id}/reset")
def reset_onboarding_step(step_id: str):
    _onboarding_state[step_id] = "pending"
    return {"step_id": step_id, "status": "pending"}


@app.get("/api/onboarding/template/{module_name}")
def download_data_template(module_name: str):
    mod = get_module(module_name)
    cols = mod.required_columns + mod.optional_columns
    df = pd.DataFrame(columns=cols)
    path = f"outputs/{module_name}_template.csv"
    os.makedirs("outputs", exist_ok=True)
    df.to_csv(path, index=False)
    return FileResponse(path, media_type="text/csv",
                        filename="churn_data_template.csv")


# -----------------------------------------------------------------------
# Dashboard summary (churn-specific)
# -----------------------------------------------------------------------
@app.get("/api/dashboard")
def dashboard_summary(save_rate: float = Query(0.35, ge=0.05, le=0.95)):
    mod = get_module("churn")
    meta_path = os.path.join(mod.artifact_dir, "metadata.json")
    metadata = None
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            metadata = json.load(f)

    metrics = _state["metrics"].get("churn")
    if not metrics:
        eval_path = os.path.join("outputs", "churn_evaluation.json")
        if os.path.exists(eval_path):
            with open(eval_path) as f:
                metrics = json.load(f)

    predictions = _state["predictions"].get("churn", [])

    # Compute summary KPIs from cached predictions
    total_arr_at_risk = 0.0
    renewing_90d = 0
    high_risk_in_window = 0
    for p in predictions:
        arr_r = p.get("arr_at_risk", 0) or 0
        total_arr_at_risk += arr_r
        if p.get("renewal_window_label") in ("<30d", "30-90d"):
            renewing_90d += 1
            if (p.get("churn_risk_pct") or 0) >= 70:
                high_risk_in_window += 1

    # Top 10 at-risk accounts
    top_10 = sorted(predictions, key=lambda x: x.get("arr_at_risk", 0) or 0, reverse=True)[:10]

    ds = _get_dataset("churn")

    return {
        "module": {
            "name": "churn",
            "display_name": mod.display_name,
            "has_model": os.path.exists(os.path.join(mod.artifact_dir, "model.joblib")),
            "has_dataset": ds is not None,
            "trained_at": metadata.get("trained_at") if metadata else None,
            "version": metadata.get("version") if metadata else None,
            "auc": metrics.get("auc") if metrics else None,
            "calibration_error": metrics.get("calibration_error") if metrics else None,
            "lift_at_top10": metrics.get("lift_at_top10") if metrics else None,
            "n_train": metadata.get("n_train") if metadata else None,
        },
        "dataset": ds,
        "kpis": {
            "total_arr_at_risk": round(total_arr_at_risk, 2),
            "projected_recoverable_arr": round(total_arr_at_risk * save_rate, 2),
            "assumed_save_rate": save_rate,
            "renewing_90d": renewing_90d,
            "high_risk_in_window": high_risk_in_window,
        },
        "top_at_risk": top_10,
    }


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------
def _get_adapter(module_name: str):
    try:
        if module_name == "churn":
            from .modules.churn import adapter as mod
        else:
            return None
        return mod
    except ImportError:
        return None


def _validation_to_dict(v: ValidationResult) -> dict:
    return {
        "valid": v.valid,
        "module": v.module,
        "n_rows": v.n_rows,
        "n_columns": v.n_columns,
        "missing_required": v.missing_required,
        "warnings": v.warnings,
        "errors": v.errors,
        "label_distribution": v.label_distribution,
        "columns": [
            {
                "name": c.name,
                "dtype": c.dtype,
                "missing_count": c.missing_count,
                "missing_pct": c.missing_pct,
                "n_unique": c.n_unique,
                "sample_values": [str(v) for v in c.sample_values[:3]],
            }
            for c in v.columns
        ],
    }

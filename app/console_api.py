"""Churn Risk Engine — Console API (FastAPI backend)."""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

_SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if _SENTRY_DSN:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=0.1,
        environment=os.environ.get("ENVIRONMENT", "production"),
    )

logger = logging.getLogger("pickpulse.api")
from pydantic import BaseModel as PydanticBaseModel, Field, field_validator


class FieldMappingItem(PydanticBaseModel):
    source_field: str
    target_field: str
    transform: str = "direct"

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from .auth import get_tenant_id, _decode_token

from .engine.config import MODULES, get_module, ModuleConfig
from .engine.schema import validate_dataset, ValidationResult
from .engine.sample_data import generate_churn_dataset, DEMO_GENERATORS
from .engine.train import train_model
from .engine.evaluate import evaluate_model, generate_pdf_report
from .engine.predict import predict, load_model
from .engine import store

# Integration layer
from .integrations.models import ConnectorConfig, ConnectorStatus
from .integrations import registry as connector_registry
from .integrations.sync import sync_connector, sync_all
from .integrations.scoring import score_accounts
from .demo_seed import auto_seed_if_needed
from .demo import DemoModeResolver
try:
    from .integrations import service as integration_service
except Exception:
    integration_service = None  # type: ignore[assignment]
from .storage import repo as storage_repo
from .outreach import router as outreach_router
from .explain import router as explain_router
from .executive_summary import router as executive_summary_router
from .revenue_impact import compute_revenue_impact
from .expansion_demo import router as expansion_demo_router
from .arr_command_center_api import router as arr_command_center_router
try:
    from .hubspot_card import router as hubspot_card_router
    _hubspot_card_available = True
except Exception:
    _hubspot_card_available = False

app = FastAPI(title="Churn Risk Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(outreach_router)
app.include_router(explain_router)
app.include_router(executive_summary_router)
app.include_router(expansion_demo_router)
app.include_router(arr_command_center_router)
if _hubspot_card_available:
    app.include_router(hubspot_card_router)


# ---------------------------------------------------------------------------
# Sentry tenant context middleware
# Attaches the authenticated tenant_id to every Sentry event so errors can
# be correlated with specific tenants in the Sentry dashboard.
# ---------------------------------------------------------------------------
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest


class _SentryTenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        # Best-effort: extract tenant from Authorization header without re-running full
        # auth flow. If it fails, Sentry events still capture but lack tenant tag.
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                payload = _decode_token(auth_header[7:])
                tenant_id = payload.get("sub", "unknown")
                sentry_sdk.set_tag("tenant_id", tenant_id)
        except Exception:
            pass
        return await call_next(request)


if _SENTRY_DSN:
    app.add_middleware(_SentryTenantMiddleware)


@app.on_event("startup")
async def _startup():
    """Clean up jobs that were running when the previous process was killed."""
    store.fail_stale_model_runs(older_than_minutes=60)
    # Verify shap is importable at startup so failures surface immediately in logs
    try:
        import shap as _shap  # noqa: F401
        logger.info("startup: shap %s available", getattr(_shap, "__version__", "unknown"))
    except ImportError:
        logger.error(
            "startup: shap package NOT installed — per-account SHAP drivers will be disabled. "
            "Add 'shap' to requirements.txt and redeploy."
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
DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("true", "1")

# Central demo/live mode resolver.  All CRM demo-mode logic routes through here.
# See app/demo/resolver.py for the provider resolution table.
demo_resolver = DemoModeResolver(demo_mode=DEMO_MODE)

# Ensure subdirectories exist at startup.
# Do NOT call makedirs on DATA_DIR itself — on Render, /data is the persistent
# disk mount point created and owned by the platform. Attempting to create it
# raises PermissionError. Only create directories *inside* DATA_DIR.
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
    """Save dataset registry to disk (kept for backward-compat flush on first run)."""
    # DATA_DIR itself is the mount root on Render — do not call makedirs on it.
    # UPLOAD_DIR and SAMPLE_DIR are already created at startup; DATA_DIR exists.
    with open(DATASET_STATE_PATH, "w") as f:
        json.dump(datasets, f, indent=2)


# Per-tenant in-memory state.
# predictions and account_statuses are loaded from Supabase (store.py) on first
# access. If Supabase is not configured, they start empty (local dev).
# train_logs and metrics remain in-memory with fallback to _evaluation.json on disk.
_tenant_state: Dict[str, Dict[str, Any]] = {}

# Default tenant for backward compatibility during migration
_DEFAULT_TENANT = "00000000-0000-0000-0000-000000000000"


def _get_state(tenant_id: str) -> Dict[str, Any]:
    """Get or create per-tenant state, loading durable state from store on first access."""
    if tenant_id not in _tenant_state:
        loaded_preds = store.get_predictions(tenant_id, MODULE_NAME)
        # Derive when those predictions were generated so staleness checks work on cold start.
        preds_generated_at = (
            max((p.get("_predicted_at", "") for p in loaded_preds), default="")
            if loaded_preds else ""
        )
        _tenant_state[tenant_id] = {
            "datasets": _load_persisted_datasets(),  # flat JSON, migrated to store below
            "train_logs": {},
            "metrics": {},
            "predictions": {MODULE_NAME: loaded_preds},
            "predictions_generated_at": preds_generated_at,
            "account_statuses": store.get_account_statuses(tenant_id),
            "model_runs": {},  # in-memory fallback when Supabase writes are unavailable
        }
    return _tenant_state[tenant_id]


def _register_dataset(module_name: str, info: Dict[str, Any], tenant_id: str = _DEFAULT_TENANT) -> None:
    """Register a dataset in memory, on disk, and in Supabase (store.py)."""
    state = _get_state(tenant_id)
    state["datasets"][module_name] = info
    _save_persisted_datasets(state["datasets"])  # flat JSON (backward compat, stays until Phase 3)
    store.save_dataset(tenant_id, module_name, info)
    store.log_action(tenant_id, "dataset.register", entity_id=module_name,
                     metadata={"filename": info.get("name"), "rows": info.get("rows")})


def _get_dataset(module_name: str, tenant_id: str = _DEFAULT_TENANT) -> Optional[Dict[str, Any]]:
    """Get dataset info, validating the file still exists on disk.

    Checks the memory cache first (populated by _register_dataset or flat JSON),
    then falls back to Supabase via store.get_current_dataset().
    """
    state = _get_state(tenant_id)
    ds = state["datasets"].get(module_name)
    if not ds:
        # Cache miss — try store (handles restarts before flat JSON is migrated)
        ds = store.get_current_dataset(tenant_id, module_name)
        if ds:
            state["datasets"][module_name] = ds
    if ds and ds.get("path") and os.path.exists(ds["path"]):
        return ds
    return None


def _predictions_are_stale(state: Dict[str, Any], module_name: str, tenant_id: str) -> bool:
    """Return True if the cached predictions pre-date the current dataset registration.

    Prevents stale predictions from a prior dataset/model context being served as
    if they belong to the currently loaded dataset.
    """
    ds = _get_dataset(module_name, tenant_id=tenant_id)
    if not ds:
        return False  # no dataset loaded — nothing to validate against
    dataset_ts = ds.get("registered_at") or ds.get("loaded_at", "")
    if not dataset_ts:
        return False
    preds_ts = state.get("predictions_generated_at", "")
    # No timestamp means predictions arrived from a pre-fix DB row; treat as stale.
    return not preds_ts or preds_ts < dataset_ts


def _tenant_output_dir(tenant_id: str) -> str:
    """Return tenant-scoped output directory under DATA_DIR, creating it if needed."""
    d = os.path.join(os.environ.get("DATA_DIR", "data"), "outputs", tenant_id)
    os.makedirs(d, exist_ok=True)
    return d


# -----------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "service": "Churn Risk Engine"}


@app.get("/api/auth/whoami")
async def whoami(tenant_id: str = Depends(get_tenant_id)):
    """Smoke-test: return the authenticated tenant info."""
    return {"tenant_id": tenant_id}


# -----------------------------------------------------------------------
# Active mode — authoritative workflow selection (salesforce / hubspot / csv / none)
# -----------------------------------------------------------------------

_VALID_MODES = frozenset({"salesforce", "hubspot", "csv", "none"})


@app.get("/api/mode")
def get_mode(tenant_id: str = Depends(get_tenant_id)):
    """Return the current active workflow mode for this tenant.

    Maps the raw active_source value to one of the four canonical mode names:
      salesforce | hubspot | csv | none

    'none' is returned whenever the source is absent, invalid, or the generic
    'crm' string (which carries no provider information and cannot be used for
    filtered queries).
    """
    source = _get_active_source(tenant_id)
    if source in ("salesforce", "hubspot"):
        mode = source
    elif source in ("csv", "dataset"):
        mode = "csv"
    else:
        mode = "none"
    return {"mode": mode}


@app.post("/api/mode")
def set_mode(body: Dict[str, Any], tenant_id: str = Depends(get_tenant_id)):
    """Set the active workflow mode.

    Valid values: 'salesforce', 'hubspot', 'csv', 'none'.
    Setting 'none' removes the context file entirely so a fresh page load
    returns the user to the welcome / source-selection experience.
    """
    mode = body.get("mode")
    if mode not in _VALID_MODES:
        raise HTTPException(status_code=422, detail=f"Invalid mode '{mode}'. Must be one of: {sorted(_VALID_MODES)}")

    if mode == "none":
        # Clear the context file so the next mode-check returns 'none'
        try:
            p = _source_context_path(tenant_id)
            if os.path.exists(p):
                os.remove(p)
        except Exception as exc:
            logger.warning("[set_mode] could not remove context file: %s", exc)
    else:
        _set_active_source(tenant_id, mode)

    return {"mode": mode}


# -----------------------------------------------------------------------
# Demo Reset
# -----------------------------------------------------------------------
@app.post("/api/demo/reset")
def reset_demo(tenant_id: str = Depends(get_tenant_id)):
    """Reset the environment to a clean first-time state for the current tenant."""

    cleared: list[str] = []

    # 1. Clear in-memory state (datasets, predictions, metrics, account statuses, train logs)
    if tenant_id in _tenant_state:
        _tenant_state.pop(tenant_id)
        cleared.extend(["dataset", "predictions", "metrics"])

    # 2. Clear persisted dataset registry (tenant-scoped keys only)
    persisted = _load_persisted_datasets()
    if any(k in persisted for k in MODULES):
        for k in list(MODULES.keys()):
            persisted.pop(k, None)
        _save_persisted_datasets(persisted)
        if "dataset" not in cleared:
            cleared.append("dataset")

    # 3. Delete tenant-scoped uploads (prefix: {tenant_id[:8]}_)
    prefix = f"{tenant_id[:8]}_"
    if os.path.exists(UPLOAD_DIR):
        for fname in os.listdir(UPLOAD_DIR):
            if fname.startswith(prefix):
                try:
                    os.remove(os.path.join(UPLOAD_DIR, fname))
                except OSError:
                    pass

    # 4. Delete model artifacts (tenant-scoped directory)
    for mod in MODULES.values():
        artifact_dir = mod.get_artifact_dir(tenant_id)
        if os.path.exists(artifact_dir):
            shutil.rmtree(artifact_dir, ignore_errors=True)
            if "model" not in cleared:
                cleared.append("model")

    # 5. Delete tenant-scoped outputs
    tenant_out = _tenant_output_dir(tenant_id)
    if os.path.exists(tenant_out):
        shutil.rmtree(tenant_out, ignore_errors=True)
        cleared.append("outputs")

    # 6. Clear notification settings
    from .executive_summary import clear_tenant_settings
    clear_tenant_settings(tenant_id)
    cleared.append("notifications")

    # 7. Delete persisted predictions from Supabase so a cold-start after reset
    #    does not re-inject stale predictions into _get_state().
    store.delete_tenant_predictions(tenant_id)
    cleared.append("predictions_live")

    # 8. In demo mode, clear all Supabase CRM data for synthetic providers so
    #    the next demo run starts from a truly clean state.  Without this, the
    #    DemoDataLoader's idempotency guard would find the old synthetic accounts
    #    and skip re-loading, which prevents cross-provider switching from
    #    working cleanly (e.g., HubSpot → reset → Salesforce).
    if DEMO_MODE:
        for _provider in ("hubspot", "salesforce"):
            try:
                _counts = storage_repo.clear_provider_data(_provider, tenant_id)
                logger.info("[reset] cleared %s CRM data: %s", _provider, _counts)
                if any(v > 0 for v in _counts.values()):
                    cleared.append(f"crm_{_provider}")
            except Exception as _exc:
                logger.warning("[reset] clear_provider_data(%s) failed: %s", _provider, _exc)

    return {"status": "reset", "tenant_id": tenant_id, "cleared": cleared}


# -----------------------------------------------------------------------
# Modules
# -----------------------------------------------------------------------
@app.get("/api/modules")
def list_modules(tenant_id: str = Depends(get_tenant_id)):
    result = []
    for name, mod in MODULES.items():
        artifact_dir = mod.get_artifact_dir(tenant_id)
        has_model = os.path.exists(os.path.join(artifact_dir, "model.joblib"))
        metadata = None
        if has_model:
            meta_path = os.path.join(artifact_dir, "metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    metadata = json.load(f)

        ds = _get_dataset(name, tenant_id=tenant_id)
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
def get_module_detail(module_name: str, tenant_id: str = Depends(get_tenant_id)):
    mod = get_module(module_name)
    artifact_dir = mod.get_artifact_dir(tenant_id)
    has_model = os.path.exists(os.path.join(artifact_dir, "model.joblib"))

    metadata = None
    if has_model:
        meta_path = os.path.join(artifact_dir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                metadata = json.load(f)

    state = _get_state(tenant_id)
    ds = _get_dataset(mod.name, tenant_id=tenant_id)
    return {
        "name": mod.name,
        "display_name": mod.display_name,
        "has_model": has_model,
        "has_dataset": ds is not None,
        "dataset_info": ds,
        "metadata": metadata,
        "metrics": state["metrics"].get(mod.name),
        "required_columns": mod.required_columns,
        "optional_columns": mod.optional_columns,
    }


# -----------------------------------------------------------------------
# Dataset upload
# -----------------------------------------------------------------------
@app.post("/api/datasets/{module_name}/upload")
async def upload_dataset(module_name: str, file: UploadFile = File(...), tenant_id: str = Depends(get_tenant_id)):
    """
    Stage 1 of the upload flow: store the raw CSV and return mapping suggestions.
    The dataset is NOT registered until confirm-mapping is called.
    """
    get_module(module_name)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    raw_filename = f"{tenant_id[:8]}_{module_name}_{uuid.uuid4().hex[:8]}_raw.csv"
    raw_filepath = os.path.join(UPLOAD_DIR, raw_filename)

    with open(raw_filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        df = pd.read_csv(raw_filepath)
    except Exception as e:
        os.remove(raw_filepath)
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    from .engine.schema_mapping import suggest_mapping, mapping_suggestion_to_dict
    suggestion = suggest_mapping(df)

    # 5-row sample for the UI preview
    sample_rows = df.head(5).where(pd.notna(df.head(5)), None).to_dict(orient="records")

    return {
        "status": "staged",
        "raw_path": raw_filepath,
        "filename": file.filename or raw_filename,
        "n_rows": len(df),
        "n_columns": len(df.columns),
        "source_columns": list(df.columns),
        "sample_rows": sample_rows,
        "mapping_suggestion": mapping_suggestion_to_dict(suggestion),
    }


@app.post("/api/datasets/{module_name}/confirm-mapping")
async def confirm_mapping(
    module_name: str,
    body: dict,
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Stage 2 of the upload flow: accept confirmed mapping, normalize, and register the dataset.
    Body: { raw_path: str, confirmed_mappings: { canonical: source_or_null } }
    """
    mod = get_module(module_name)

    raw_path: str = body.get("raw_path", "")
    confirmed_mappings: dict = body.get("confirmed_mappings", {})

    # Security: ensure raw_path is within UPLOAD_DIR
    upload_dir_abs = os.path.abspath(UPLOAD_DIR)
    raw_path_abs = os.path.abspath(raw_path)
    if not raw_path_abs.startswith(upload_dir_abs + os.sep):
        raise HTTPException(status_code=400, detail="Invalid raw_path.")
    if not os.path.exists(raw_path_abs):
        raise HTTPException(status_code=400, detail="Raw file not found. Re-upload the CSV.")

    try:
        raw_df = pd.read_csv(raw_path_abs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {e}")

    from .engine.normalizer import normalize, compute_readiness, readiness_to_dict

    norm_result = normalize(raw_df, confirmed_mappings)
    canonical_df = norm_result.canonical_df

    # Store the normalized CSV — this becomes the registered dataset path
    norm_filename = os.path.basename(raw_path_abs).replace("_raw.csv", ".csv")
    norm_filepath = os.path.join(UPLOAD_DIR, norm_filename)
    canonical_df.to_csv(norm_filepath, index=False)

    # Store the confirmed mapping in the artifact directory for reuse at predict time
    artifact_dir = mod.get_artifact_dir(tenant_id)
    os.makedirs(artifact_dir, exist_ok=True)
    mapping_path = os.path.join(artifact_dir, "mapping.json")
    with open(mapping_path, "w") as mf:
        json.dump({
            "confirmed_mappings": confirmed_mappings,
            "derived_columns": norm_result.derived_columns,
            "coercion_log": norm_result.coercion_log,
        }, mf, indent=2)

    # Compute readiness before registering so we can persist the mode
    loaded_at = datetime.now(timezone.utc).isoformat()
    original_filename = body.get("filename", norm_filename)

    readiness = compute_readiness(
        canonical_df=canonical_df,
        derived_columns=norm_result.derived_columns,
        warnings=norm_result.warnings,
        n_rows=len(canonical_df),
        filename=original_filename,
        loaded_at=loaded_at,
    )

    # Register the normalized dataset — include readiness_mode so the Train
    # page can check whether training is possible without re-normalizing.
    ds_info = {
        "path": norm_filepath,
        "name": original_filename,
        "rows": len(canonical_df),
        "columns": len(canonical_df.columns),
        "is_demo": False,
        "loaded_at": loaded_at,
        "readiness_mode": readiness.mode,
    }
    _register_dataset(module_name, ds_info, tenant_id=tenant_id)

    # Embed dataset_info into the readiness report
    readiness.dataset_info = ds_info

    return {
        "status": "confirmed",
        "readiness": readiness_to_dict(readiness),
        "coercion_log": norm_result.coercion_log,
        "dataset_info": ds_info,
    }


@app.get("/api/datasets/{module_name}/canonical-schema")
def get_canonical_schema(module_name: str):
    """Return the canonical schema definition for the mapping UI."""
    get_module(module_name)
    from .engine.schema_mapping import CANONICAL_SCHEMA, ALIAS_MAP
    fields = []
    for name, fd in CANONICAL_SCHEMA.items():
        fields.append({
            "name": name,
            "required_for_training": fd.required_for_training,
            "required_for_analysis": fd.required_for_analysis,
            "label_column": fd.label_column,
            "display_only": fd.display_only,
            "derivable_from": fd.derivable_from,
            "description": fd.description,
            "aliases_preview": ALIAS_MAP.get(name, [])[:4],
        })
    return {"fields": fields}


@app.post("/api/datasets/{module_name}/sample")
def load_sample_dataset(
    module_name: str,
    variant: str = Query("balanced", pattern="^(balanced|high_risk|enterprise)$"),
    tenant_id: str = Depends(get_tenant_id),
):
    mod = get_module(module_name)
    os.makedirs(SAMPLE_DIR, exist_ok=True)

    if module_name != "churn":
        raise HTTPException(status_code=400, detail="Only churn module is available")

    generator = DEMO_GENERATORS.get(variant, DEMO_GENERATORS["balanced"])
    df = generator()

    variant_names = {
        "balanced": "Balanced Demo",
        "high_risk": "High-Risk Demo",
        "enterprise": "Enterprise Demo",
    }
    display_name = variant_names.get(variant, "Balanced Demo")

    filepath = os.path.join(SAMPLE_DIR, f"{module_name}_sample.csv")
    df.to_csv(filepath, index=False)

    # Validate the normalized form so demo datasets that use column aliases
    # (e.g. customer_id → account_id) don't show a misleading warning state.
    # The raw CSV is kept as-is; the adapter handles normalization at training time.
    df_for_validation = df
    _adapter = _get_adapter(module_name)
    if _adapter:
        df_for_validation = _adapter.normalize_columns(df.copy())
    validation = validate_dataset(df_for_validation, mod)

    # Store a trivial identity mapping for sample data so predict-time
    # normalization always has a mapping.json to load.
    artifact_dir = mod.get_artifact_dir(tenant_id)
    os.makedirs(artifact_dir, exist_ok=True)
    trivial_mapping = {col: col for col in df.columns}
    with open(os.path.join(artifact_dir, "mapping.json"), "w") as mf:
        json.dump({
            "confirmed_mappings": trivial_mapping,
            "derived_columns": [],
            "coercion_log": ["Sample data: identity mapping (canonical column names)"],
        }, mf, indent=2)

    loaded_at = datetime.now(timezone.utc).isoformat()
    ds_info = {
        "path": filepath,
        "name": display_name,
        "rows": len(df),
        "columns": len(df.columns),
        "is_demo": True,
        "loaded_at": loaded_at,
        "readiness_mode": "TRAINING_READY",
    }
    _register_dataset(module_name, ds_info, tenant_id=tenant_id)

    return {
        "status": "loaded",
        "validation": _validation_to_dict(validation),
        "dataset_info": ds_info,
    }


@app.get("/api/datasets/{module_name}/current")
def get_current_dataset(module_name: str, tenant_id: str = Depends(get_tenant_id)):
    """Return metadata for the currently loaded dataset (or 404)."""
    get_module(module_name)  # validate module name
    ds = _get_dataset(module_name, tenant_id=tenant_id)
    if not ds:
        raise HTTPException(status_code=404, detail="No dataset loaded.")
    return ds


@app.get("/api/datasets/{module_name}/validate")
def validate_current_dataset(module_name: str, tenant_id: str = Depends(get_tenant_id)):
    mod = get_module(module_name)
    ds = _get_dataset(module_name, tenant_id=tenant_id)
    if not ds:
        raise HTTPException(status_code=404, detail="No dataset loaded.")

    df = pd.read_csv(ds["path"])
    validation = validate_dataset(df, mod)
    return _validation_to_dict(validation)


# -----------------------------------------------------------------------
# Training — DB-backed job tracking with in-process worker execution
#
# The train endpoint returns 202 immediately with a job_id. A daemon thread
# executes training in the background. Job lifecycle is tracked in the
# model_runs table via store.py.
#
# NOTE: This architecture assumes a single process / single instance. If
# Render is ever scaled to multiple dynos, replace the daemon thread with
# dequeue semantics (worker picks up 'pending' rows from model_runs).
# -----------------------------------------------------------------------

def _execute_training_job(
    tenant_id: str,
    module_name: str,
    run_id: str,
    dataset_path: str,
    val_frac: float,
    artifact_dir: str,
    version_str: str,
) -> None:
    """Background worker — runs in a daemon thread. Updates model_run status."""

    def _update_mem(run_id: str, **fields) -> None:
        """Mirror a status update into in-memory state (always succeeds)."""
        mem = _get_state(tenant_id).get("model_runs", {}).get(run_id)
        if mem is not None:
            mem.update(fields)

    try:
        started = datetime.now(timezone.utc)
        store.update_model_run(run_id, status="running", started_at=started)
        _update_mem(run_id, status="running", started_at=started.isoformat())

        mod = get_module(module_name)
        df = pd.read_csv(dataset_path)
        adapter = _get_adapter(module_name)
        if adapter:
            df = adapter.normalize_columns(df)
            df = adapter.add_derived_features(df)

        metadata = train_model(df, mod, val_frac=val_frac, tenant_id=tenant_id, run_id=run_id,
                               version_str=version_str)

        if "error" in metadata:
            raise RuntimeError(metadata.get("message", metadata["error"]))

        # Auto-evaluate on val split.
        # Pre-load the model from the explicit artifact_dir so evaluate_model
        # doesn't fall back to get_artifact_dir(tenant_id) (no run_id), which
        # points to a path where nothing was written.
        loaded_artifacts = load_model(mod, artifact_dir=artifact_dir)

        state = _get_state(tenant_id)
        ts_col = mod.timestamp_column
        metrics = None
        if ts_col in df.columns:
            df_sorted = df.copy()
            df_sorted["_ts"] = pd.to_datetime(df_sorted[ts_col], errors="coerce")
            df_sorted = df_sorted.sort_values("_ts").drop(columns=["_ts"])
            split_idx = int(len(df_sorted) * (1 - val_frac))
            val_df = df_sorted.iloc[split_idx:]
            if adapter:
                val_df = adapter.add_derived_features(val_df)
            if len(val_df) >= 10:
                metrics = evaluate_model(val_df, mod, tenant_id=tenant_id,
                                         artifacts=loaded_artifacts)
                state["metrics"][module_name] = metrics
                eval_path = os.path.join(_tenant_output_dir(tenant_id), f"{module_name}_evaluation.json")
                with open(eval_path, "w") as ef:
                    json.dump(metrics, ef, indent=2)
        if metrics is None and metadata.get("val_metrics"):
            metrics = metadata["val_metrics"]
            state["metrics"][module_name] = metrics
            eval_path = os.path.join(_tenant_output_dir(tenant_id), f"{module_name}_evaluation.json")
            with open(eval_path, "w") as ef:
                json.dump(metrics, ef, indent=2)

        # Mark complete and promote to current version
        completed = datetime.now(timezone.utc)
        final_metrics = metrics or metadata.get("val_metrics")
        store.update_model_run(
            run_id,
            status="complete",
            version_str=metadata.get("version"),
            metrics_json=final_metrics,
            artifact_path=artifact_dir,
            completed_at=completed,
        )
        _update_mem(run_id, status="complete", version_str=metadata.get("version"),
                    metrics_json=final_metrics, completed_at=completed.isoformat())
        store.set_current_model_run(tenant_id, module_name, run_id)
        store.log_action(tenant_id, "model.train_complete", entity_id=run_id,
                         metadata={"version": metadata.get("version"),
                                   "artifact_path": artifact_dir})

    except Exception as exc:
        traceback.print_exc()
        failed_at = datetime.now(timezone.utc)
        store.update_model_run(
            run_id,
            status="failed",
            error_message=str(exc),
            completed_at=failed_at,
        )
        _update_mem(run_id, status="failed", error_message=str(exc),
                    completed_at=failed_at.isoformat())
        sentry_sdk.capture_exception(exc)


@app.post("/api/train/{module_name}", status_code=202)
def train_module(module_name: str, val_frac: float = Query(0.2), tenant_id: str = Depends(get_tenant_id)):
    """Start a training job. Returns 202 immediately with job_id; poll /status for progress."""
    mod = get_module(module_name)
    ds = _get_dataset(module_name, tenant_id=tenant_id)
    if not ds:
        raise HTTPException(status_code=400, detail="No dataset loaded. Upload or load sample first.")

    # Validate dataset before kicking off background job (fast, synchronous)
    try:
        df_check = pd.read_csv(ds["path"])
        adapter = _get_adapter(module_name)
        if adapter:
            df_check = adapter.normalize_columns(df_check)
            df_check = adapter.add_derived_features(df_check)
        from .engine.schema import validate_dataset
        validation = validate_dataset(df_check, mod)
        if not validation.valid:
            raise HTTPException(
                status_code=400,
                detail="; ".join(validation.errors) or "Dataset failed validation. Check required columns.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Viability gate — only blocks if a completed audit explicitly says "blocked".
    # Tenants using CSV uploads (no HubSpot audit) are unaffected.
    try:
        from app.integrations.label_auditor import load_audit as _load_viability
        _viability = _load_viability(tenant_id)
        if _viability and _viability.get("viability") == "blocked":
            raise HTTPException(
                status_code=412,
                detail={
                    "message": "Training blocked: insufficient labeled data in connected HubSpot portal.",
                    "viability": "blocked",
                    "rationale": _viability.get("decision", {}).get("rationale", ""),
                    "next_steps": _viability.get("decision", {}).get("next_steps", []),
                    "audit_at": _viability.get("audit_at"),
                },
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Never let the viability check block CSV-based training

    run_id = str(uuid.uuid4())
    artifact_dir = mod.get_artifact_dir(tenant_id, run_id=run_id)
    store.create_model_run(tenant_id, module_name, run_id, artifact_dir)

    # Mirror to in-memory state so the status endpoint works even when the
    # Supabase insert above fails silently (e.g. env vars not set on demo server).
    _get_state(tenant_id)["model_runs"][run_id] = {
        "id": run_id, "tenant_id": tenant_id, "module": module_name,
        "status": "pending", "trained_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None, "completed_at": None,
        "version_str": None, "metrics_json": None, "error_message": None,
    }

    # Derive version string from durable run history before spawning the thread.
    # Only completed runs count; failed/pending runs do not consume a version number.
    completed_count = sum(
        1 for r in store.list_model_runs(tenant_id, module_name)
        if r.get("status") == "complete"
    )
    version_str = f"{module_name}_v{completed_count + 1}"

    store.log_action(tenant_id, "model.train_start", entity_id=run_id,
                     metadata={"module": module_name, "val_frac": val_frac,
                                "version_str": version_str})

    threading.Thread(
        target=_execute_training_job,
        args=(tenant_id, module_name, run_id, ds["path"], val_frac, artifact_dir, version_str),
        daemon=True,
        name=f"train-{run_id[:8]}",
    ).start()

    return {"job_id": run_id, "status": "pending"}


@app.get("/api/train/{module_name}/status/{job_id}")
def training_job_status(module_name: str, job_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Poll training job status. Returns status + metrics when complete."""
    get_module(module_name)  # validate module
    run = store.get_model_run(job_id, tenant_id=tenant_id)
    if not run:
        # Fall back to in-memory state — covers the case where create_model_run
        # failed silently (Supabase env vars absent or connection error).
        run = _get_state(tenant_id).get("model_runs", {}).get(job_id)
    if not run:
        raise HTTPException(status_code=404, detail="Training job not found.")

    # Inline stale-job cleanup: mark abandoned jobs failed without waiting for
    # the next server restart. Handles the common case where a Render deploy
    # killed the daemon thread mid-flight, leaving the row stuck in "pending".
    status = run.get("status")
    now_utc = datetime.now(timezone.utc)
    if status == "pending":
        trained_at_str = run.get("trained_at")
        if trained_at_str:
            try:
                trained_at = datetime.fromisoformat(trained_at_str.replace("Z", "+00:00"))
                if (now_utc - trained_at).total_seconds() > 120:  # 2 minutes
                    store.update_model_run(
                        job_id,
                        status="failed",
                        error_message="Training job was never picked up — the server may have restarted. Please try again.",
                        completed_at=now_utc,
                    )
                    run["status"] = "failed"
                    run["error_message"] = "Training job was never picked up — the server may have restarted. Please try again."
            except (ValueError, TypeError):
                pass
    elif status == "running":
        started_at_str = run.get("started_at")
        if started_at_str:
            try:
                started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                if (now_utc - started_at).total_seconds() > 3600:  # 60 minutes
                    store.update_model_run(
                        job_id,
                        status="failed",
                        error_message="Training timed out after 60 minutes. Please try again.",
                        completed_at=now_utc,
                    )
                    run["status"] = "failed"
                    run["error_message"] = "Training timed out after 60 minutes. Please try again."
            except (ValueError, TypeError):
                pass

    return {
        "job_id": job_id,
        "status": run.get("status"),
        "version_str": run.get("version_str"),
        "metrics": run.get("metrics_json"),
        "error_message": run.get("error_message"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
    }


# -----------------------------------------------------------------------
# Evaluation
# -----------------------------------------------------------------------
@app.get("/api/evaluate/{module_name}")
def get_evaluation(module_name: str, tenant_id: str = Depends(get_tenant_id)):
    mod = get_module(module_name)
    state = _get_state(tenant_id)
    metrics = state["metrics"].get(module_name)

    if not metrics:
        report_path = os.path.join(_tenant_output_dir(tenant_id), f"{module_name}_evaluation.json")
        if os.path.exists(report_path):
            with open(report_path) as f:
                metrics = json.load(f)
            state["metrics"][module_name] = metrics

    if not metrics:
        # Resolve artifact dir from current model run (post-3A versioned path)
        # with legacy fallback for models trained before PR 3A.
        current_run = store.get_current_model_run(tenant_id, module_name)
        if current_run and current_run.get("artifact_path"):
            artifact_dir = current_run["artifact_path"]
        else:
            artifact_dir = mod.get_artifact_dir(tenant_id)  # legacy fallback
        meta_path = os.path.join(artifact_dir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                metadata = json.load(f)
            metrics = metadata.get("val_metrics")
            if metrics:
                state["metrics"][module_name] = metrics

    if not metrics:
        raise HTTPException(status_code=404, detail="No evaluation results. Train a model first.")

    return metrics


@app.get("/api/model/performance")
def model_performance(tenant_id: str = Depends(get_tenant_id)):
    """Return calibration curve and lift data for the prediction accuracy trust panel.

    Reads from the churn_evaluation.json artifact produced at train time.
    Returns 404 if no model has been trained yet.
    """
    state = _get_state(tenant_id)
    metrics = state["metrics"].get("churn")
    if not metrics:
        eval_path = os.path.join(_tenant_output_dir(tenant_id), "churn_evaluation.json")
        if os.path.exists(eval_path):
            with open(eval_path) as f:
                metrics = json.load(f)

    if not metrics:
        raise HTTPException(
            status_code=404,
            detail="No evaluation data. Train and evaluate a model first.",
        )

    return {
        "auc": metrics.get("auc"),
        "pr_auc": metrics.get("pr_auc"),
        "brier": metrics.get("brier"),
        "calibration_error": metrics.get("calibration_error"),
        "lift_at_top10": metrics.get("lift_at_top10"),
        "capture_at_top10": metrics.get("capture_at_top10"),
        "n": metrics.get("n"),
        "calibration_bins": metrics.get("calibration_bins", []),
        "lift_table": metrics.get("lift_table", []),
        "evaluated_at": metrics.get("evaluated_at"),
    }


@app.get("/api/digest/weekly/preview")
def weekly_digest_preview(tenant_id: str = Depends(get_tenant_id)):
    """Generate the weekly revenue digest and return it for browser preview.

    Never sends email. Safe to call repeatedly — does update the WoW snapshot.
    Returns subject, html, text, and the structured digest_data object.
    """
    from app.weekly_digest import generate_weekly_digest
    return generate_weekly_digest(tenant_id=tenant_id, send=False)


@app.post("/api/digest/weekly")
def send_weekly_digest(tenant_id: str = Depends(get_tenant_id)):
    """Generate and send the weekly revenue digest to configured recipients.

    Requires SMTP_HOST env var and notification recipients to be configured.
    Returns the same payload as the preview endpoint, plus sent_to list.
    generate_weekly_digest(send=True) is the stable entry point for future
    cron triggers — no changes to this function needed to enable scheduling.
    """
    from app.weekly_digest import generate_weekly_digest
    return generate_weekly_digest(tenant_id=tenant_id, send=True)


@app.get("/api/arr/forecast")
def arr_forecast(
    horizon_days: int = 90,
    expansion_rate: float = 0.0,
    tenant_id: str = Depends(get_tenant_id),
):
    """Return the ARR trajectory forecast for the next horizon_days.

    Args:
        horizon_days:   Look-ahead window (default 90). Must be 1–365.
        expansion_rate: Fractional upsell applied to low-risk renewing accounts
                        (churn_prob < 30%). Default 0.0 (no expansion assumed).
                        Example: 0.10 = 10% ARR growth on qualifying renewals.

    Returns base forecast, model uncertainty range (±1σ), renewal calendar,
    top at-risk accounts, coverage stats, and an auditable assumptions array.
    """
    if not (1 <= horizon_days <= 365):
        raise HTTPException(status_code=422, detail="horizon_days must be between 1 and 365.")
    if not (0.0 <= expansion_rate <= 1.0):
        raise HTTPException(status_code=422, detail="expansion_rate must be between 0.0 and 1.0.")

    from app.arr_forecast import compute_arr_forecast
    return compute_arr_forecast(
        tenant_id=tenant_id,
        horizon_days=horizon_days,
        expansion_rate=expansion_rate,
        source=_get_crm_provider(tenant_id) if _crm_mode_active(tenant_id) else None,
    )


@app.get("/api/model/insights")
def model_insights(tenant_id: str = Depends(get_tenant_id)):
    """Return plain-language model explainability for the trained churn model.

    Translates feature importances into business-readable drivers and health
    signals. Returns 404 if no model has been trained yet.

    Intended audience: CRO, PE, board — not data scientists.
    Raw feature names are never exposed in the response.
    """
    from app.model_insights import load_insights_for_tenant
    from app.engine.config import get_module as _get_module
    from app.engine import store as _store
    insights = load_insights_for_tenant(tenant_id)
    if insights is None:
        raise HTTPException(status_code=404, detail="No trained model found for this tenant.")
    # Augment with artifact availability so the UI can prompt retrain when needed
    try:
        _mod = _get_module("churn")
        _run = _store.get_current_model_run(tenant_id, "churn")
        _adir = _run.get("artifact_path") if _run else _mod.get_artifact_dir(tenant_id)
        if _adir:
            insights["has_base_model"] = os.path.exists(os.path.join(_adir, "base_model.joblib"))
            insights["has_shap_background"] = os.path.exists(os.path.join(_adir, "shap_background.npy"))
        else:
            insights["has_base_model"] = False
            insights["has_shap_background"] = False
    except Exception:
        insights["has_base_model"] = False
        insights["has_shap_background"] = False
    return insights


@app.get("/api/model/portfolio-drivers")
def get_portfolio_drivers(tenant_id: str = Depends(get_tenant_id)):
    """Return the latest portfolio-level SHAP driver summary.

    Written at score-time; updated every scoring run. Returns 404 if no
    scoring run has been performed yet (or SHAP was unavailable during scoring).
    """
    summary_path = os.path.join(DATA_DIR, "outputs", tenant_id, "portfolio_shap_summary.json")
    if not os.path.exists(summary_path):
        raise HTTPException(status_code=404, detail="No portfolio driver summary found. Run scoring first.")
    try:
        with open(summary_path) as _f:
            return json.load(_f)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read portfolio summary: {exc}")


@app.get("/api/model/production-accuracy")
def get_production_accuracy(tenant_id: str = Depends(get_tenant_id)):
    """Return production prediction accuracy: predictions matched to real outcomes.

    Results are cached per-tenant and recomputed at most once every 24 hours.
    Returns n_pairs=0 with null metrics when no matched pairs exist yet.
    Use POST /api/model/production-accuracy/refresh to force an immediate recompute.
    """
    from app.reconciliation import get_or_refresh
    return get_or_refresh(tenant_id)


@app.post("/api/model/production-accuracy/refresh")
def refresh_production_accuracy(tenant_id: str = Depends(get_tenant_id)):
    """Force-recompute production accuracy metrics from live outcome data.

    Bypasses the 24-hour cache and writes fresh results.
    """
    from app.reconciliation import get_or_refresh
    return get_or_refresh(tenant_id, force=True)


# -----------------------------------------------------------------------
# CRM-native model training
# Builds a labeled dataset from Supabase (accounts + signals + outcomes)
# and trains a provider-isolated model (hubspot_churn / salesforce_churn).
# -----------------------------------------------------------------------

def _execute_crm_training_job(
    tenant_id: str,
    module_name: str,
    run_id: str,
    df: "pd.DataFrame",
    val_frac: float,
    artifact_dir: str,
    version_str: str,
) -> None:
    """Background worker for CRM-native training. Accepts a pre-built DataFrame."""

    def _update_mem(run_id: str, **fields) -> None:
        mem = _get_state(tenant_id).get("model_runs", {}).get(run_id)
        if mem is not None:
            mem.update(fields)

    try:
        started = datetime.now(timezone.utc)
        store.update_model_run(run_id, status="running", started_at=started)
        _update_mem(run_id, status="running", started_at=started.isoformat())

        mod = get_module(module_name)

        # Drop metadata column that must not become a feature
        if "label_source" in df.columns:
            df = df.drop(columns=["label_source"])

        metadata = train_model(df, mod, val_frac=val_frac, tenant_id=tenant_id,
                               run_id=run_id, version_str=version_str, min_rows=10)

        if "error" in metadata:
            raise RuntimeError(metadata.get("message", metadata["error"]))

        loaded_artifacts = load_model(mod, artifact_dir=artifact_dir)

        state = _get_state(tenant_id)
        ts_col = mod.timestamp_column
        metrics = None
        if ts_col in df.columns:
            df_sorted = df.copy()
            df_sorted["_ts"] = pd.to_datetime(df_sorted[ts_col], errors="coerce")
            df_sorted = df_sorted.sort_values("_ts").drop(columns=["_ts"])
            split_idx = int(len(df_sorted) * (1 - val_frac))
            val_df = df_sorted.iloc[split_idx:]
            if len(val_df) >= 10:
                metrics = evaluate_model(val_df, mod, tenant_id=tenant_id,
                                         artifacts=loaded_artifacts)
                state["metrics"][module_name] = metrics
                eval_path = os.path.join(_tenant_output_dir(tenant_id), f"{module_name}_evaluation.json")
                with open(eval_path, "w") as ef:
                    json.dump(metrics, ef, indent=2)
        if metrics is None and metadata.get("val_metrics"):
            metrics = metadata["val_metrics"]
            state["metrics"][module_name] = metrics
            eval_path = os.path.join(_tenant_output_dir(tenant_id), f"{module_name}_evaluation.json")
            with open(eval_path, "w") as ef:
                json.dump(metrics, ef, indent=2)

        completed = datetime.now(timezone.utc)
        final_metrics = metrics or metadata.get("val_metrics")
        store.update_model_run(
            run_id,
            status="complete",
            version_str=metadata.get("version"),
            metrics_json=final_metrics,
            artifact_path=artifact_dir,
            completed_at=completed,
        )
        _update_mem(run_id, status="complete", version_str=metadata.get("version"),
                    metrics_json=final_metrics, completed_at=completed.isoformat())
        store.set_current_model_run(tenant_id, module_name, run_id)
        store.log_action(tenant_id, "model.crm_train_complete", entity_id=run_id,
                         metadata={"module": module_name, "version": metadata.get("version"),
                                   "artifact_path": artifact_dir})

    except Exception as exc:
        traceback.print_exc()
        failed_at = datetime.now(timezone.utc)
        store.update_model_run(
            run_id,
            status="failed",
            error_message=str(exc),
            completed_at=failed_at,
        )
        _update_mem(run_id, status="failed", error_message=str(exc),
                    completed_at=failed_at.isoformat())
        sentry_sdk.capture_exception(exc)


@app.get("/api/crm/data-sufficiency")
def crm_data_sufficiency(
    source: str = Query(...),
    tenant_id: str = Depends(get_tenant_id),
):
    """Check whether sufficient labeled CRM data exists to train a model.

    Returns account counts, outcome distribution, and a pass/fail verdict
    with a human-readable explanation of any shortfall.
    """
    if source not in ("hubspot", "salesforce"):
        raise HTTPException(status_code=400, detail=f"Unknown source '{source}'. Must be 'hubspot' or 'salesforce'.")
    seed_warning: Optional[str] = None
    if DEMO_MODE:
        # Ensure demo dataset is loaded (idempotent — no-op if already present).
        load_result = demo_resolver.ensure_demo_data(tenant_id, provider=source)
        if load_result.errors:
            seed_warning = f"Demo data load error: {'; '.join(load_result.errors)}"
            logger.warning("[demo_resolver] sufficiency pre-load errors: %s", load_result.errors)
    try:
        from app.crm_training import build_crm_training_dataset, check_data_sufficiency
        df, stats = build_crm_training_dataset(tenant_id=tenant_id, source=source)
        ok, message, stats = check_data_sufficiency(df, stats, demo_mode=DEMO_MODE)
        return {
            "ok": ok,
            "message": message,
            "stats": stats,
            "seed_warning": seed_warning,
        }
    except Exception as exc:
        logger.exception("[crm] data-sufficiency failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/crm/train", status_code=202)
def crm_train(
    source: str = Query(...),
    val_frac: float = Query(0.2),
    tenant_id: str = Depends(get_tenant_id),
):
    """Start a CRM-native training job. Builds dataset from Supabase tables.

    Returns 202 immediately with job_id; poll
    GET /api/train/{source}_churn/status/{job_id} for progress.
    """
    if source not in ("hubspot", "salesforce"):
        raise HTTPException(status_code=400, detail=f"Unknown source '{source}'.")

    module_name = f"{source}_churn"
    mod = get_module(module_name)  # validates module exists

    # Build and validate the training dataset synchronously (fast enough for request time)
    if DEMO_MODE:
        # Ensure demo dataset is loaded (idempotent — no-op if already present).
        load_result = demo_resolver.ensure_demo_data(tenant_id, provider=source)
        if load_result.errors:
            logger.warning("[demo_resolver] train pre-load errors: %s", load_result.errors)
    try:
        from app.crm_training import build_crm_training_dataset, check_data_sufficiency
        df, stats = build_crm_training_dataset(tenant_id=tenant_id, source=source)
        ok, message, stats = check_data_sufficiency(df, stats, demo_mode=DEMO_MODE)
        if not ok:
            raise HTTPException(status_code=400, detail=message)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[crm] train dataset build failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    run_id = str(uuid.uuid4())
    artifact_dir = mod.get_artifact_dir(tenant_id, run_id=run_id)
    store.create_model_run(tenant_id, module_name, run_id, artifact_dir)

    _get_state(tenant_id)["model_runs"][run_id] = {
        "id": run_id, "tenant_id": tenant_id, "module": module_name,
        "status": "pending", "trained_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None, "completed_at": None,
        "version_str": None, "metrics_json": None, "error_message": None,
    }

    completed_count = sum(
        1 for r in store.list_model_runs(tenant_id, module_name)
        if r.get("status") == "complete"
    )
    version_str = f"{module_name}_v{completed_count + 1}"

    store.log_action(tenant_id, "model.crm_train_start", entity_id=run_id,
                     metadata={"module": module_name, "source": source,
                               "val_frac": val_frac, "version_str": version_str,
                               "training_rows": len(df)})

    threading.Thread(
        target=_execute_crm_training_job,
        args=(tenant_id, module_name, run_id, df, val_frac, artifact_dir, version_str),
        daemon=True,
        name=f"crm-train-{run_id[:8]}",
    ).start()

    return {"job_id": run_id, "status": "pending", "module": module_name,
            "training_rows": len(df)}


@app.post("/api/evaluate/{module_name}/report")
def generate_report(module_name: str, tenant_id: str = Depends(get_tenant_id)):
    mod = get_module(module_name)
    state = _get_state(tenant_id)
    metrics = state["metrics"].get(module_name)
    if not metrics:
        raise HTTPException(status_code=404, detail="No evaluation metrics. Train first.")

    output_path = os.path.join(_tenant_output_dir(tenant_id), f"{module_name}_report.pdf")
    result = generate_pdf_report(metrics, mod, output_path)
    if not result:
        raise HTTPException(status_code=500, detail="PDF generation failed (reportlab not installed).")

    return FileResponse(output_path, media_type="application/pdf",
                        filename="churn_risk_report.pdf")


# -----------------------------------------------------------------------
# HubSpot write-back
# -----------------------------------------------------------------------

# Per-process cache: integration IDs for which we have already confirmed that
# PickPulse custom properties exist in the tenant's HubSpot portal.
# Cleared implicitly on process restart.  Keyed by integration_id (1:1 with
# HubSpot portal), not tenant_id, since properties are portal-scoped.
_hs_properties_provisioned: set = set()


def _run_hubspot_writeback(tenant_id: str, records: List[Dict[str, Any]]) -> None:
    """Push scored predictions to HubSpot company properties + create tasks.

    Runs in a daemon thread — failures are logged and silently swallowed so
    they never break the predict response to the user.

    Flow:
      1. Look up the tenant's HubSpot integration (skip if not connected).
      2. Ensure PickPulse custom properties exist (idempotent, once per process).
      3. Batch-update company properties for all scored accounts.
      4. Load persisted hs_task_id values to deduplicate task creation.
      5. Create tasks for high-risk accounts that don't already have one.
      6. Persist the task_id back into prediction_json so we don't duplicate.
    """
    # M3: import constants once at function entry, outside the per-record loop
    from app.integrations.hubspot import TASK_RISK_THRESHOLD, TASK_RENEWAL_WINDOW_DAYS

    if not integration_service:
        return
    try:
        hs_integration = integration_service.get_integration(
            tenant_id=tenant_id, provider="hubspot"
        )
        # C1: integration status is "connected" for OAuth; "active" was never
        # set by the service layer and would have caused a permanent silent no-op.
        if not hs_integration or hs_integration.get("status") != "connected":
            return

        from app.integrations.registry import get_connector_for_integration
        connector = get_connector_for_integration(hs_integration["id"])
        if not connector:
            return

        # Part 3: if no records carry hs_object_id, the whole write-back would
        # target wrong companies. Warn with an actionable message and stop early.
        if not any(rec.get("hs_object_id") for rec in records):
            logger.warning(
                "[writeback] Skipping HubSpot write-back for tenant %s: hs_object_id not found "
                "in scored records. Add an 'hs_object_id' column to the dataset mapped to "
                "HubSpot company Record IDs (found in HubSpot exports as 'Record ID').",
                tenant_id,
            )
            return

        # M1: only provision properties once per process per integration
        integration_id = hs_integration["id"]
        if integration_id not in _hs_properties_provisioned:
            connector.ensure_churn_properties()
            _hs_properties_provisioned.add(integration_id)

        # Push scores for all accounts (push_churn_scores skips records missing hs_object_id)
        pushed = connector.push_churn_scores(records)
        logger.info("[writeback] Pushed %d churn scores to HubSpot for tenant %s", pushed, tenant_id)

        # C2: load persisted task IDs from Supabase in one batch query.
        # Fresh scored rows never carry hs_task_id (it lives only in prediction_json
        # in the DB), so the old in-memory check always failed.
        existing_task_ids = store.get_accounts_with_task_ids(tenant_id, MODULE_NAME)

        # Create tasks for high-risk, renewal-window accounts
        tasks_created = 0
        skipped_no_hs_id = 0
        for rec in records:
            try:
                # Part 2: require hs_object_id for task creation / association
                if not rec.get("hs_object_id"):
                    skipped_no_hs_id += 1
                    continue

                churn_risk_pct = float(rec.get("churn_risk_pct") or 0)
                if churn_risk_pct < TASK_RISK_THRESHOLD:
                    continue
                days_renewal = rec.get("days_until_renewal")
                if days_renewal is not None:
                    try:
                        if float(days_renewal) > TASK_RENEWAL_WINDOW_DAYS:
                            continue
                    except (TypeError, ValueError):
                        pass

                # C2: deduplicate using the DB-backed lookup (keyed by account_id,
                # which is the primary key in predictions_live)
                account_id = str(rec.get("account_id", ""))
                if existing_task_ids.get(account_id):
                    continue

                task_id = connector.create_task(rec)
                if task_id:
                    store.patch_prediction_json(
                        tenant_id, MODULE_NAME,
                        account_id,
                        {"hs_task_id": task_id},
                    )
                    # Update local dedup map so same-run duplicates are prevented
                    existing_task_ids[account_id] = task_id
                    tasks_created += 1
            except Exception as exc:
                logger.warning("[writeback] Task creation failed for account %s: %s",
                               rec.get("account_id"), exc)

        if skipped_no_hs_id:
            logger.warning(
                "[writeback] Skipped task creation for %d records with missing hs_object_id "
                "(tenant %s)", skipped_no_hs_id, tenant_id,
            )
        if tasks_created:
            logger.info("[writeback] Created %d HubSpot tasks for tenant %s", tasks_created, tenant_id)

    except Exception as exc:
        logger.warning("[writeback] HubSpot write-back failed for tenant %s: %s", tenant_id, exc)


def _spawn_hubspot_writeback(tenant_id: str, records: List[Dict[str, Any]]) -> None:
    """Fire-and-forget: spawn write-back in a daemon thread."""
    t = threading.Thread(
        target=_run_hubspot_writeback,
        args=(tenant_id, records),
        daemon=True,
        name=f"hs-writeback-{tenant_id[:8]}",
    )
    t.start()


# -----------------------------------------------------------------------
# Predictions
# -----------------------------------------------------------------------
@app.post("/api/predict/{module_name}")
def predict_module(
    module_name: str,
    limit: int = Query(100),
    include_archived: bool = Query(False),
    tenant_id: str = Depends(get_tenant_id),
):
    """Generate predictions on the loaded dataset."""
    mod = get_module(module_name)
    ds = _get_dataset(module_name, tenant_id=tenant_id)
    if not ds:
        raise HTTPException(status_code=400, detail="No dataset loaded.")

    # Resolve artifact directory: versioned path from model_runs (PR 3A+) with
    # backward-compatible fallback to the flat per-tenant+module path.
    current_run = store.get_current_model_run(tenant_id, module_name)
    if current_run and current_run.get("artifact_path"):
        artifact_dir = current_run["artifact_path"]
        run_id = current_run.get("id")
    else:
        artifact_dir = mod.get_artifact_dir(tenant_id)  # legacy fallback
        run_id = None

    if not os.path.exists(os.path.join(artifact_dir, "model.joblib")):
        raise HTTPException(status_code=400, detail="No trained model. Train first.")

    try:
        df = pd.read_csv(ds["path"])
        adapter = _get_adapter(module_name)
        if adapter:
            df = adapter.normalize_columns(df)
            df = adapter.add_derived_features(df)

        artifacts = load_model(mod, artifact_dir=artifact_dir)
        scored = predict(df, mod, artifacts=artifacts)

        state = _get_state(tenant_id)
        # Apply any manual status overrides
        for cid, status in state["account_statuses"].items():
            mask = scored[mod.id_column] == cid
            if mask.any():
                scored.loc[mask, "account_status"] = status

        # Save full scored output for export (tenant-scoped)
        scored.to_csv(os.path.join(_tenant_output_dir(tenant_id), f"{module_name}_scored.csv"), index=False)

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
            "top_drivers", "confidence_level", "action_tier",
            "hs_object_id",  # included when present; flows into prediction_json for CRM card lookup
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
        # Round churn_risk_pct to 1 decimal — pandas float64 → dict preserves
        # IEEE 754 imprecision (e.g. 15.370000000000001 instead of 15.4)
        for _r in records:
            if "churn_risk_pct" in _r and _r["churn_risk_pct"] is not None:
                _r["churn_risk_pct"] = round(float(_r["churn_risk_pct"]), 1)
        state["predictions"][module_name] = records
        state["predictions_generated_at"] = datetime.now(timezone.utc).isoformat()
        store.save_predictions(tenant_id, module_name, run_id or "", records)
        # Only set context to "dataset" when a CRM integration is NOT active.
        # If CRM is active, the context must stay on the CRM provider — dataset
        # predictions running in the background must not silently overwrite it.
        if not _crm_mode_active(tenant_id):
            _set_active_source(tenant_id, "csv")

        # H3: write-back uses the full active scored set (no head() cap).
        # The display subset above is limited to `limit` rows for the UI;
        # HubSpot needs all scored accounts regardless of display pagination.
        if module_name == MODULE_NAME:
            _wb_cols = [c for c in [
                mod.id_column, "churn_risk_pct", "arr_at_risk",
                "recommended_action", "days_until_renewal", "tier",
                "hs_object_id",  # deterministic HubSpot company ID for write-back
            ] if c in scored_display.columns]
            writeback_records = scored_display[_wb_cols].to_dict(orient="records")
            _spawn_hubspot_writeback(tenant_id, writeback_records)

        # Tier counts (from full active set)
        tier_counts = scored_display["tier"].value_counts().to_dict()

        # Summary stats for dashboard
        summary = {}
        if "arr_at_risk" in scored_display.columns:
            summary["total_arr_at_risk"] = round(float(scored_display["arr_at_risk"].sum()), 2)
        if "renewal_window_90d" in scored.columns:
            summary["renewing_90d"] = int(scored[scored["account_status"] == "active"]["renewal_window_90d"].sum()) if "account_status" in scored.columns else int(scored["renewal_window_90d"].sum())
        if "churn_risk_pct" in scored_display.columns and "days_until_renewal" in scored_display.columns:
            high_in_window = scored_display[
                (scored_display["churn_risk_pct"] >= 25) &
                (scored_display["days_until_renewal"].notna()) &
                (scored_display["days_until_renewal"] <= 30)
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


# ---------------------------------------------------------------------------
# CRM pipeline helpers — power the Accounts page from churn_scores_daily
# ---------------------------------------------------------------------------

def _source_context_path(tenant_id: str) -> str:
    """Path to the persisted active-source marker file."""
    return os.path.join(_tenant_output_dir(tenant_id), ".source_context.json")


def _get_active_source(tenant_id: str) -> Optional[str]:
    """Return 'dataset' | 'crm' | None (file absent = no explicit context set)."""
    try:
        p = _source_context_path(tenant_id)
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f).get("active_source")
    except Exception:
        pass
    return None


def _set_active_source(
    tenant_id: str,
    source: str,
    crm_provider: Optional[str] = None,
) -> None:
    """Persist the active source to disk.

    The stored value is always the specific, queryable source name:
      - 'csv' / 'dataset' for CSV/dataset mode
      - the exact CRM provider name (e.g. 'hubspot', 'salesforce') for CRM mode

    The generic string 'crm' is intentionally NOT stored because it carries no
    provider information and causes unfiltered cross-provider queries downstream.
    When crm_provider is supplied it is used as the effective stored value so
    callers using the old (source='crm', crm_provider='hubspot') convention
    continue to work correctly.
    """
    try:
        os.makedirs(os.path.dirname(_source_context_path(tenant_id)), exist_ok=True)
        # Always store the most specific value available.
        effective = crm_provider if crm_provider else source
        with open(_source_context_path(tenant_id), "w") as f:
            json.dump({"active_source": effective}, f)
    except Exception as exc:
        logger.warning("[source_context] Could not persist active_source: %s", exc)


def _get_crm_provider(tenant_id: str) -> Optional[str]:
    """Return the specific CRM provider name when in CRM mode, else None.

    With the new context format the active_source field IS the provider name
    (e.g. 'hubspot', 'salesforce').  For legacy context files that still use
    the generic 'crm' active_source, falls back to the separate crm_provider
    field if present.  Returns None for dataset/csv mode or when the provider
    cannot be determined (callers must then apply no source filter).
    """
    try:
        p = _source_context_path(tenant_id)
        if os.path.exists(p):
            with open(p) as f:
                data = json.load(f)
            s = data.get("active_source")
            # New format: active_source holds the specific provider name directly.
            if s and s not in ("csv", "dataset", "crm"):
                return s
            # Legacy format: active_source='crm' with a separate crm_provider field.
            if s == "crm":
                return data.get("crm_provider")  # may still be None for very old files
    except Exception:
        pass
    return None


def _crm_mode_active(tenant_id: str) -> bool:
    """True when the active scoring context is a specific CRM provider.

    Requires an explicit context file written by a CRM scoring endpoint with
    a known provider name (e.g. 'hubspot', 'salesforce').  Returns False for:
      - No context file (server restart / fresh deployment)
      - Dataset/CSV mode ('dataset', 'csv')
      - Generic 'crm' without a provider (old format — user must rescore)
    This prevents the Overview and Accounts pages from pre-populating from
    stale DB rows when the active provider cannot be determined.
    """
    s = _get_active_source(tenant_id)
    # Only dataset-mode markers and the unresolvable generic 'crm' return False.
    if s is None or s in ("csv", "dataset", "crm"):
        return False
    # Any other non-empty string is treated as a specific CRM provider name.
    return True


def _build_crm_predict_response(
    tenant_id: str,
    limit: int = 500,
    include_archived: bool = False,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a PredictResponse-shaped dict from churn_scores_daily + accounts + signals.

    Replaces the predictions_live path when the integrations pipeline has
    recent scores (CRM mode). Returns the same shape as predict_module so
    the frontend requires zero changes.

    source: if provided (e.g. "salesforce"), restricts scores to that provider
    so HubSpot and Salesforce data are never mixed in the response.
    """
    from .modules.churn.adapter import compute_renewal_window_label

    scores = storage_repo.latest_scores(limit=10000, tenant_id=tenant_id, source=source)
    signals_by_account = storage_repo.bulk_latest_signals(tenant_id)
    account_statuses = _get_state(tenant_id).get("account_statuses", {})

    predictions: List[Dict[str, Any]] = []
    for s in scores:
        acct_uuid = s.get("account_id", "")
        ext_id = s.get("external_id") or acct_uuid

        # Apply any manual lifecycle status overrides
        status = account_statuses.get(str(ext_id), s.get("account_status", "active"))
        is_archived = status not in ("active", "at_risk", "save_in_progress")
        if is_archived and not include_archived:
            continue

        sig = signals_by_account.get(acct_uuid, {})
        days_until_renewal = sig.get("days_until_renewal")
        auto_renew_flag = sig.get("auto_renew_flag")

        # Renewal window label: prefer stored value, fall back to computing from signals
        renewal_window = s.get("renewal_window") or (
            compute_renewal_window_label(float(days_until_renewal))
            if days_until_renewal is not None else "unknown"
        )

        predictions.append({
            "account_id": ext_id,
            "churn_risk_pct": float(s.get("churn_risk_pct", 0)),
            "urgency_score": s.get("urgency_score"),
            "renewal_window_label": renewal_window or "unknown",
            "days_until_renewal": int(float(days_until_renewal)) if days_until_renewal is not None else None,
            "auto_renew_flag": int(float(auto_renew_flag)) if auto_renew_flag is not None else None,
            "arr": s.get("arr"),
            "arr_at_risk": s.get("arr_at_risk"),
            "recommended_action": s.get("recommended_action") or "Monitor",
            "tier": s.get("tier") or "Low Risk",
            "account_status": status,
            "name": s.get("name"),
        })

    # Rank is positional after sort-by-risk (latest_scores already orders DESC)
    for i, p in enumerate(predictions):
        p["rank"] = i + 1

    showing = predictions[:limit]

    tier_counts: Dict[str, int] = {}
    total_arr_at_risk = 0.0
    renewing_90d = 0
    high_risk_in_window = 0
    active_count = 0
    archived_count = 0
    for p in predictions:
        t = p.get("tier", "Unknown")
        tier_counts[t] = tier_counts.get(t, 0) + 1
        total_arr_at_risk += p.get("arr_at_risk") or 0
        if p.get("account_status") in ("active", "at_risk", "save_in_progress"):
            active_count += 1
        else:
            archived_count += 1
        wl = p.get("renewal_window_label", "")
        if wl in ("<30d", "30-90d"):
            renewing_90d += 1
        dur = p.get("days_until_renewal")
        if dur is not None and dur <= 30 and float(p.get("churn_risk_pct", 0)) >= 25:
            high_risk_in_window += 1

    return {
        "predictions": showing,
        "total": len(predictions),
        "showing": len(showing),
        "active_count": active_count,
        "archived_count": archived_count,
        "tier_counts": tier_counts,
        "crm_mode": True,
        "summary": {
            "total_arr_at_risk": round(total_arr_at_risk, 2),
            "renewing_90d": renewing_90d,
            "high_risk_in_window": high_risk_in_window,
        },
    }


@app.get("/api/predict/{module_name}/cached")
def get_cached_predictions(
    module_name: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """Return cached predictions without re-scoring.

    Returns 404 when no active mode has been set — this is the primary
    guard against pre-populating the UI from stale DB rows or old scores
    when the user has not yet selected a workflow source.

    CRM mode (salesforce / hubspot): builds the response from
    churn_scores_daily filtered to the active provider.

    CSV mode: reads from the predictions_live table (in-memory state).
    """
    # Gate: no active mode = no predictions served, ever.
    active_source = _get_active_source(tenant_id)
    if active_source is None or active_source == "crm":
        raise HTTPException(status_code=404, detail="No active workflow mode. Select a data source first.")

    if module_name == MODULE_NAME and _crm_mode_active(tenant_id):
        return _build_crm_predict_response(tenant_id, source=_get_crm_provider(tenant_id))

    state = _get_state(tenant_id)
    records = state["predictions"].get(module_name, [])
    if not records:
        raise HTTPException(status_code=404, detail="No cached predictions. Run predict first.")
    if _predictions_are_stale(state, module_name, tenant_id):
        raise HTTPException(status_code=404, detail="No cached predictions. Run predict first.")

    tier_counts: dict[str, int] = {}
    total_arr_at_risk = 0.0
    renewing_90d = 0
    high_risk_in_window = 0
    active_count = 0
    archived_count = 0
    for p in records:
        tier = p.get("tier", "Unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        arr_r = p.get("arr_at_risk", 0) or 0
        total_arr_at_risk += arr_r
        status_val = p.get("account_status", "active")
        if status_val == "active":
            active_count += 1
        else:
            archived_count += 1
        pct = p.get("churn_risk_pct", 0) or 0
        wl = p.get("renewal_window_label", "")
        if wl in ("<30d", "30-90d"):
            renewing_90d += 1
        dur = p.get("days_until_renewal")
        if dur is not None and dur <= 30 and pct >= 25:
            high_risk_in_window += 1

    return {
        "predictions": records,
        "total": len(records),
        "showing": len(records),
        "active_count": active_count,
        "archived_count": archived_count,
        "tier_counts": tier_counts,
        "summary": {
            "total_arr_at_risk": round(total_arr_at_risk, 2),
            "renewing_90d": renewing_90d,
            "high_risk_in_window": high_risk_in_window,
        },
    }


@app.get("/api/predict/{module_name}/export")
def export_predictions(module_name: str, tenant_id: str = Depends(get_tenant_id)):
    import io as _io

    # CRM mode: build CSV in-memory from live scores (no static file exists)
    if module_name == MODULE_NAME and _crm_mode_active(tenant_id):
        crm_data = _build_crm_predict_response(
            tenant_id, limit=100_000, source=_get_crm_provider(tenant_id)
        )
        predictions = crm_data.get("predictions", [])
        if not predictions:
            raise HTTPException(status_code=404, detail="No scored predictions. Run Rescore All first.")
        buf = _io.StringIO()
        pd.DataFrame(predictions).to_csv(buf, index=False)
        buf.seek(0)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=\"churn_predictions.csv\""},
        )

    get_module(module_name)
    scored_path = os.path.join(_tenant_output_dir(tenant_id), f"{module_name}_scored.csv")
    if not os.path.exists(scored_path):
        raise HTTPException(status_code=404, detail="No scored predictions. Run predict first.")

    return FileResponse(scored_path, media_type="text/csv",
                        filename="churn_predictions.csv")


# -----------------------------------------------------------------------
# Account status management
# -----------------------------------------------------------------------
@app.post("/api/accounts/{account_id}/status")
def update_account_status(account_id: str, status: str = Query(...), tenant_id: str = Depends(get_tenant_id)):
    """Update account lifecycle status.

    Valid statuses: active, at_risk, save_in_progress, renewed, churned,
                    archived_renewed, archived_cancelled
    """
    valid = ["active", "at_risk", "save_in_progress", "renewed", "churned",
             "archived_renewed", "archived_cancelled"]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")

    state = _get_state(tenant_id)
    state["account_statuses"][account_id] = status
    store.update_account_status(tenant_id, account_id, status, module=MODULE_NAME)
    store.log_action(tenant_id, "account.status_change", entity_id=account_id,
                     metadata={"status": status})

    # Record definitive outcome when a CSM marks an account as renewed or churned.
    # Non-blocking — failures are logged by record_outcome() as warnings.
    _OUTCOME_STATUS_MAP = {
        "renewed": "renewed",
        "archived_renewed": "renewed",
        "churned": "churned",
        "archived_cancelled": "churned",
    }
    if status in _OUTCOME_STATUS_MAP:
        storage_repo.record_outcome(
            external_id=account_id,
            outcome_type=_OUTCOME_STATUS_MAP[status],
            source="manual",
            tenant_id=tenant_id,
        )

    return {"account_id": account_id, "status": status}


@app.get("/api/accounts")
def list_accounts(status: Optional[str] = Query(None), tenant_id: str = Depends(get_tenant_id)):
    """List accounts with optional status filter."""
    state = _get_state(tenant_id)
    predictions = state["predictions"].get(MODULE_NAME, [])
    if status:
        # Filter by status from overrides or from predictions
        filtered = []
        for p in predictions:
            acct_status = state["account_statuses"].get(
                p.get("account_id"), p.get("account_status", "active")
            )
            if acct_status == status:
                filtered.append({**p, "account_status": acct_status})
        return {"accounts": filtered, "count": len(filtered)}

    return {"accounts": predictions, "count": len(predictions)}


# -----------------------------------------------------------------------
# API docs
# -----------------------------------------------------------------------
@app.get("/api/api-docs")
def api_docs_meta(tenant_id: str = Depends(get_tenant_id)):
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
                        {"account_id": "CUST-20042", "churn_risk_pct": 82.3,
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
                "path": "/api/accounts/{account_id}/status",
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
def get_onboarding(tenant_id: str = Depends(get_tenant_id)):
    steps = []
    for step in ONBOARDING_STEPS:
        steps.append({
            **step,
            "status": _onboarding_state.get(step["id"], "pending"),
        })
    return {"steps": steps}


@app.post("/api/onboarding/{step_id}/complete")
def complete_onboarding_step(step_id: str, tenant_id: str = Depends(get_tenant_id)):
    valid_ids = [s["id"] for s in ONBOARDING_STEPS]
    if step_id not in valid_ids:
        raise HTTPException(status_code=404, detail=f"Unknown step: {step_id}")
    _onboarding_state[step_id] = "complete"
    return {"step_id": step_id, "status": "complete"}


@app.post("/api/onboarding/{step_id}/reset")
def reset_onboarding_step(step_id: str, tenant_id: str = Depends(get_tenant_id)):
    _onboarding_state[step_id] = "pending"
    return {"step_id": step_id, "status": "pending"}


@app.get("/api/onboarding/template/{module_name}")
def download_data_template(module_name: str, tenant_id: str = Depends(get_tenant_id)):
    mod = get_module(module_name)
    cols = mod.required_columns + mod.optional_columns
    df = pd.DataFrame(columns=cols)
    output_dir = os.path.join(os.environ.get("DATA_DIR", "data"), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{module_name}_template.csv")
    df.to_csv(path, index=False)
    return FileResponse(path, media_type="text/csv",
                        filename="churn_data_template.csv")


# -----------------------------------------------------------------------
# Dashboard summary (churn-specific)
# -----------------------------------------------------------------------
@app.get("/api/dashboard")
def dashboard_summary(save_rate: float = Query(0.35, ge=0.05, le=0.95), tenant_id: str = Depends(get_tenant_id)):
    mod = get_module("churn")
    artifact_dir = mod.get_artifact_dir(tenant_id)
    meta_path = os.path.join(artifact_dir, "metadata.json")
    metadata = None
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            metadata = json.load(f)

    state = _get_state(tenant_id)
    metrics = state["metrics"].get("churn")
    if not metrics:
        eval_path = os.path.join(_tenant_output_dir(tenant_id), "churn_evaluation.json")
        if os.path.exists(eval_path):
            with open(eval_path) as f:
                metrics = json.load(f)

    # CRM mode: source predictions from churn_scores_daily instead of
    # the in-memory CSV pipeline state.
    if _crm_mode_active(tenant_id):
        crm_response = _build_crm_predict_response(
            tenant_id, limit=10000, source=_get_crm_provider(tenant_id)
        )
        predictions = crm_response.get("predictions", [])
    else:
        predictions = state["predictions"].get("churn", [])
        # Discard predictions that pre-date the current dataset registration.
        if predictions and _predictions_are_stale(state, "churn", tenant_id):
            predictions = []

    # Compute summary KPIs from cached predictions
    total_arr_at_risk = 0.0
    renewing_90d = 0
    high_risk_in_window = 0
    # Recovery buckets by churn probability tier
    high_saves = 0.0   # churn_risk_pct >= 30
    medium_saves = 0.0  # 20 <= churn_risk_pct < 30
    low_saves = 0.0     # churn_risk_pct < 20
    tier_counts: dict[str, int] = {}
    for p in predictions:
        arr_r = p.get("arr_at_risk", 0) or 0
        total_arr_at_risk += arr_r
        pct = p.get("churn_risk_pct") or 0
        if pct >= 30:
            high_saves += arr_r
        elif pct >= 20:
            medium_saves += arr_r
        else:
            low_saves += arr_r
        if p.get("renewal_window_label") in ("<30d", "30-90d"):
            renewing_90d += 1
        dur = p.get("days_until_renewal")
        if dur is not None and dur <= 30 and pct >= 25:
            high_risk_in_window += 1
        tier = p.get("tier", "Unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    # Top risk drivers from model feature importance
    top_risk_drivers: list[dict] = []
    if metadata and isinstance(metadata.get("feature_importance"), list):
        sorted_fi = sorted(
            metadata["feature_importance"],
            key=lambda x: abs(x.get("importance", 0)),
            reverse=True,
        )[:5]
        top_risk_drivers = [
            {"feature": f["feature"], "importance": f["importance"]}
            for f in sorted_fi
        ]

    # Top 10 at-risk accounts
    top_10 = sorted(predictions, key=lambda x: x.get("arr_at_risk", 0) or 0, reverse=True)[:10]

    # Top priority accounts: prob >= 25%, sorted by days_until_renewal ASC (nulls last), prob DESC
    priority_candidates = [p for p in predictions if (p.get("churn_risk_pct") or 0) >= 25]
    top_priority_accounts = sorted(
        priority_candidates,
        key=lambda x: (
            x.get("days_until_renewal") is None,
            x.get("days_until_renewal") if x.get("days_until_renewal") is not None else 9999,
            -(x.get("churn_risk_pct") or 0),
        ),
    )[:5]

    ds = _get_dataset("churn", tenant_id=tenant_id)

    return {
        "module": {
            "name": "churn",
            "display_name": mod.display_name,
            "has_model": os.path.exists(os.path.join(artifact_dir, "model.joblib")),
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
        "recovery_buckets": {
            "high_confidence_saves": round(high_saves, 2),
            "medium_confidence_saves": round(medium_saves, 2),
            "low_confidence_saves": round(low_saves, 2),
        },
        "top_at_risk": top_10,
        "top_priority_accounts": top_priority_accounts,
        "tier_counts": tier_counts,
        "top_risk_drivers": top_risk_drivers,
        "active_source": _get_active_source(tenant_id) or "dataset",
    }


# -----------------------------------------------------------------------
# Revenue Impact Tracker — platform-level executive metric
# -----------------------------------------------------------------------
@app.get("/api/dashboard/revenue-impact")
def revenue_impact_summary(tenant_id: str = Depends(get_tenant_id)):
    """Return platform-level revenue impact metrics for the executive hero section."""
    state = _get_state(tenant_id)
    predictions = state["predictions"].get("churn", [])
    account_statuses = state.get("account_statuses", {})
    ds = _get_dataset("churn", tenant_id=tenant_id)
    is_demo = bool((ds or {}).get("is_demo", False)) or DEMO_MODE

    return compute_revenue_impact(predictions, account_statuses, is_demo)


# -----------------------------------------------------------------------
# Integrations (new platform endpoints)
# -----------------------------------------------------------------------

def _require_service():
    if integration_service is None:
        raise HTTPException(503, detail="Integration service unavailable — check server env vars")


@app.get("/api/integrations")
def list_integrations(tenant_id: str = Depends(get_tenant_id)):
    """List all providers with integration status."""
    try:
        if not integration_service:
            raise RuntimeError("service unavailable")
        providers = integration_service.list_integrations(tenant_id)
        # Enrich available providers with account counts
        for p in providers:
            if p["enabled"]:
                p["account_count"] = storage_repo.account_count(source=p["provider"], tenant_id=tenant_id)
            else:
                p["account_count"] = 0
        return {"providers": providers}
    except Exception:
        # Fallback to legacy if integration tables don't exist yet
        connectors = connector_registry.list_connectors()
        for c in connectors:
            if c.enabled:
                c.account_count = storage_repo.account_count(source=c.name)
                cfg = connector_registry.get_config(c.name)
                if cfg and cfg.extra.get("last_sync_result"):
                    sync_info = cfg.extra["last_sync_result"]
                    c.error_message = "; ".join(sync_info.get("errors", [])) or None
        return {"connectors": [c.model_dump() for c in connectors]}


@app.get("/api/integrations/{provider}/metadata")
def get_provider_metadata(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Get provider template with default field mappings."""
    _require_service()
    tmpl = integration_service.get_template(provider)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    return tmpl


@app.post("/api/integrations/{provider}/connect")
def connect_integration(provider: str, api_key: str = Query(...), tenant_id: str = Depends(get_tenant_id)):
    """Connect a provider using an API key."""
    available = connector_registry.available_connectors()
    if provider not in available:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {provider}")

    # Test connection first using a temporary connector
    config = ConnectorConfig(
        name=provider,
        display_name=available[provider].__name__,
        api_key=api_key,
        enabled=True,
    )
    cls = available[provider]
    instance = cls(config)
    if not instance.test_connection():
        raise HTTPException(status_code=400, detail="Connection test failed. Check your API key.")

    # Persist with encrypted token
    try:
        if not integration_service:
            raise RuntimeError("service unavailable")
        integration = integration_service.connect_api_key(tenant_id, provider, api_key)
    except Exception as exc:
        # If integration tables don't exist, fall back to legacy
        connector_registry.configure(provider, config)
        return {"status": "configured", "connector": provider}

    # Also configure legacy registry for backward compat
    connector_registry.configure(provider, config)

    return {"status": "connected", "connector": provider, "integration_id": integration["id"]}


# Legacy backward-compat: redirect /configure to /connect
@app.post("/api/integrations/{connector_name}/configure")
def configure_integration(connector_name: str, api_key: str = Query(...), tenant_id: str = Depends(get_tenant_id)):
    """Configure a connector with API credentials (legacy — redirects to /connect)."""
    return connect_integration(connector_name, api_key, tenant_id=tenant_id)


@app.get("/api/integrations/{provider}/oauth/start")
def start_oauth_flow(
    provider: str,
    redirect_uri: str = Query(...),
    tenant_id: str = Depends(get_tenant_id),
):
    """Start OAuth flow — returns auth URL and state token."""
    _require_service()
    try:
        result = integration_service.start_oauth(tenant_id, provider, redirect_uri)
        auth_url = result.get("auth_url", "")
        logger.info("[oauth/start] provider=%s redirect_uri=%s", provider, redirect_uri)
        logger.info("[oauth/start] auth_url=%s", auth_url)
        logger.info("[oauth/start] state present in URL: %s", "&state=" in auth_url or "?state=" in auth_url)
        return result
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/integrations/{provider}/oauth/callback")
def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
):
    """OAuth callback — exchanges code for tokens, redirects to frontend."""
    from fastapi.responses import RedirectResponse
    _require_service()

    logger.info("[oauth/callback] provider=%s code=%s... state=%s...", provider, code[:8], state[:20])

    try:
        from app.integrations.oauth import validate_state
        payload = validate_state(state)
        logger.info("[oauth/callback] state payload: tenant=%s provider=%s", payload.get("tenant_id"), payload.get("provider"))

        # redirect_uri for token exchange must match what we sent to the provider
        api_base = os.environ.get("API_BASE_URL", "").rstrip("/")
        callback_url = f"{api_base}/api/integrations/{provider}/oauth/callback"

        integration = integration_service.complete_oauth(
            provider, code, state, callback_url
        )

        # Redirect browser to the frontend URL stored in state
        frontend_redirect = payload.get("redirect", "/")
        separator = "&" if "?" in frontend_redirect else "?"
        return RedirectResponse(
            url=f"{frontend_redirect}{separator}oauth=success&provider={provider}",
            status_code=302,
        )
    except ValueError as exc:
        logger.error("[oauth/callback] ValueError: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[oauth/callback] Error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/integrations/{provider}/disconnect")
def disconnect_integration(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Disconnect a provider — purge tokens and disable."""
    _require_service()
    integration_service.disconnect(tenant_id, provider)
    return {"status": "disconnected", "provider": provider}


@app.post("/api/integrations/{provider}/sync")
def trigger_sync(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Trigger a sync for a provider.

    In demo mode, HubSpot and Salesforce bypass the live CRM pull entirely and
    use a fixed seeded synthetic dataset instead.  The OAuth connection flow is
    preserved; only the data ingestion step is replaced.
    """
    from app.integrations.models import SyncResult as _SyncResult

    # ------------------------------------------------------------------
    # Demo mode intercept (HubSpot / Salesforce only)
    # ------------------------------------------------------------------
    # When running in demo mode, load the provider-specific synthetic dataset
    # directly into Supabase instead of pulling live CRM data.  This ensures:
    #   • The rest of the pipeline (train / score / ARR CC) operates on the
    #     same Supabase tables and requires zero downstream changes.
    #   • Live CRM data can never contaminate the demo tenant.
    #   • The result is deterministic and repeatable across demo runs.
    if demo_resolver.should_use_synthetic(provider):
        logger.info("[sync] DEMO MODE: loading synthetic %s dataset for tenant %s…", provider, tenant_id[:8])
        load_result = demo_resolver.ensure_demo_data(tenant_id, provider)
        if load_result.errors:
            logger.error("[sync] Demo data load errors: %s", load_result.errors)
        return {
            "status": "synced",
            "accounts_synced": load_result.account_count,
            "signals_synced": load_result.signal_count,
            "errors": load_result.errors,
            "duration_seconds": 0,
            "demo_mode": True,
        }

    # ------------------------------------------------------------------
    # Live mode — real CRM ingestion (unchanged)
    # ------------------------------------------------------------------
    if integration_service:
        # Service layer handles OAuth providers — never fall back to legacy for these.
        # Any internal exception is caught here and returned as a SyncResult error
        # rather than letting it surface to the legacy path (which raises 400).
        try:
            result = integration_service.trigger_sync(tenant_id, provider)
        except Exception as exc:
            logger.exception("[sync] Service layer raised for provider=%s", provider)
            result = _SyncResult(connector=provider, errors=[str(exc)])
    else:
        # Legacy sync — only for non-OAuth connectors configured in-memory
        cfg = connector_registry.get_config(provider)
        if not cfg or not cfg.enabled:
            raise HTTPException(
                status_code=400,
                detail=f"Connector '{provider}' not configured or not enabled.",
            )
        result = sync_connector(provider)

    return {
        "status": "synced" if not result.errors else "partial",
        "accounts_synced": result.accounts_synced,
        "signals_synced": result.signals_synced,
        "outcomes_imported": getattr(result, "outcomes_imported", 0),
        "errors": result.errors,
        "duration_seconds": result.duration_seconds,
    }


@app.get("/api/integrations/{provider}/sync/status")
def get_sync_status(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Get sync state for a provider."""
    _require_service()
    integration = integration_service.get_integration(
        tenant_id=tenant_id, provider=provider
    )
    if not integration:
        return {"provider": provider, "sync_states": [], "status": "not_configured"}

    states = integration_service.get_sync_state(integration["id"])
    return {
        "provider": provider,
        "status": integration["status"],
        "sync_states": states,
    }


@app.get("/api/integrations/{provider}/mappings")
def get_field_mappings(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Get field mappings for a provider."""
    _require_service()
    integration = integration_service.get_integration(
        tenant_id=tenant_id, provider=provider
    )
    if not integration:
        # Return template defaults
        tmpl = integration_service.get_template(provider)
        if not tmpl:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
        mappings = []
        for source, mapping in tmpl.get("default_field_map", {}).items():
            mappings.append({
                "source_field": source,
                "target_field": mapping["target"],
                "transform": mapping.get("transform", "direct"),
                "is_default": True,
            })
        return {"provider": provider, "mappings": mappings}

    mappings = integration_service.get_field_mappings(integration["id"])
    return {"provider": provider, "mappings": mappings}


@app.put("/api/integrations/{provider}/mappings")
def update_field_mappings(provider: str, mappings: List[FieldMappingItem], tenant_id: str = Depends(get_tenant_id)):
    """Update field mappings for a provider."""
    _require_service()
    integration = integration_service.get_integration(
        tenant_id=tenant_id, provider=provider
    )
    if not integration:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not connected")

    count = integration_service.update_field_mappings(
        integration["id"], [m.model_dump() for m in mappings]
    )
    return {"provider": provider, "updated": count}


@app.post("/api/integrations/{provider}/preview")
def preview_integration(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Preview first 5 records with current field mapping."""
    _require_service()
    from app.integrations.registry import get_connector_for_integration

    integration = integration_service.get_integration(
        tenant_id=tenant_id, provider=provider
    )
    if not integration:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not connected")

    connector = get_connector_for_integration(integration["id"])
    if not connector:
        raise HTTPException(status_code=400, detail="Could not instantiate connector")

    try:
        accounts = connector.pull_accounts()
        preview = [a.model_dump() for a in accounts[:5]]
        return {"provider": provider, "preview": preview, "total_available": len(accounts)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/integrations/{provider}/health")
def check_integration_health(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Check connection health for a provider."""
    _require_service()
    return integration_service.check_health(tenant_id, provider)


@app.get("/api/integrations/{provider}/preflight")
def integration_preflight(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Run a connection preflight check and return object counts + schema coverage.

    Returns a PreflightResult: companies/contacts/deals/tickets counts, whether
    property metadata was retrieved, schema coverage %, and any unmapped fields.
    Never raises — all failures are captured in the result's warnings list.
    """
    if provider != "hubspot":
        raise HTTPException(status_code=400, detail="Preflight is only supported for hubspot")

    from app.integrations.registry import get_connector_for_integration

    integration = None
    if integration_service:
        integration = integration_service.get_integration(tenant_id=tenant_id, provider=provider)
    if not integration:
        raise HTTPException(status_code=404, detail="HubSpot not connected for this tenant")

    try:
        connector = get_connector_for_integration(integration["id"])
        if not connector:
            raise HTTPException(status_code=404, detail="Could not load HubSpot connector")
        result = connector.connection_preflight()
        return result.dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[preflight] %s: %s", provider, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/integrations/{provider}/schema")
def integration_schema(
    provider: str,
    mode: str = Query("saas", regex="^(saas|services)$"),
    tenant_id: str = Depends(get_tenant_id),
):
    """Return dynamic schema mapping for the connected portal.

    Pulls all property metadata from the portal and matches against canonical
    field aliases. Returns resolved mappings with confidence scores, alternates,
    and unmapped fields.
    """
    if provider != "hubspot":
        raise HTTPException(status_code=400, detail="Schema discovery is only supported for hubspot")

    from app.integrations.registry import get_connector_for_integration
    from app.integrations.schema_mapper import discover as _discover

    integration = None
    if integration_service:
        integration = integration_service.get_integration(tenant_id=tenant_id, provider=provider)
    if not integration:
        raise HTTPException(status_code=404, detail="HubSpot not connected for this tenant")

    try:
        connector = get_connector_for_integration(integration["id"])
        if not connector:
            raise HTTPException(status_code=404, detail="Could not load HubSpot connector")
        raw_props = connector.pull_company_properties()
        mapping = _discover(raw_props, business_mode=mode)
        return mapping.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[schema] %s: %s", provider, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/integrations/{provider}/viability-audit")
def run_viability_audit(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Run the Phase 0 pre-training viability audit for a connected HubSpot portal.

    Executes three label-source scan paths (company properties, deal pipelines,
    lifecycle stages), selects the best candidate, counts labeled examples, and
    assesses reliability. Returns a ViabilityReport with a viability decision:
      proceed       — ≥100 positive examples, balanced, reliable
      exploratory   — marginal but trainable (confidence downgraded)
      insufficient  — below exploratory threshold
      blocked       — <20 examples or no label source found

    Stores the result to disk so training can gate on it.
    """
    if provider != "hubspot":
        raise HTTPException(status_code=400, detail="Viability audit is only supported for hubspot")

    from app.integrations.registry import get_connector_for_integration
    from app.integrations.label_discovery import discover_candidates
    from app.integrations.label_auditor import run_audit, save_audit

    integration = None
    if integration_service:
        integration = integration_service.get_integration(tenant_id=tenant_id, provider=provider)
    if not integration:
        raise HTTPException(status_code=404, detail="HubSpot not connected for this tenant")

    connector = get_connector_for_integration(integration["id"])
    if not connector:
        raise HTTPException(status_code=404, detail="Could not load HubSpot connector")

    try:
        # Pull metadata needed for discovery (two API calls, fast)
        company_props = connector.pull_company_properties()
        deal_pipelines = connector.pull_deal_pipelines()

        # Discover label source candidates
        candidates = discover_candidates(company_props, deal_pipelines)

        if not candidates:
            report = {
                "viability": "blocked",
                "label_source": None,
                "counts": {
                    "positive_examples": 0, "negative_examples": 0,
                    "unlabeled_companies": 0, "total_labeled": 0,
                    "class_ratio": None, "oldest_outcome": None, "most_recent_outcome": None,
                },
                "reliability": {"score": 0.0, "issues": ["No label source candidates found in this portal"]},
                "decision": {
                    "viability": "blocked",
                    "rationale": "No property or deal pipeline was identified as a churn/non-renewal label source.",
                    "confidence_mode": None,
                    "next_steps": [
                        "Add a company property to track churn/renewal status (e.g. a boolean 'churned' field)",
                        "Or create a renewal deal pipeline with distinct Closed Won and Closed Lost stages",
                    ],
                },
                "audit_at": datetime.now(timezone.utc).isoformat(),
                "tenant_id": tenant_id,
            }
            save_audit(tenant_id, report)
            return report

        # Audit the top candidate (highest confidence)
        best_candidate = candidates[0]
        report = run_audit(connector, best_candidate, tenant_id)

        # Surface all candidates as alternates in the report
        report["candidate_alternates"] = [c.to_dict() for c in candidates[1:5]]

        save_audit(tenant_id, report)
        return report

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[viability-audit] %s tenant=%s: %s", provider, tenant_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/integrations/{provider}/viability-audit")
def get_viability_audit(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Return the most recently stored ViabilityReport for this tenant.

    Returns 404 if no audit has been run yet.
    """
    if provider != "hubspot":
        raise HTTPException(status_code=400, detail="Viability audit is only supported for hubspot")

    from app.integrations.label_auditor import load_audit

    report = load_audit(tenant_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail="No viability audit found. Run POST /api/integrations/hubspot/viability-audit first.",
        )
    return report


@app.get("/api/integrations/{provider}/data-quality")
def integration_data_quality(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Return a data quality audit of the most recently synced accounts.

    Computes per-field coverage (% non-null) and classifies each field as
    usable (≥70%), low_coverage (30–70%), or too_sparse (<30%).
    """
    if provider != "hubspot":
        raise HTTPException(status_code=400, detail="Data quality is only supported for hubspot")

    from app.storage import repo
    from app.integrations.normalization import audit_records

    accounts = repo.list_accounts(limit=5000, tenant_id=tenant_id)
    if not accounts:
        return {
            "n_records": 0,
            "message": "No accounts synced yet — run a sync first",
            "field_stats": {},
            "usable_fields": [],
            "low_coverage_fields": [],
            "sparse_fields": [],
            "overall_coverage_pct": 0.0,
        }

    # Pull normalized data from raw_data._normalized if present
    scored_fields = [
        "arr", "company_size", "renewal_date", "days_until_renewal",
        "contract_months_remaining", "industry", "plan", "nps_score",
        "days_since_last_login", "days_since_last_activity",
    ]
    records = []
    for acct in accounts:
        raw = acct.get("raw_data") or {}
        normalized = raw.get("_normalized") or {}
        # Supplement with top-level account fields
        record = {
            "arr": acct.get("arr") or normalized.get("arr"),
            "company_size": acct.get("company_size") or normalized.get("company_size"),
            "industry": acct.get("industry") or normalized.get("industry"),
            "plan": acct.get("plan") or normalized.get("plan"),
            **{f: normalized.get(f) for f in scored_fields if f not in ("arr", "company_size", "industry", "plan")},
        }
        records.append(record)

    return audit_records(records, fields=scored_fields)


@app.get("/api/integrations/{provider}/readiness")
def integration_readiness(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Data quality report and training eligibility for a synced CRM provider.

    Works for both HubSpot and Salesforce. Queries only already-synced data —
    no live CRM API calls. Returns:
      - total_accounts, churned_detected, pct_with_signals, pct_with_arr
      - expected_confidence: High / Medium / Low (deterministic thresholds)
      - eligibility: ready | needs_outcome_mapping | insufficient_churn |
                     low_signal_coverage | insufficient_data
      - candidate_fields: raw_data fields suitable for custom label mapping
      - label_mapping: currently saved custom mapping, if any
    """
    from app.integrations.readiness import compute_readiness
    try:
        return compute_readiness(tenant_id, provider)
    except Exception as exc:
        logger.warning("[readiness] compute failed for %s tenant=%s: %s", provider, tenant_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/integrations/{provider}/label-mapping")
def get_label_mapping(provider: str, tenant_id: str = Depends(get_tenant_id)):
    """Return the saved custom label mapping for this provider, or empty dict if none."""
    from app.integrations.readiness import load_label_mapping
    return load_label_mapping(tenant_id, provider) or {}


class LabelMappingRequest(PydanticBaseModel):
    field_name: str = Field(..., max_length=200)
    churned_values: List[str] = Field(..., min_length=1)

    @field_validator("field_name")
    @classmethod
    def strip_field_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("churned_values")
    @classmethod
    def strip_values(cls, v: List[str]) -> List[str]:
        cleaned = [s.strip() for s in v if s.strip()]
        if not cleaned:
            raise ValueError("churned_values must contain at least one non-empty string")
        return cleaned


@app.post("/api/integrations/{provider}/label-mapping")
def save_label_mapping_endpoint(
    provider: str,
    body: LabelMappingRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """Save a custom churn label mapping and re-import outcomes using the new definition.

    Workflow:
      1. Persist mapping to disk ({DATA_DIR}/outputs/{tenant_id}/label_mapping_{provider}.json)
      2. Delete all auto-imported outcomes for this tenant
      3. Re-run outcome import on all synced accounts with the new mapping
      4. Return updated readiness report
    """
    from app.integrations.readiness import save_label_mapping, compute_readiness
    from app.integrations.outcome_import import import_outcomes_from_accounts
    from app.integrations.models import Account
    from app.storage import repo

    mapping = save_label_mapping(tenant_id, provider, body.field_name, body.churned_values)

    outcomes_reimported = 0
    try:
        repo.delete_auto_imported_outcomes(tenant_id)
        accounts_db = repo.list_accounts(source=provider, limit=10_000, tenant_id=tenant_id)
        accounts = [
            Account(
                external_id=a["external_id"],
                source=provider,
                name=a.get("name") or a.get("external_id", ""),
                raw_data=a.get("raw_data") or {},
            )
            for a in accounts_db
            if a.get("external_id")
        ]
        outcomes_reimported = import_outcomes_from_accounts(accounts, provider, tenant_id)
        logger.info(
            "[label-mapping] re-imported %d outcomes for %s tenant=%s",
            outcomes_reimported, provider, tenant_id,
        )
    except Exception as exc:
        logger.warning("[label-mapping] re-import failed: %s", exc)

    try:
        readiness = compute_readiness(tenant_id, provider)
    except Exception:
        readiness = None

    return {
        "mapping": mapping,
        "outcomes_reimported": outcomes_reimported,
        "readiness": readiness,
    }


@app.get("/api/integrations/{provider}/events")
def get_integration_events(provider: str, limit: int = Query(50), tenant_id: str = Depends(get_tenant_id)):
    """Get audit events for a provider."""
    _require_service()
    integration = integration_service.get_integration(
        tenant_id=tenant_id, provider=provider
    )
    if not integration:
        return {"provider": provider, "events": []}

    events = integration_service.get_events(integration["id"], limit=limit)
    return {"provider": provider, "events": events}


@app.get("/api/integrations/{provider_name}/status")
def integration_status(provider_name: str, tenant_id: str = Depends(get_tenant_id)):
    """Get detailed status for a specific connector."""
    # Try new service layer
    integration = None
    if integration_service:
        integration = integration_service.get_integration(
            tenant_id=tenant_id, provider=provider_name
        )
    if integration:
        return {
            "name": provider_name,
            "status": integration["status"],
            "enabled": integration["enabled"],
            "account_count": storage_repo.account_count(source=provider_name, tenant_id=tenant_id),
            "connected_at": integration.get("connected_at"),
        }

    # Fall back to legacy
    cfg = connector_registry.get_config(provider_name)
    if not cfg:
        return {
            "name": provider_name,
            "status": "not_configured",
            "enabled": False,
            "account_count": 0,
        }

    connector = connector_registry.get_connector(provider_name)
    connected = connector.test_connection() if connector else False

    return {
        "name": provider_name,
        "status": "healthy" if connected else "error",
        "enabled": cfg.enabled,
        "account_count": storage_repo.account_count(source=provider_name, tenant_id=tenant_id),
        "last_sync": cfg.extra.get("last_sync_result"),
    }


@app.get("/api/integrations/accounts")
def list_integration_accounts(
    source: Optional[str] = Query(None),
    limit: int = Query(200),
    offset: int = Query(0),
    tenant_id: str = Depends(get_tenant_id),
):
    """List accounts from the integration database."""
    accounts = storage_repo.list_accounts(source=source, limit=limit, offset=offset, tenant_id=tenant_id)
    total = storage_repo.account_count(source=source, tenant_id=tenant_id)
    return {"accounts": accounts, "total": total, "showing": len(accounts)}


@app.post("/api/integrations/score")
def trigger_live_scoring(
    source: Optional[str] = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    """Score integrated accounts using the trained churn model.

    source: optional CRM provider name (e.g. "salesforce", "hubspot").
    When provided, only that provider's accounts are scored and the active-source
    context is updated to reflect the provider.  When omitted, all accounts are
    scored (legacy behaviour — retained for backward compatibility).

    Model resolution order (first model found wins):
      1. {source}_churn model — provider-specific CRM-native model
      2. generic churn model — CSV-trained fallback
    """
    # Resolve the effective provider first (needed for model selection)
    effective_source = source or _get_crm_provider(tenant_id)

    # Try provider-specific model first, then fall back to generic churn
    mod = None
    artifact_dir = None
    if effective_source and effective_source in ("hubspot", "salesforce"):
        crm_module_name = f"{effective_source}_churn"
        try:
            crm_mod = get_module(crm_module_name)
            crm_run = store.get_current_model_run(tenant_id, crm_module_name)
            if crm_run and crm_run.get("artifact_path"):
                crm_artifact_dir = crm_run["artifact_path"]
            else:
                crm_artifact_dir = crm_mod.get_artifact_dir(tenant_id)
            if os.path.exists(os.path.join(crm_artifact_dir, "model.joblib")):
                mod = crm_mod
                artifact_dir = crm_artifact_dir
                logger.info("[scoring] using provider-specific model: %s", crm_module_name)
        except Exception:
            pass  # module not registered or other error — fall through to generic

    if mod is None:
        mod = get_module("churn")
        current_run = store.get_current_model_run(tenant_id, "churn")
        if current_run and current_run.get("artifact_path"):
            artifact_dir = current_run["artifact_path"]
        else:
            artifact_dir = mod.get_artifact_dir(tenant_id)  # legacy fallback
        logger.info("[scoring] using generic churn model")

    model_path = os.path.join(artifact_dir, "model.joblib")

    if not os.path.exists(model_path):
        raise HTTPException(status_code=400, detail="No trained model. Train a model first.")

    # Resolve the effective provider: prefer explicit source param; fall back to
    # the provider recorded from the previous scoring run so that "Rescore All"
    acct_count = storage_repo.account_count(source=effective_source, tenant_id=tenant_id)
    if acct_count == 0:
        raise HTTPException(status_code=400, detail="No accounts in database. Sync an integration first.")

    # In demo mode, ensure signals/outcomes are present before scoring.
    # This is a safety-net only — data should already be loaded from trigger_sync.
    if DEMO_MODE and effective_source in ("hubspot", "salesforce"):
        demo_resolver.ensure_demo_data(tenant_id, provider=effective_source)

    try:
        scores = score_accounts(tenant_id=tenant_id, artifact_dir=artifact_dir, source=effective_source)
        # Store the specific provider name — never the generic string "crm".
        # _set_active_source collapses crm_provider into active_source when provided.
        _set_active_source(tenant_id, effective_source or "crm")
        high = sum(1 for s in scores if s.tier == "High Risk")
        med = sum(1 for s in scores if s.tier == "Medium Risk")
        low = sum(1 for s in scores if s.tier == "Low Risk")
        total_arr = sum(s.arr_at_risk or 0 for s in scores)

        # HubSpot property writeback — fire-and-forget in a daemon thread.
        # Filters to hubspot-source accounts only so CSV-sourced accounts in
        # the same tenant are never pushed.  Task deduplication is skipped in
        # this path (V1): _run_hubspot_writeback will see an empty task-id map
        # for CRM accounts and may create tasks for high-risk accounts each run.
        # Full dedup against churn_scores_daily is a V2 item.
        try:
            scored_rows = storage_repo.latest_scores(limit=10000, tenant_id=tenant_id)
            signals_by_account = storage_repo.bulk_latest_signals(tenant_id)
            writeback_records = []
            for row in scored_rows:
                if row.get("source") != "hubspot":
                    continue
                ext_id = row.get("external_id") or ""
                if not ext_id:
                    continue
                acct_uuid = row.get("account_id", "")
                sig = signals_by_account.get(acct_uuid, {})
                days_until_renewal = sig.get("days_until_renewal")
                writeback_records.append({
                    # account_id used by _run_hubspot_writeback for task dedup lookup
                    "account_id": ext_id,
                    # hs_object_id is the HubSpot company Record ID; for HubSpot-
                    # sourced accounts this is identical to external_id.
                    "hs_object_id": ext_id,
                    "churn_risk_pct": row.get("churn_risk_pct"),
                    "tier": row.get("tier"),
                    "arr_at_risk": row.get("arr_at_risk"),
                    "recommended_action": row.get("recommended_action"),
                    "days_until_renewal": (
                        int(float(days_until_renewal))
                        if days_until_renewal is not None else None
                    ),
                })
            if writeback_records:
                _spawn_hubspot_writeback(tenant_id, writeback_records)
                logger.info(
                    "[integrations/score] Queued HubSpot writeback for %d accounts (tenant %s)",
                    len(writeback_records), tenant_id,
                )
        except Exception as wb_exc:
            logger.warning(
                "[integrations/score] HubSpot writeback setup failed for tenant %s: %s",
                tenant_id, wb_exc,
            )

        return {
            "status": "scored",
            "accounts_scored": len(scores),
            "tier_counts": {"High Risk": high, "Medium Risk": med, "Low Risk": low},
            "total_arr_at_risk": round(total_arr, 2),
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/integrations/scores/latest")
def get_latest_scores(
    limit: int = Query(10000),
    source: Optional[str] = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    """Get the most recent churn scores for accounts.

    source: explicit provider filter.  When omitted, auto-detects from the
    active-source context so scores always reflect the currently active integration.
    """
    effective_source = source or _get_crm_provider(tenant_id)
    scores = storage_repo.latest_scores(limit=limit, tenant_id=tenant_id, source=effective_source)
    return {"scores": scores, "count": len(scores)}


@app.post("/api/integrations/{connector_name}/run-demo")
def run_demo(connector_name: str, tenant_id: str = Depends(get_tenant_id)):
    """One-click: validate connector → sync → score. Returns combined result."""
    # In demo mode, CRM providers use synthetic datasets — load directly.
    if demo_resolver.should_use_synthetic(connector_name):
        load_result = demo_resolver.ensure_demo_data(tenant_id, provider=connector_name)
        sync_result = type("_SR", (), {
            "accounts_synced": load_result.account_count,
            "signals_synced": load_result.signal_count,
            "errors": load_result.errors,
            "duration_seconds": 0,
        })()
    else:
        # Try new sync first, fall back to legacy
        try:
            if not integration_service:
                raise RuntimeError("service unavailable")
            sync_result = integration_service.trigger_sync(tenant_id, connector_name)
        except Exception:
            cfg = connector_registry.get_config(connector_name)
            if not cfg or not cfg.enabled:
                raise HTTPException(
                    status_code=400,
                    detail=f"Connector '{connector_name}' is not configured. Call /connect first.",
                )
            sync_result = sync_connector(connector_name)

    # Score (only if we have accounts + a trained model)
    scored = 0
    tier_counts: Dict[str, int] = {}
    total_arr = 0.0
    score_error = None

    mod = get_module("churn")
    current_run = store.get_current_model_run(tenant_id, "churn")
    if current_run and current_run.get("artifact_path"):
        artifact_dir = current_run["artifact_path"]
    else:
        artifact_dir = mod.get_artifact_dir(tenant_id)  # legacy fallback
    model_exists = os.path.exists(os.path.join(artifact_dir, "model.joblib"))
    acct_count = storage_repo.account_count(tenant_id=tenant_id)

    if model_exists and acct_count > 0:
        if DEMO_MODE and not demo_resolver.should_use_synthetic(connector_name):
            # CSV demo path — still uses the original signal seeder.
            auto_seed_if_needed(tenant_id=tenant_id)
        try:
            # Pass connector_name as source so only this provider's accounts are
            # scored and the context file records the specific provider name.
            scores = score_accounts(tenant_id=tenant_id, artifact_dir=artifact_dir, source=connector_name)
            _set_active_source(tenant_id, connector_name)
            scored = len(scores)
            tier_counts = {
                "High Risk": sum(1 for s in scores if s.tier == "High Risk"),
                "Medium Risk": sum(1 for s in scores if s.tier == "Medium Risk"),
                "Low Risk": sum(1 for s in scores if s.tier == "Low Risk"),
            }
            total_arr = round(sum(s.arr_at_risk or 0 for s in scores), 2)
        except Exception as e:
            score_error = str(e)
    elif not model_exists:
        score_error = "No trained model — sync succeeded but scoring was skipped."

    now = datetime.now(timezone.utc).isoformat()
    return {
        "status": "ok" if not sync_result.errors and not score_error else "partial",
        "connector": connector_name,
        "synced_accounts": sync_result.accounts_synced,
        "synced_signals": sync_result.signals_synced,
        "scored_accounts": scored,
        "tier_counts": tier_counts,
        "total_arr_at_risk": total_arr,
        "score_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "model_version": "churn_v1" if model_exists else None,
        "last_sync_at": now,
        "last_scored_at": now if scored > 0 else None,
        "sync_errors": sync_result.errors,
        "score_error": score_error,
    }


# -----------------------------------------------------------------------
# Cron / automation auth
# -----------------------------------------------------------------------
CRON_API_KEY = os.environ.get("CRON_API_KEY", "")


def _verify_cron_key(key: str) -> None:
    """Raise 401 if the key doesn't match CRON_API_KEY."""
    if not CRON_API_KEY:
        raise HTTPException(status_code=500, detail="CRON_API_KEY not configured on server.")
    if key != CRON_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid cron API key.")


@app.get("/api/debug/oauth-config")
def debug_oauth_config(key: str = Query(...)):
    """Temporary debug: show OAuth config (guarded by CRON_API_KEY)."""
    _verify_cron_key(key)
    api_base = os.environ.get("API_BASE_URL", "(not set)")
    client_id = os.environ.get("HUBSPOT_CLIENT_ID", "(not set)")
    callback_url = f"{api_base.rstrip('/')}/api/integrations/hubspot/oauth/callback"
    has_secret = bool(os.environ.get("OAUTH_STATE_SECRET"))
    has_client_secret = bool(os.environ.get("HUBSPOT_CLIENT_SECRET"))
    # Generate a test auth URL if possible
    test_url = ""
    try:
        _require_service()
        result = integration_service.start_oauth(
            _DEFAULT_TENANT, "hubspot", "https://demo.pickpulse.co/integrations"
        )
        test_url = result.get("auth_url", "")
    except Exception as exc:
        test_url = f"ERROR: {exc}"
    return {
        "api_base_url": api_base,
        "hubspot_client_id": client_id[:8] + "..." if len(client_id) > 8 else client_id,
        "hubspot_callback_url": callback_url,
        "oauth_state_secret_set": has_secret,
        "hubspot_client_secret_set": has_client_secret,
        "test_auth_url_first_300": test_url[:300],
        "test_auth_url_contains_scope": "scope=" in test_url,
        "test_auth_url_contains_state": "state=" in test_url,
        "test_auth_url_contains_response_type": "response_type=" in test_url,
    }


@app.post("/api/cron/sync-all")
def cron_sync_all(x_cron_key: str = Query(..., alias="key")):
    """Scheduled endpoint: sync all enabled connectors. Requires CRON_API_KEY."""
    _verify_cron_key(x_cron_key)
    results = sync_all()
    return {
        "status": "ok",
        "results": [
            {
                "connector": r.connector,
                "accounts": r.accounts_synced,
                "signals": r.signals_synced,
                "errors": r.errors,
            }
            for r in results
        ],
    }


@app.post("/api/cron/score")
def cron_score(x_cron_key: str = Query(..., alias="key")):
    """Scheduled endpoint: score all synced accounts. Requires CRON_API_KEY."""
    _verify_cron_key(x_cron_key)

    mod = get_module("churn")
    if not os.path.exists(os.path.join(mod.artifact_dir, "model.joblib")):
        return {"status": "skipped", "reason": "No trained model"}

    if storage_repo.account_count() == 0:
        return {"status": "skipped", "reason": "No accounts synced"}

    scores = score_accounts()
    return {
        "status": "ok",
        "scored": len(scores),
        "total_arr_at_risk": round(sum(s.arr_at_risk or 0 for s in scores), 2),
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

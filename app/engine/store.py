"""Persistence layer for PickPulse engine tables.

ALL reads and writes to datasets, model_runs, predictions_live, and audit_log
MUST go through this module. Do not import the Supabase client or execute SQL
against these tables from any other file.

Public API
----------
Datasets:
    save_dataset(tenant_id, module, info)
    get_current_dataset(tenant_id, module) -> dict | None

Model runs:
    create_model_run(tenant_id, module, run_id, artifact_path) -> dict
    update_model_run(run_id, **fields)
    get_model_run(run_id) -> dict | None
    get_current_model_run(tenant_id, module) -> dict | None
    set_current_model_run(tenant_id, module, run_id)
    list_model_runs(tenant_id, module) -> list[dict]
    fail_stale_model_runs(older_than_minutes) — call at startup

Predictions:
    save_predictions(tenant_id, module, run_id, records)
    get_predictions(tenant_id, module) -> list[dict]
    update_account_status(tenant_id, account_id, status)
    get_account_statuses(tenant_id) -> dict[str, str]

Audit:
    log_action(tenant_id, action, entity_id, metadata, user_id)

Availability
------------
All functions gracefully no-op (with a logged warning) when Supabase is not
configured (SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing). This allows
local development without a Supabase instance — in-memory state is still
available via _get_state() in console_api.py.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supabase client access
# ---------------------------------------------------------------------------

def _available() -> bool:
    """Return True if Supabase credentials are configured."""
    return bool(
        os.environ.get("SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )


def _db():
    """Return the Supabase service-role client."""
    from ..storage.db import get_client
    return get_client()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

def save_dataset(tenant_id: str, module: str, info: Dict[str, Any]) -> None:
    """Upsert the current dataset registration for a tenant+module.

    Marks all previous registrations for this tenant+module as is_current=False,
    then inserts a new row with is_current=True.
    """
    if not _available():
        logger.debug("[store] Supabase not configured — save_dataset skipped")
        return
    try:
        db = _db()
        # Deactivate previous current dataset for this tenant+module
        db.table("datasets").update({"is_current": False}).eq(
            "tenant_id", tenant_id
        ).eq("module", module).eq("is_current", True).execute()

        # Insert new current row
        db.table("datasets").insert({
            "tenant_id": tenant_id,
            "module": module,
            "filename": info.get("name"),
            "raw_path": info.get("path"),
            "readiness_mode": info.get("readiness_mode"),
            "source_columns": json.dumps(info.get("source_columns", [])),
            "confirmed_mappings": json.dumps(info.get("confirmed_mappings", {})),
            "is_current": True,
            "registered_at": _now_iso(),
        }).execute()
    except Exception as exc:
        logger.warning("[store] save_dataset failed: %s", exc)


def get_current_dataset(tenant_id: str, module: str) -> Optional[Dict[str, Any]]:
    """Return the current dataset info dict for a tenant+module, or None."""
    if not _available():
        return None
    try:
        db = _db()
        resp = (
            db.table("datasets")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("module", module)
            .eq("is_current", True)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        row = resp.data[0]
        # Re-hydrate to the dict shape that console_api.py expects
        return {
            "path": row.get("raw_path"),
            "name": row.get("filename"),
            "readiness_mode": row.get("readiness_mode"),
            "source_columns": row.get("source_columns") or [],
            "confirmed_mappings": row.get("confirmed_mappings") or {},
            "registered_at": row.get("registered_at"),
        }
    except Exception as exc:
        logger.warning("[store] get_current_dataset failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Model runs
# ---------------------------------------------------------------------------

def create_model_run(
    tenant_id: str,
    module: str,
    run_id: str,
    artifact_path: str,
) -> Dict[str, Any]:
    """Insert a new model_run row with status=pending. Returns the row dict."""
    row = {
        "id": run_id,
        "tenant_id": tenant_id,
        "module": module,
        "artifact_path": artifact_path,
        "status": "pending",
        "is_current": False,
        "trained_at": _now_iso(),
    }
    if not _available():
        logger.debug("[store] Supabase not configured — create_model_run skipped")
        return row
    try:
        _db().table("model_runs").insert(row).execute()
    except Exception as exc:
        logger.warning("[store] create_model_run failed: %s", exc)
    return row


def update_model_run(run_id: str, **fields: Any) -> None:
    """Update any subset of model_run columns by run_id."""
    if not _available():
        return
    try:
        # Convert non-serializable values (datetime → ISO string)
        payload: Dict[str, Any] = {}
        for k, v in fields.items():
            if isinstance(v, datetime):
                payload[k] = v.isoformat()
            elif isinstance(v, (dict, list)):
                payload[k] = json.dumps(v)
            else:
                payload[k] = v
        _db().table("model_runs").update(payload).eq("id", run_id).execute()
    except Exception as exc:
        logger.warning("[store] update_model_run failed: %s", exc)


def get_model_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Return a single model_run row by id, or None."""
    if not _available():
        return None
    try:
        resp = _db().table("model_runs").select("*").eq("id", run_id).limit(1).execute()
        return resp.data[0] if resp.data else None
    except Exception as exc:
        logger.warning("[store] get_model_run failed: %s", exc)
        return None


def get_current_model_run(tenant_id: str, module: str) -> Optional[Dict[str, Any]]:
    """Return the is_current=True model_run for a tenant+module, or None."""
    if not _available():
        return None
    try:
        resp = (
            _db().table("model_runs")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("module", module)
            .eq("is_current", True)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as exc:
        logger.warning("[store] get_current_model_run failed: %s", exc)
        return None


def set_current_model_run(tenant_id: str, module: str, run_id: str) -> None:
    """Flip is_current: True on run_id, False on all other runs for tenant+module."""
    if not _available():
        return
    try:
        db = _db()
        db.table("model_runs").update({"is_current": False}).eq(
            "tenant_id", tenant_id
        ).eq("module", module).eq("is_current", True).execute()
        db.table("model_runs").update({"is_current": True}).eq("id", run_id).execute()
    except Exception as exc:
        logger.warning("[store] set_current_model_run failed: %s", exc)


def list_model_runs(tenant_id: str, module: str) -> List[Dict[str, Any]]:
    """Return all model_runs for tenant+module ordered by trained_at desc."""
    if not _available():
        return []
    try:
        resp = (
            _db().table("model_runs")
            .select("id, version_str, status, metrics_json, artifact_path, is_current, trained_at, completed_at")
            .eq("tenant_id", tenant_id)
            .eq("module", module)
            .order("trained_at", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.warning("[store] list_model_runs failed: %s", exc)
        return []


def fail_stale_model_runs(older_than_minutes: int = 60) -> None:
    """Mark any model_run still 'running' from a previous process as 'failed'.

    Call at application startup to clean up jobs that were abandoned when the
    previous process was killed (e.g. by a Render deploy).
    """
    if not _available():
        return
    try:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        ).isoformat()
        resp = (
            _db().table("model_runs")
            .update({
                "status": "failed",
                "error_message": "Process was killed before this job completed (stale cleanup at startup)",
                "completed_at": _now_iso(),
            })
            .eq("status", "running")
            .lt("started_at", cutoff)
            .execute()
        )
        if resp.data:
            logger.info("[store] Marked %d stale model_run(s) as failed", len(resp.data))
    except Exception as exc:
        logger.warning("[store] fail_stale_model_runs failed: %s", exc)


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

def save_predictions(
    tenant_id: str,
    module: str,
    run_id: str,
    records: List[Dict[str, Any]],
) -> None:
    """Upsert all prediction records for a tenant+module.

    Each record must have an 'account_id' key. Uses upsert on the
    (tenant_id, module, account_id) unique constraint so re-running predict
    overwrites previous scores.
    """
    if not _available():
        return
    if not records:
        return
    try:
        db = _db()
        rows = []
        for rec in records:
            account_id = str(rec.get("account_id", ""))
            if not account_id:
                continue
            rows.append({
                "tenant_id": tenant_id,
                "module": module,
                "model_run_id": run_id,
                "account_id": account_id,
                "score": float(rec.get("churn_risk_pct") or rec.get("probability") or 0) / 100
                if "churn_risk_pct" in rec
                else float(rec.get("probability") or 0),
                "confidence_tier": rec.get("tier"),
                "prediction_json": json.dumps(rec),
                "predicted_at": _now_iso(),
            })
        if rows:
            db.table("predictions_live").upsert(
                rows,
                on_conflict="tenant_id,module,account_id",
            ).execute()
    except Exception as exc:
        logger.warning("[store] save_predictions failed: %s", exc)


def get_predictions(tenant_id: str, module: str) -> List[Dict[str, Any]]:
    """Return current prediction records for tenant+module.

    Returns the full prediction_json records merged with current account status.
    """
    if not _available():
        return []
    try:
        resp = (
            _db().table("predictions_live")
            .select("account_id, score, confidence_tier, status, status_changed_at, prediction_json")
            .eq("tenant_id", tenant_id)
            .eq("module", module)
            .order("score", desc=True)
            .execute()
        )
        records = []
        for row in (resp.data or []):
            rec = row.get("prediction_json") or {}
            if isinstance(rec, str):
                rec = json.loads(rec)
            # Overlay live status onto the prediction record
            rec["_account_status"] = row.get("status", "none")
            records.append(rec)
        return records
    except Exception as exc:
        logger.warning("[store] get_predictions failed: %s", exc)
        return []


def update_account_status(tenant_id: str, account_id: str, status: str) -> None:
    """Update the CSM status for a single account in predictions_live."""
    if not _available():
        return
    try:
        _db().table("predictions_live").update({
            "status": status,
            "status_changed_at": _now_iso(),
        }).eq("tenant_id", tenant_id).eq("account_id", account_id).execute()
    except Exception as exc:
        logger.warning("[store] update_account_status failed: %s", exc)


def get_account_statuses(tenant_id: str) -> Dict[str, str]:
    """Return {account_id: status} for all accounts with a non-default status."""
    if not _available():
        return {}
    try:
        resp = (
            _db().table("predictions_live")
            .select("account_id, status")
            .eq("tenant_id", tenant_id)
            .neq("status", "none")
            .execute()
        )
        return {row["account_id"]: row["status"] for row in (resp.data or [])}
    except Exception as exc:
        logger.warning("[store] get_account_statuses failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def log_action(
    tenant_id: str,
    action: str,
    entity_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> None:
    """Append an entry to the audit log."""
    if not _available():
        return
    try:
        _db().table("audit_log").insert({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action": action,
            "entity_id": entity_id,
            "metadata_json": json.dumps(metadata or {}),
            "created_at": _now_iso(),
        }).execute()
    except Exception as exc:
        # Audit log failures must never surface to the user — log and continue.
        logger.warning("[store] log_action failed (action=%s): %s", action, exc)

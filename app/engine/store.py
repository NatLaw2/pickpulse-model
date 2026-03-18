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
    get_prediction_for_account(tenant_id, module, account_id) -> dict | None
    get_prediction_by_hs_object_id(tenant_id, module, hs_object_id) -> dict | None
    patch_prediction_json(tenant_id, module, account_id, patch)
    get_accounts_with_task_ids(tenant_id, module) -> dict[str, str]
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

_unavailable_warned = False


def _available() -> bool:
    """Return True if Supabase credentials are configured."""
    global _unavailable_warned
    ok = bool(
        os.environ.get("SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )
    if not ok and not _unavailable_warned:
        _unavailable_warned = True
        logger.warning(
            "[store] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set — "
            "all DB operations will be skipped. Set both env vars in the Render dashboard."
        )
    return ok


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
            "source_columns": info.get("source_columns", []),
            "confirmed_mappings": info.get("confirmed_mappings", {}),
            "row_count": int(info.get("rows") or 0),
            "column_count": int(info.get("columns") or 0),
            "is_demo": bool(info.get("is_demo", False)),
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
        # Re-hydrate to the dict shape that console_api.py expects.
        # registered_at doubles as loaded_at — both represent when the dataset
        # was registered; no separate column is needed.
        return {
            "path": row.get("raw_path"),
            "name": row.get("filename"),
            "readiness_mode": row.get("readiness_mode"),
            "source_columns": row.get("source_columns") or [],
            "confirmed_mappings": row.get("confirmed_mappings") or {},
            "rows": row.get("row_count") or 0,
            "columns": row.get("column_count") or 0,
            "is_demo": bool(row.get("is_demo", False)),
            "loaded_at": row.get("registered_at"),
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
        # Convert non-serializable values (datetime → ISO string).
        # dict/list values are passed as-is; supabase-py serialises them to
        # JSONB natively.  Wrapping with json.dumps() would produce a
        # string-inside-JSONB which is not queryable.
        payload: Dict[str, Any] = {}
        for k, v in fields.items():
            if isinstance(v, datetime):
                payload[k] = v.isoformat()
            else:
                payload[k] = v
        _db().table("model_runs").update(payload).eq("id", run_id).execute()
    except Exception as exc:
        logger.warning("[store] update_model_run failed: %s", exc)


def get_model_run(run_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return a single model_run row by id, or None.

    When tenant_id is provided the query filters by both id AND tenant_id, so a
    caller can never retrieve a run that belongs to a different tenant.
    """
    if not _available():
        return None
    try:
        q = _db().table("model_runs").select("*").eq("id", run_id)
        if tenant_id is not None:
            q = q.eq("tenant_id", tenant_id)
        resp = q.limit(1).execute()
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
    """Flip is_current: True on run_id, False on all other runs for tenant+module.

    Order is deliberate: promote the new run first, then demote the old one.
    This means any predict call landing between the two updates uses the new
    model (correct behaviour) rather than finding no current model at all.
    """
    if not _available():
        return
    try:
        db = _db()
        db.table("model_runs").update({"is_current": True}).eq("id", run_id).execute()
        db.table("model_runs").update({"is_current": False}).eq(
            "tenant_id", tenant_id
        ).eq("module", module).eq("is_current", True).neq("id", run_id).execute()
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
    """Mark abandoned training jobs as failed at application startup.

    Handles two abandoned states:

    1. status=running, older than older_than_minutes — the training thread was
       executing when the process was killed. Use a long threshold (default 60 min)
       to avoid failing legitimately long-running jobs.

    2. status=pending, older than 5 minutes — the job row was created but the
       daemon thread was never spawned (process died between create_model_run and
       Thread.start). A pending job that is still pending after 5 minutes is
       definitively orphaned.

    Call at application startup only.
    """
    if not _available():
        return
    db = _db()
    now = datetime.now(timezone.utc)

    # --- running jobs abandoned mid-execution ---
    try:
        running_cutoff = (now - timedelta(minutes=older_than_minutes)).isoformat()
        resp = (
            db.table("model_runs")
            .update({
                "status": "failed",
                "error_message": "Process was killed before this job completed (stale cleanup at startup)",
                "completed_at": _now_iso(),
            })
            .eq("status", "running")
            .lt("started_at", running_cutoff)
            .execute()
        )
        if resp.data:
            logger.info("[store] Marked %d stale running model_run(s) as failed", len(resp.data))
    except Exception as exc:
        logger.warning("[store] fail_stale_model_runs (running) failed: %s", exc)

    # --- pending jobs whose thread was never spawned ---
    try:
        pending_cutoff = (now - timedelta(minutes=5)).isoformat()
        resp = (
            db.table("model_runs")
            .update({
                "status": "failed",
                "error_message": "Job was never picked up — process likely died before thread could start (stale cleanup at startup)",
                "completed_at": _now_iso(),
            })
            .eq("status", "pending")
            .lt("trained_at", pending_cutoff)
            .execute()
        )
        if resp.data:
            logger.info("[store] Marked %d orphaned pending model_run(s) as failed", len(resp.data))
    except Exception as exc:
        logger.warning("[store] fail_stale_model_runs (pending) failed: %s", exc)


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
                "prediction_json": rec,
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
    Each record includes a _predicted_at field (ISO timestamp) so callers can
    validate whether predictions are current relative to the active dataset.
    """
    if not _available():
        return []
    try:
        resp = (
            _db().table("predictions_live")
            .select("account_id, score, confidence_tier, status, status_changed_at, prediction_json, predicted_at")
            .eq("tenant_id", tenant_id)
            .eq("module", module)
            .not_.is_("score", "null")   # exclude status-only placeholder rows
            .order("score", desc=True)
            .execute()
        )
        records = []
        for row in (resp.data or []):
            rec = row.get("prediction_json") or {}
            if isinstance(rec, str):
                rec = json.loads(rec)
            # Overlay live status and provenance onto the prediction record
            rec["_account_status"] = row.get("status", "none")
            rec["_predicted_at"] = row.get("predicted_at") or ""
            records.append(rec)
        return records
    except Exception as exc:
        logger.warning("[store] get_predictions failed: %s", exc)
        return []


def delete_tenant_predictions(tenant_id: str, module: str = "churn") -> None:
    """Delete all prediction rows for a tenant+module from predictions_live.

    Called by reset_demo to ensure a cold-start after reset does not re-load
    stale predictions from Supabase.
    """
    if not _available():
        return
    try:
        _db().table("predictions_live").delete().eq("tenant_id", tenant_id).eq("module", module).execute()
        logger.info("[store] Deleted predictions_live rows for tenant %s module %s", tenant_id, module)
    except Exception as exc:
        logger.warning("[store] delete_tenant_predictions failed: %s", exc)


def update_account_status(
    tenant_id: str,
    account_id: str,
    status: str,
    module: str = "churn",
) -> None:
    """Upsert the CSM status for a single account in predictions_live.

    Uses upsert on the (tenant_id, module, account_id) unique constraint so that
    a status write before predictions are run creates a minimal placeholder row
    rather than silently no-oping.  The placeholder row has an empty prediction_json
    ({}) which is the column's DEFAULT — it will be overwritten on the next predict
    run via save_predictions upsert.
    """
    if not _available():
        return
    try:
        _db().table("predictions_live").upsert(
            {
                "tenant_id": tenant_id,
                "module": module,
                "account_id": account_id,
                "status": status,
                "status_changed_at": _now_iso(),
            },
            on_conflict="tenant_id,module,account_id",
        ).execute()
    except Exception as exc:
        logger.warning("[store] update_account_status failed: %s", exc)


def get_prediction_for_account(
    tenant_id: str,
    module: str,
    account_id: str,
) -> Optional[Dict[str, Any]]:
    """Return the full prediction_json for a single account, or None."""
    if not _available():
        return None
    try:
        resp = (
            _db().table("predictions_live")
            .select("prediction_json, score, confidence_tier, status")
            .eq("tenant_id", tenant_id)
            .eq("module", module)
            .eq("account_id", account_id)
            .not_.is_("score", "null")
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        row = resp.data[0]
        rec = row.get("prediction_json") or {}
        if isinstance(rec, str):
            import json as _json
            rec = _json.loads(rec)
        rec["_account_status"] = row.get("status", "none")
        return rec
    except Exception as exc:
        logger.warning("[store] get_prediction_for_account failed: %s", exc)
        return None


def patch_prediction_json(
    tenant_id: str,
    module: str,
    account_id: str,
    patch: Dict[str, Any],
) -> None:
    """Merge patch dict into the existing prediction_json JSONB for an account.

    Uses Postgres || operator via a raw RPC to avoid a read-modify-write cycle.
    Falls back to a Python-side read-then-write when the RPC is unavailable.
    """
    if not _available():
        return
    try:
        db = _db()
        # Attempt server-side merge using Postgres jsonb concatenation via rpc
        db.rpc(
            "patch_prediction_json",
            {
                "p_tenant_id": tenant_id,
                "p_module": module,
                "p_account_id": account_id,
                "p_patch": patch,
            },
        ).execute()
    except Exception:
        # Fallback: Python-side read-modify-write
        try:
            db = _db()
            resp = (
                db.table("predictions_live")
                .select("prediction_json")
                .eq("tenant_id", tenant_id)
                .eq("module", module)
                .eq("account_id", account_id)
                .limit(1)
                .execute()
            )
            existing: Dict[str, Any] = {}
            if resp.data:
                raw = resp.data[0].get("prediction_json") or {}
                if isinstance(raw, str):
                    import json as _json
                    raw = _json.loads(raw)
                existing = dict(raw)
            existing.update(patch)
            db.table("predictions_live").update(
                {"prediction_json": existing}
            ).eq("tenant_id", tenant_id).eq("module", module).eq("account_id", account_id).execute()
        except Exception as exc2:
            logger.warning("[store] patch_prediction_json fallback failed: %s", exc2)


def get_prediction_by_hs_object_id(
    tenant_id: str,
    module: str,
    hs_object_id: str,
) -> Optional[Dict[str, Any]]:
    """Look up a prediction by HubSpot company object ID stored in prediction_json.

    Uses PostgREST JSONB text-extraction filter. Falls back to None (not to
    account_id) — callers that want account_id fallback must implement it themselves.
    """
    if not _available():
        return None
    try:
        resp = (
            _db().table("predictions_live")
            .select("prediction_json, score, confidence_tier, status")
            .eq("tenant_id", tenant_id)
            .eq("module", module)
            .not_.is_("score", "null")
            .filter("prediction_json->>hs_object_id", "eq", hs_object_id)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        row = resp.data[0]
        rec = row.get("prediction_json") or {}
        if isinstance(rec, str):
            rec = json.loads(rec)
        rec["_account_status"] = row.get("status", "none")
        return rec
    except Exception as exc:
        logger.warning("[store] get_prediction_by_hs_object_id failed: %s", exc)
        return None


def get_accounts_with_task_ids(tenant_id: str, module: str) -> Dict[str, str]:
    """Return {account_id: hs_task_id} for all accounts that have a persisted HubSpot task ID.

    Single query — used by write-back for batched task dedup before the per-account task loop.
    """
    if not _available():
        return {}
    try:
        resp = (
            _db().table("predictions_live")
            .select("account_id, prediction_json")
            .eq("tenant_id", tenant_id)
            .eq("module", module)
            .not_.is_("score", "null")
            .execute()
        )
        result: Dict[str, str] = {}
        for row in (resp.data or []):
            rec = row.get("prediction_json") or {}
            if isinstance(rec, str):
                rec = json.loads(rec)
            task_id = rec.get("hs_task_id")
            if task_id:
                result[row["account_id"]] = str(task_id)
        return result
    except Exception as exc:
        logger.warning("[store] get_accounts_with_task_ids failed: %s", exc)
        return {}


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
            "metadata_json": metadata or {},
            "created_at": _now_iso(),
        }).execute()
    except Exception as exc:
        # Audit log failures must never surface to the user — log and continue.
        logger.warning("[store] log_action failed (action=%s): %s", action, exc)

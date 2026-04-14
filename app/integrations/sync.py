"""Sync engine — pulls data from connectors into normalized storage."""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from app.integrations.models import ConnectorStatus, SyncResult
from app.integrations import registry
from app.storage import repo
from app.storage.repo import DEFAULT_TENANT

logger = logging.getLogger(__name__)


def sync_connector(name: str, tenant_id: str = DEFAULT_TENANT) -> SyncResult:
    """Pull accounts + signals from a single connector and store them.

    Also auto-imports churn outcomes from CRM account fields (idempotent —
    safe to call on every sync without creating duplicates).
    """
    start = time.time()
    result = SyncResult(connector=name)

    connector = registry.get_connector(name)
    if connector is None:
        result.errors.append(f"Connector '{name}' not configured")
        return result

    # Pull accounts
    accounts = []
    try:
        accounts = connector.pull_accounts()
        result.accounts_synced = repo.upsert_accounts(accounts, tenant_id=tenant_id)
    except Exception as exc:
        logger.exception("Failed to pull accounts from %s", name)
        result.errors.append(f"Account pull failed: {exc}")

    # Auto-import churn outcomes from CRM account fields
    if accounts:
        try:
            from app.integrations.outcome_import import import_outcomes_from_accounts
            result.outcomes_imported = import_outcomes_from_accounts(
                accounts, name, tenant_id
            )
        except Exception as exc:
            logger.warning("Outcome import failed for %s: %s", name, exc)

    # Pull signals for synced accounts
    if result.accounts_synced > 0:
        try:
            stored = repo.list_accounts(source=name, limit=10000, tenant_id=tenant_id)
            eids = [a["external_id"] for a in stored]
            signals = connector.pull_signals(eids)
            result.signals_synced = repo.upsert_signals(signals, tenant_id=tenant_id)
        except Exception as exc:
            logger.exception("Failed to pull signals from %s", name)
            result.errors.append(f"Signal pull failed: {exc}")

    result.duration_seconds = round(time.time() - start, 2)

    # Update connector status
    cfg = registry.get_config(name)
    if cfg:
        cfg.extra["last_sync_result"] = {
            "accounts": result.accounts_synced,
            "signals": result.signals_synced,
            "outcomes_imported": result.outcomes_imported,
            "errors": result.errors,
            "duration": result.duration_seconds,
        }

    logger.info(
        "Sync %s: %d accounts, %d signals, %d outcomes, %d errors in %.1fs",
        name,
        result.accounts_synced,
        result.signals_synced,
        result.outcomes_imported,
        len(result.errors),
        result.duration_seconds,
    )
    return result


def sync_all() -> List[SyncResult]:
    """Sync all configured + enabled connectors."""
    results = []
    for info in registry.list_connectors():
        if info.enabled:
            results.append(sync_connector(info.name))
    return results

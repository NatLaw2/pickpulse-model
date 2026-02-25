"""Sync engine — pulls data from connectors into normalized storage."""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from app.integrations.models import ConnectorStatus, SyncResult
from app.integrations import registry
from app.storage import repo

logger = logging.getLogger(__name__)


def sync_connector(name: str) -> SyncResult:
    """Pull accounts + signals from a single connector and store them."""
    start = time.time()
    result = SyncResult(connector=name)

    connector = registry.get_connector(name)
    if connector is None:
        result.errors.append(f"Connector '{name}' not configured")
        return result

    # Pull accounts
    try:
        accounts = connector.pull_accounts()
        result.accounts_synced = repo.upsert_accounts(accounts)
    except Exception as exc:
        logger.exception("Failed to pull accounts from %s", name)
        result.errors.append(f"Account pull failed: {exc}")

    # Pull signals for synced accounts
    if result.accounts_synced > 0:
        try:
            stored = repo.list_accounts(source=name, limit=10000)
            eids = [a["external_id"] for a in stored]
            signals = connector.pull_signals(eids)
            result.signals_synced = repo.upsert_signals(signals)
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
            "errors": result.errors,
            "duration": result.duration_seconds,
        }

    logger.info(
        "Sync %s: %d accounts, %d signals, %d errors in %.1fs",
        name,
        result.accounts_synced,
        result.signals_synced,
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

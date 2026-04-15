"""DemoDataLoader — writes a provider's synthetic dataset into Supabase.

This is an internal module; callers should use DemoModeResolver instead of
importing DemoDataLoader directly.

Architecture
------------
1.  Idempotency guard: if ≥ LOADED_THRESHOLD accounts for this provider+tenant
    already exist, skip and return already_loaded=True.
2.  Generate: instantiate the provider-specific generator and call .generate().
3.  Upsert accounts: batch via Supabase upsert on (tenant_id, source, external_id).
    Collect the returned rows to build external_id → account_uuid mapping.
4.  Upsert signals: join against the UUID map and upsert to account_signals_daily.
5.  Upsert outcomes: join against UUID map, upsert to account_outcomes
    on (tenant_id, account_id) — only churned outcomes are inserted.

All three steps are batched in chunks of BATCH_SIZE to avoid Supabase payload
limits.  Failures in any step are propagated as exceptions to the caller
(DemoModeResolver catches them and records the error).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger("pickpulse.demo.loader")

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

LOADED_THRESHOLD = 200    # accounts for this provider → assume fully loaded
BATCH_SIZE = 400          # rows per Supabase upsert call


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DemoLoadResult:
    already_loaded: bool = False
    account_count: int = 0
    signal_count: int = 0
    outcome_count: int = 0
    skipped: bool = False          # True when demo mode is off or provider is CSV
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunks(lst: list, n: int) -> Iterator[list]:
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _get_generator(provider: str):
    """Return an instantiated dataset generator for the given provider.

    Import is deferred to avoid loading numpy at module import time.
    """
    if provider == "hubspot":
        from .hubspot import HubSpotDemoDataset
        return HubSpotDemoDataset()
    if provider == "salesforce":
        from .salesforce import SalesforceDemoDataset
        return SalesforceDemoDataset()
    raise ValueError(f"No demo dataset generator for provider '{provider}'")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class DemoDataLoader:
    """Loads synthetic demo data into Supabase for a given tenant+provider pair."""

    def ensure_loaded(
        self,
        tenant_id: str,
        provider: str,
        force: bool = False,
    ) -> DemoLoadResult:
        """Ensure synthetic demo data exists for this tenant+provider.

        Parameters
        ----------
        tenant_id:
            Supabase tenant UUID.
        provider:
            'hubspot' or 'salesforce'.
        force:
            If True, skip the idempotency guard and reload even if data exists.
            Use only for explicit resets; normal demo flow should leave this False.

        Returns
        -------
        DemoLoadResult
            Contains counts of accounts/signals/outcomes written, and whether the
            load was skipped because data was already present.
        """
        from ..storage import repo
        from ..storage.db import get_client

        # ---- Idempotency check -------------------------------------------
        if not force:
            existing = repo.account_count(source=provider, tenant_id=tenant_id)
            if existing >= LOADED_THRESHOLD:
                logger.info(
                    "[demo_loader] %s demo data already loaded for tenant %s… (%d accounts) — skipping",
                    provider, tenant_id[:8], existing,
                )
                return DemoLoadResult(already_loaded=True, account_count=existing)

        logger.info(
            "[demo_loader] Loading %s synthetic demo dataset for tenant %s…",
            provider, tenant_id[:8],
        )

        # ---- Generate dataset --------------------------------------------
        generator = _get_generator(provider)
        dataset = generator.generate()

        accounts_data: List[Dict[str, Any]] = dataset["accounts"]
        signals_data:  List[Dict[str, Any]] = dataset["signals"]
        outcomes_data: List[Dict[str, Any]] = dataset["outcomes"]

        logger.info(
            "[demo_loader] Generated: %d accounts, %d signal rows, %d outcomes",
            len(accounts_data), len(signals_data), len(outcomes_data),
        )

        sb = get_client()

        # ---- Step 1: Upsert accounts, collect UUID map -------------------
        account_id_map: Dict[str, str] = {}  # external_id → account UUID
        accounts_loaded = 0

        for batch in _chunks(accounts_data, BATCH_SIZE):
            rows = [
                {
                    "tenant_id":  tenant_id,
                    "source":     provider,
                    "external_id": a["external_id"],
                    "name":       a["name"],
                    "domain":     a.get("domain"),
                    "arr":        a.get("arr"),
                    "status":     a.get("status", "active"),
                    "auto_renew": a.get("auto_renew", True),
                    "metadata":   a.get("metadata", {}),
                }
                for a in batch
            ]
            res = sb.table("accounts").upsert(
                rows,
                on_conflict="tenant_id,source,external_id",
            ).execute()
            for row in res.data or []:
                account_id_map[row["external_id"]] = row["id"]
                accounts_loaded += 1

        logger.info("[demo_loader] Accounts upserted: %d (map size: %d)", accounts_loaded, len(account_id_map))

        if not account_id_map:
            # If Supabase returned no data (e.g., no RETURNING), do a fallback fetch.
            logger.warning("[demo_loader] Upsert returned no rows — fetching UUIDs via SELECT")
            all_ext_ids = [a["external_id"] for a in accounts_data]
            for ext_batch in _chunks(all_ext_ids, BATCH_SIZE):
                res = sb.table("accounts") \
                    .select("id,external_id") \
                    .eq("tenant_id", tenant_id) \
                    .eq("source", provider) \
                    .in_("external_id", ext_batch) \
                    .execute()
                for row in res.data or []:
                    account_id_map[row["external_id"]] = row["id"]
            logger.info("[demo_loader] UUID map rebuilt via SELECT: %d entries", len(account_id_map))

        # ---- Step 2: Upsert signals --------------------------------------
        signal_rows: List[Dict[str, Any]] = []
        for sig in signals_data:
            uuid = account_id_map.get(sig["external_id"])
            if not uuid:
                continue
            signal_rows.append({
                "tenant_id":    tenant_id,
                "account_id":   uuid,
                "signal_date":  sig["signal_date"],
                "signal_key":   sig["signal_key"],
                "signal_value": sig.get("signal_value"),
                "signal_text":  sig.get("signal_text"),
            })

        signals_loaded = 0
        for batch in _chunks(signal_rows, BATCH_SIZE):
            sb.table("account_signals_daily").upsert(
                batch,
                on_conflict="tenant_id,account_id,signal_date,signal_key",
            ).execute()
            signals_loaded += len(batch)

        logger.info("[demo_loader] Signal rows upserted: %d", signals_loaded)

        # ---- Step 3: Upsert outcomes -------------------------------------
        # account_outcomes has a UNIQUE(tenant_id, account_id) constraint,
        # so we upsert with on_conflict to remain idempotent.
        outcome_rows: List[Dict[str, Any]] = []
        now_ts = datetime.now(timezone.utc).isoformat()
        for out in outcomes_data:
            uuid = account_id_map.get(out["external_id"])
            if not uuid:
                continue
            outcome_rows.append({
                "tenant_id":     tenant_id,
                "account_id":    uuid,
                "outcome_type":  out["outcome_type"],
                "effective_date": out["effective_date"],
                "source":        "system",
                "notes":         "Synthetic demo dataset",
                "recorded_at":   out.get("recorded_at", now_ts),
            })

        outcomes_loaded = 0
        for batch in _chunks(outcome_rows, BATCH_SIZE):
            try:
                sb.table("account_outcomes").upsert(
                    batch,
                    on_conflict="tenant_id,account_id",
                ).execute()
                outcomes_loaded += len(batch)
            except Exception as exc:
                # Fallback: if the unique constraint doesn't exist yet, insert
                # only rows for accounts that have no existing outcome.
                logger.warning(
                    "[demo_loader] outcomes upsert failed (%s) — falling back to filtered insert",
                    exc,
                )
                ext_ids_in_batch = [o["account_id"] for o in batch]
                existing_res = sb.table("account_outcomes") \
                    .select("account_id") \
                    .eq("tenant_id", tenant_id) \
                    .in_("account_id", ext_ids_in_batch) \
                    .execute()
                existing_acct_ids = {r["account_id"] for r in (existing_res.data or [])}
                new_rows = [o for o in batch if o["account_id"] not in existing_acct_ids]
                if new_rows:
                    sb.table("account_outcomes").insert(new_rows).execute()
                    outcomes_loaded += len(new_rows)

        logger.info("[demo_loader] Outcomes upserted: %d", outcomes_loaded)

        return DemoLoadResult(
            account_count=accounts_loaded or len(accounts_data),
            signal_count=signals_loaded,
            outcome_count=outcomes_loaded,
        )

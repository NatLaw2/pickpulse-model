"""DemoModeResolver — central demo/live mode arbiter.

This is THE single authoritative place where the demo/live mode decision is
made for any provider.  All other code that previously scattered
``if DEMO_MODE: auto_seed_if_needed(...)`` calls should instead call
``demo_resolver.ensure_demo_data(tenant_id, provider)``.

Design
------
*  Provider-aware: HubSpot and Salesforce each get their own synthetic dataset.
   CSV always uses the real pipeline (no synthetic path).
*  Demo mode is a binary flag set once at startup from the DEMO_MODE env var.
   No per-request resolution needed.
*  Idempotent: ensure_demo_data() checks whether data is already loaded before
   writing anything, so it is safe to call on every sync / train / score request.
*  Live mode is completely untouched: should_use_synthetic() returns False, and
   ensure_demo_data() returns DemoLoadResult(skipped=True) immediately.

Provider resolution table
--------------------------
+------------------+------------+-------------------------------------+
| provider         | demo_mode  | behaviour                           |
+==================+============+=====================================+
| hubspot          | True       | use synthetic HubSpot dataset       |
| hubspot          | False      | real HubSpot ingestion (unchanged)  |
| salesforce       | True       | use synthetic Salesforce dataset    |
| salesforce       | False      | real Salesforce ingestion           |
| csv / any other  | True/False | always real pipeline (unchanged)    |
+------------------+------------+-------------------------------------+
"""
from __future__ import annotations

import logging
from typing import Optional

from ._loader import DemoDataLoader, DemoLoadResult

logger = logging.getLogger("pickpulse.demo.resolver")

# Providers that have a synthetic demo dataset.
# CSV is deliberately excluded — it remains the baseline real pipeline.
_SYNTHETIC_PROVIDERS = frozenset({"hubspot", "salesforce"})


class DemoModeResolver:
    """Central arbiter for demo vs. live data source selection.

    Instantiate once at application startup::

        demo_resolver = DemoModeResolver(demo_mode=DEMO_MODE)

    Then use throughout the application::

        if demo_resolver.should_use_synthetic(provider):
            result = demo_resolver.ensure_demo_data(tenant_id, provider)
    """

    def __init__(self, demo_mode: bool) -> None:
        self._demo_mode = demo_mode
        self._loader = DemoDataLoader()
        if demo_mode:
            logger.info(
                "[demo_resolver] Initialised in DEMO MODE — HubSpot and Salesforce "
                "will use fixed synthetic datasets after connection."
            )
        else:
            logger.info(
                "[demo_resolver] Initialised in LIVE MODE — all CRM providers use "
                "real ingestion pipelines."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def demo_mode(self) -> bool:
        """True when the application is running in demo mode."""
        return self._demo_mode

    def should_use_synthetic(self, provider: str) -> bool:
        """Return True only when this provider+mode combination uses synthetic data.

        This is the primary gate used in trigger_sync to decide whether to
        bypass the real CRM pull.

        Parameters
        ----------
        provider:
            The CRM provider name, e.g. ``'hubspot'``, ``'salesforce'``, ``'csv'``.

        Returns
        -------
        bool
            True → skip live CRM data, use synthetic dataset.
            False → use real CRM pipeline (live mode OR CSV source).
        """
        return self._demo_mode and provider in _SYNTHETIC_PROVIDERS

    def ensure_demo_data(
        self,
        tenant_id: str,
        provider: str,
        force_reload: bool = False,
    ) -> DemoLoadResult:
        """Ensure the synthetic demo dataset is loaded for this tenant+provider.

        Safe to call multiple times — the loader checks whether accounts are
        already present and skips if so (idempotent).

        Parameters
        ----------
        tenant_id:
            Supabase tenant UUID (from JWT ``sub`` claim).
        provider:
            CRM provider name.  Non-CRM providers (``'csv'``) are silently skipped.
        force_reload:
            When True, bypasses the idempotency guard and reloads the full
            dataset.  Use only from an explicit admin reset flow.

        Returns
        -------
        DemoLoadResult
            ``skipped=True`` when demo mode is off or provider is not synthetic.
            ``already_loaded=True`` when data was already present.
            Otherwise, populated with counts of rows written.
        """
        if not self.should_use_synthetic(provider):
            return DemoLoadResult(skipped=True)

        try:
            result = self._loader.ensure_loaded(
                tenant_id=tenant_id,
                provider=provider,
                force=force_reload,
            )
        except Exception as exc:
            logger.exception(
                "[demo_resolver] Failed to load %s demo data for tenant %s: %s",
                provider, tenant_id[:8], exc,
            )
            return DemoLoadResult(errors=[str(exc)])

        if result.already_loaded:
            logger.debug(
                "[demo_resolver] %s demo data already present for tenant %s — no-op",
                provider, tenant_id[:8],
            )
        else:
            logger.info(
                "[demo_resolver] %s demo data loaded: %d accounts, %d signals, %d outcomes",
                provider, result.account_count, result.signal_count, result.outcome_count,
            )

        return result

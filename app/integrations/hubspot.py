"""HubSpot CRM connector — pulls companies, contacts, and deals."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from app.integrations.base import BaseConnector
from app.integrations.models import Account, AccountSignal, ConnectorConfig

logger = logging.getLogger(__name__)

API_BASE = "https://api.hubapi.com"


class HubSpotConnector(BaseConnector):

    @property
    def name(self) -> str:
        return "hubspot"

    @property
    def display_name(self) -> str:
        return "HubSpot CRM"

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        try:
            r = requests.get(
                f"{API_BASE}/crm/v3/objects/companies",
                headers=self._headers(),
                params={"limit": 1},
                timeout=10,
            )
            return r.status_code == 200
        except Exception as exc:
            logger.warning("HubSpot connection test failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Pull accounts (companies)
    # ------------------------------------------------------------------

    def pull_accounts(self) -> List[Account]:
        properties = [
            "name", "domain", "industry", "numberofemployees",
            "annualrevenue", "createdate", "hs_object_id",
        ]
        # Also include custom properties from config
        extra_props = self.config.extra.get("company_properties", [])
        properties.extend(extra_props)

        accounts: List[Account] = []
        after: str | None = None

        while True:
            params: Dict[str, Any] = {
                "limit": 100,
                "properties": ",".join(properties),
            }
            if after:
                params["after"] = after

            r = requests.get(
                f"{API_BASE}/crm/v3/objects/companies",
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()

            for company in data.get("results", []):
                props = company.get("properties", {})
                accounts.append(self._company_to_account(company["id"], props))

            paging = data.get("paging", {}).get("next")
            if paging and paging.get("after"):
                after = paging["after"]
            else:
                break

        logger.info("HubSpot: pulled %d companies", len(accounts))
        return accounts

    def _company_to_account(self, hs_id: str, props: Dict[str, Any]) -> Account:
        revenue = props.get("annualrevenue")
        arr = float(revenue) if revenue else None

        employees = props.get("numberofemployees")
        size = None
        if employees:
            try:
                n = int(employees)
                if n < 50:
                    size = "small"
                elif n < 500:
                    size = "mid-market"
                else:
                    size = "enterprise"
            except (ValueError, TypeError):
                size = str(employees)

        created = props.get("createdate")
        created_dt = None
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return Account(
            external_id=hs_id,
            source="hubspot",
            name=props.get("name", ""),
            email=props.get("domain", ""),
            plan=None,
            arr=arr,
            industry=props.get("industry"),
            company_size=size,
            created_at=created_dt,
            raw_data=props,
        )

    # ------------------------------------------------------------------
    # Pull signals (engagement data from deals / contacts)
    # ------------------------------------------------------------------

    def pull_signals(self, external_ids: List[str]) -> List[AccountSignal]:
        """Pull engagement signals from HubSpot engagements API.

        For the v1, we pull recent deal activity and contact engagement
        as a proxy for usage signals.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        signals: List[AccountSignal] = []

        for eid in external_ids:
            try:
                signal = self._pull_company_signal(eid, today)
                if signal:
                    signals.append(signal)
            except Exception as exc:
                logger.warning("HubSpot signal pull failed for %s: %s", eid, exc)

        logger.info("HubSpot: pulled %d signals", len(signals))
        return signals

    def _pull_company_signal(self, company_id: str, date: str) -> AccountSignal | None:
        # Get associated contacts count as a proxy for seats
        r = requests.get(
            f"{API_BASE}/crm/v3/objects/companies/{company_id}/associations/contacts",
            headers=self._headers(),
            timeout=15,
        )
        contacts_count = 0
        if r.status_code == 200:
            contacts_count = len(r.json().get("results", []))

        # Get recent deals for renewal status signals
        r = requests.get(
            f"{API_BASE}/crm/v3/objects/companies/{company_id}/associations/deals",
            headers=self._headers(),
            timeout=15,
        )
        deal_count = 0
        if r.status_code == 200:
            deal_count = len(r.json().get("results", []))

        return AccountSignal(
            external_id=company_id,
            signal_date=date,
            seats=contacts_count if contacts_count > 0 else None,
            support_tickets=deal_count,
            extra={"contacts": contacts_count, "deals": deal_count},
        )

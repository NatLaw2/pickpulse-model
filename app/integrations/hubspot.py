"""HubSpot CRM connector — pulls companies, contacts, and deals."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from app.integrations.base import BaseConnector
from app.integrations.models import Account, AccountSignal, ConnectorConfig

logger = logging.getLogger(__name__)

API_BASE = "https://api.hubapi.com"

# Custom property group and properties created in the tenant's HubSpot portal
_PICKPULSE_PROPERTY_GROUP = "pickpulse_churn"
_CHURN_PROPERTIES = [
    {
        "name": "pickpulse_churn_risk_pct",
        "label": "Churn Risk %",
        "type": "number",
        "fieldType": "number",
        "description": "PickPulse churn risk score (0–100)",
    },
    {
        "name": "pickpulse_tier",
        "label": "PickPulse Risk Tier",
        "type": "string",
        "fieldType": "text",
        "description": "PickPulse confidence tier: High / Medium / Low",
    },
    {
        "name": "pickpulse_arr_at_risk",
        "label": "ARR at Risk",
        "type": "number",
        "fieldType": "number",
        "description": "ARR weighted by churn probability (PickPulse)",
    },
    {
        "name": "pickpulse_recommended_action",
        "label": "Recommended Action",
        "type": "string",
        "fieldType": "text",
        "description": "PickPulse recommended CSM action",
    },
    {
        "name": "pickpulse_scored_at",
        "label": "PickPulse Last Scored",
        "type": "datetime",
        "fieldType": "date",
        "description": "Timestamp of last PickPulse scoring run",
    },
]

# Task creation thresholds
TASK_RISK_THRESHOLD = 70       # churn_risk_pct must be >= this
TASK_RENEWAL_WINDOW_DAYS = 90  # days_until_renewal must be <= this (or unknown)


class HubSpotConnector(BaseConnector):

    @property
    def name(self) -> str:
        return "hubspot"

    @property
    def display_name(self) -> str:
        return "HubSpot CRM"

    @property
    def auth_method(self) -> str:
        return "oauth"

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
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

    # ------------------------------------------------------------------
    # Write-back helpers
    # ------------------------------------------------------------------

    def _refresh_token_if_needed(self) -> None:
        """Proactively refresh the access token if it may be near expiry.

        HubSpot tokens expire after 6 hours (21,600 s). We refresh when the
        stored token is absent or when refresh_token is available and the
        token is older than 5.5 hours.  On failure we log and continue —
        the write call will fail with 401 and be retried on the next run.
        """
        from app.integrations.oauth import refresh_access_token

        refresh_token = self.config.extra.get("refresh_token")
        token_acquired_at = self.config.extra.get("token_acquired_at", 0)
        try:
            token_acquired_at = float(token_acquired_at)
        except (TypeError, ValueError):
            token_acquired_at = 0.0

        if not refresh_token:
            return

        age_s = time.time() - token_acquired_at
        if age_s < 19_800:  # 5.5 hours — still fresh
            return

        try:
            result = refresh_access_token("hubspot", refresh_token)
            self.config.extra["access_token"] = result["access_token"]
            self.config.extra["token_acquired_at"] = time.time()
            logger.info("[hubspot] Access token refreshed successfully")
        except Exception as exc:
            logger.warning("[hubspot] Token refresh failed: %s", exc)

    def ensure_churn_properties(self) -> None:
        """Idempotently create the PickPulse property group and custom properties.

        Safe to call before every write-back run — HubSpot returns 409 for
        existing resources, which we treat as success.
        """
        self._refresh_token_if_needed()
        headers = self._headers()

        # 1. Create property group
        try:
            r = requests.post(
                f"{API_BASE}/crm/v3/properties/companies/groups",
                headers=headers,
                json={"name": _PICKPULSE_PROPERTY_GROUP, "label": "PickPulse Churn"},
                timeout=15,
            )
            if r.status_code not in (200, 201, 409):
                logger.warning("[hubspot] Property group creation returned %d: %s", r.status_code, r.text[:200])
        except Exception as exc:
            logger.warning("[hubspot] ensure_churn_properties (group) failed: %s", exc)

        # 2. Create each property
        for prop in _CHURN_PROPERTIES:
            try:
                payload = {
                    "name": prop["name"],
                    "label": prop["label"],
                    "type": prop["type"],
                    "fieldType": prop["fieldType"],
                    "description": prop.get("description", ""),
                    "groupName": _PICKPULSE_PROPERTY_GROUP,
                }
                r = requests.post(
                    f"{API_BASE}/crm/v3/properties/companies",
                    headers=headers,
                    json=payload,
                    timeout=15,
                )
                if r.status_code not in (200, 201, 409):
                    logger.warning("[hubspot] Property create %s returned %d", prop["name"], r.status_code)
            except Exception as exc:
                logger.warning("[hubspot] ensure_churn_properties (%s) failed: %s", prop["name"], exc)

    def push_churn_scores(self, scores: List[Dict[str, Any]]) -> int:
        """Batch-update company properties for a list of scored accounts.

        Each score dict must have 'account_id' (== hs_object_id) and optionally:
          churn_risk_pct, tier, arr_at_risk, recommended_action, predicted_at.

        Returns the number of companies successfully updated.
        """
        self._refresh_token_if_needed()

        # Filter to records that have a usable HubSpot ID
        rows = [s for s in scores if s.get("account_id")]
        if not rows:
            return 0

        updated = 0
        batch_size = 100

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            inputs = []
            for s in batch:
                props: Dict[str, str] = {}
                if s.get("churn_risk_pct") is not None:
                    props["pickpulse_churn_risk_pct"] = str(round(float(s["churn_risk_pct"]), 1))
                if s.get("tier"):
                    props["pickpulse_tier"] = str(s["tier"])
                if s.get("arr_at_risk") is not None:
                    props["pickpulse_arr_at_risk"] = str(round(float(s["arr_at_risk"]), 2))
                if s.get("recommended_action"):
                    props["pickpulse_recommended_action"] = str(s["recommended_action"])
                props["pickpulse_scored_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                inputs.append({"id": str(s["account_id"]), "properties": props})

            try:
                r = requests.post(
                    f"{API_BASE}/crm/v3/objects/companies/batch/update",
                    headers=self._headers(),
                    json={"inputs": inputs},
                    timeout=30,
                )
                if r.status_code in (200, 207):
                    resp_data = r.json()
                    n_errors = resp_data.get("numErrors", 0) or 0
                    successful = len(batch) - n_errors
                    updated += max(0, successful)
                    if n_errors:
                        logger.warning(
                            "[hubspot] Batch %d had %d/%d errors: %s",
                            i // batch_size + 1, n_errors, len(batch),
                            str(resp_data.get("errors", []))[:300],
                        )
                    else:
                        logger.info("[hubspot] Batch updated %d companies (batch %d)", len(batch), i // batch_size + 1)
                else:
                    logger.warning("[hubspot] Batch update returned %d: %s", r.status_code, r.text[:300])
            except Exception as exc:
                logger.warning("[hubspot] push_churn_scores batch %d failed: %s", i // batch_size + 1, exc)

            if i + batch_size < len(rows):
                time.sleep(0.15)  # stay well within HubSpot rate limits

        return updated

    def create_task(
        self,
        account: Dict[str, Any],
        subject: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Optional[str]:
        """Create a HubSpot task for a high-risk account. Returns task_id or None."""
        self._refresh_token_if_needed()

        account_id = str(account.get("account_id", ""))
        account_name = account.get("account_id", "account")
        churn_risk_pct = float(account.get("churn_risk_pct") or 0)
        days_renewal = account.get("days_until_renewal")
        recommended_action = account.get("recommended_action", "Review")

        task_subject = subject or f"[PickPulse] {recommended_action} — {account_name}"
        renewal_note = f" | Renewal in {int(float(days_renewal))} days" if days_renewal is not None else ""
        task_body = body or (
            f"PickPulse churn risk: {churn_risk_pct:.0f}%{renewal_note}. "
            f"Recommended: {recommended_action}. Review account health and engage proactively."
        )

        try:
            r = requests.post(
                f"{API_BASE}/crm/v3/objects/tasks",
                headers=self._headers(),
                json={
                    "properties": {
                        "hs_task_subject": task_subject,
                        "hs_task_body": task_body,
                        "hs_task_status": "NOT_STARTED",
                        "hs_task_priority": "HIGH" if churn_risk_pct >= 80 else "MEDIUM",
                        "hs_task_type": "TODO",
                    }
                },
                timeout=15,
            )
            r.raise_for_status()
            task_id = r.json().get("id")
            logger.info("[hubspot] Created task %s for account %s", task_id, account_id)

            # Associate task to company
            if task_id and account_id:
                self._associate_task_to_company(task_id, account_id)

            return task_id
        except Exception as exc:
            logger.warning("[hubspot] create_task failed for %s: %s", account_id, exc)
            return None

    def _associate_task_to_company(self, task_id: str, company_id: str) -> None:
        """Associate a task to a HubSpot company via the associations API.

        Association type label must be uppercase TASK_TO_COMPANY as required by
        HubSpot CRM v3 associations API.
        """
        try:
            r = requests.put(
                f"{API_BASE}/crm/v3/objects/tasks/{task_id}/associations/companies/{company_id}/TASK_TO_COMPANY",
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code not in (200, 201):
                logger.warning(
                    "[hubspot] task-company association returned %d for task=%s company=%s: %s",
                    r.status_code, task_id, company_id, r.text[:200],
                )
        except Exception as exc:
            logger.warning("[hubspot] _associate_task_to_company failed: %s", exc)

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

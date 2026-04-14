"""Salesforce CRM connector — v1 scope: connect, ingest, score, view.

v1 implements:
  - test_connection()
  - pull_accounts()   — Account object, explicit field list, SOQL pagination
  - pull_signals()    — contact count, open opportunity count/value, last activity

Deferred to v2:
  - Score writeback to Salesforce custom fields
  - Task creation for high-risk accounts
  - Custom field provisioning via Metadata API
  - Sandbox vs production branching
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from app.integrations.base import BaseConnector
from app.integrations.models import Account, AccountSignal, ConnectorConfig
from app.integrations.normalization import safe_float, safe_int, clean_string, days_since

logger = logging.getLogger(__name__)

# Salesforce REST API version — bump here to upgrade all calls
_SF_API_VERSION = "v57.0"

# SOQL account fields pulled in v1 — conservative, explicit set
_ACCOUNT_FIELDS = [
    "Id",
    "Name",
    "Website",
    "AnnualRevenue",
    "Industry",
    "NumberOfEmployees",
    "CreatedDate",
    "LastActivityDate",
    "Type",  # "Former Customer" → churn indicator for outcome auto-import
]

# Batch size for SOQL IN clauses — stays well under the 20k char SOQL limit
_SIGNAL_BATCH_SIZE = 200

# Max accounts pulled in v1 — intentional ceiling; increase in v2
_ACCOUNT_LIMIT = 2000


class SalesforceConnector(BaseConnector):

    @property
    def name(self) -> str:
        return "salesforce"

    @property
    def display_name(self) -> str:
        return "Salesforce CRM"

    @property
    def auth_method(self) -> str:
        return "oauth"

    # ------------------------------------------------------------------
    # Instance URL — critical Salesforce-specific requirement
    # ------------------------------------------------------------------

    @property
    def _instance_url(self) -> str:
        """Return the org-specific Salesforce API base URL.

        Salesforce does not have a fixed API host. The correct URL is returned
        during the OAuth token exchange as `instance_url` and stored in
        integration_tokens. It is loaded into config.extra by the connector
        registry before instantiation.

        If missing (e.g. re-used token without re-connect), raises RuntimeError
        so the failure is explicit rather than silently hitting the wrong host.
        """
        url = self.config.extra.get("instance_url", "").rstrip("/")
        if not url:
            raise RuntimeError(
                "Salesforce instance_url is not set. "
                "Disconnect and reconnect the Salesforce integration to refresh it."
            )
        return url

    def _api_base(self) -> str:
        return f"{self._instance_url}/services/data/{_SF_API_VERSION}"

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Retry-aware HTTP wrapper (mirrors HubSpot pattern)
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> requests.Response:
        """HTTP request with exponential back-off and 429/5xx retry handling.

        Retries on: 429 (rate limit), 500, 502, 503, 504.
        Raises immediately on 401, 403, 404, and other 4xx.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                r = requests.request(
                    method, url,
                    headers=self._headers(),
                    params=params,
                    json=json,
                    timeout=timeout,
                )

                if r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", 2 ** attempt))
                    logger.warning(
                        "[salesforce] Rate limited — waiting %ds (attempt %d)",
                        retry_after, attempt + 1,
                    )
                    time.sleep(min(retry_after, 30))
                    continue

                if r.status_code in (500, 502, 503, 504):
                    wait = 2 ** attempt
                    logger.warning("[salesforce] %d error, retrying in %ds", r.status_code, wait)
                    time.sleep(wait)
                    last_exc = requests.HTTPError(response=r)
                    continue

                return r

            except (requests.Timeout, requests.ConnectionError) as exc:
                wait = 2 ** attempt
                logger.warning("[salesforce] Network error (%s), retrying in %ds", exc, wait)
                time.sleep(wait)
                last_exc = exc

        raise last_exc or requests.RequestException("Max retries exceeded")

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        """Verify that the access token is valid and the org is reachable."""
        try:
            r = self._request(
                "GET",
                f"{self._api_base()}/sobjects/Account",
                timeout=10,
            )
            return r.status_code == 200
        except Exception as exc:
            logger.warning("[salesforce] Connection test failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Pull accounts (SOQL, paginated)
    # ------------------------------------------------------------------

    def pull_accounts(self) -> List[Account]:
        """Pull Salesforce Account records via SOQL.

        Uses a conservative, explicit field list. Paginates via nextRecordsUrl
        up to _ACCOUNT_LIMIT rows.
        """
        fields = ", ".join(_ACCOUNT_FIELDS)
        soql = (
            f"SELECT {fields} FROM Account "
            f"WHERE IsDeleted = false "
            f"ORDER BY CreatedDate DESC "
            f"LIMIT {_ACCOUNT_LIMIT}"
        )

        accounts: List[Account] = []
        # First request: POST to query endpoint with SOQL
        query_url = f"{self._api_base()}/query"
        params: Optional[Dict[str, Any]] = {"q": soql}
        next_url: Optional[str] = None

        while True:
            if next_url:
                # Subsequent pages — nextRecordsUrl is a path, prepend instance_url
                r = self._request(
                    "GET",
                    f"{self._instance_url}{next_url}",
                    timeout=30,
                )
            else:
                r = self._request("GET", query_url, params=params, timeout=30)

            r.raise_for_status()
            data = r.json()

            for record in data.get("records", []):
                try:
                    accounts.append(self._record_to_account(record))
                except Exception as exc:
                    logger.warning(
                        "[salesforce] Skipping account %s: %s",
                        record.get("Id"), exc,
                    )

            if data.get("done", True) or not data.get("nextRecordsUrl"):
                break
            next_url = data["nextRecordsUrl"]

        logger.info("[salesforce] Pulled %d accounts", len(accounts))
        return accounts

    def _record_to_account(self, record: Dict[str, Any]) -> Account:
        """Normalize a raw Salesforce Account record to PickPulse Account model."""
        sf_id = record["Id"]

        # Parse CreatedDate (ISO 8601 with timezone)
        created_dt: Optional[datetime] = None
        raw_created = record.get("CreatedDate")
        if raw_created:
            try:
                # Salesforce format: "2023-01-15T12:00:00.000+0000"
                created_dt = datetime.fromisoformat(
                    raw_created.replace("+0000", "+00:00").replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        return Account(
            external_id=sf_id,
            source="salesforce",
            name=clean_string(record.get("Name", "")) or sf_id,
            email=clean_string(record.get("Website")),  # Website as domain proxy
            plan=None,  # No standard plan field in Salesforce Account
            arr=safe_float(record.get("AnnualRevenue")),
            industry=clean_string(record.get("Industry")),
            company_size=self._bucket_employees(record.get("NumberOfEmployees")),
            created_at=created_dt,
            raw_data=record,
        )

    @staticmethod
    def _bucket_employees(value: Any) -> Optional[str]:
        """Convert raw employee count to PickPulse size bucket."""
        n = safe_int(value)
        if n is None:
            return None
        if n < 50:
            return "1-50"
        if n < 200:
            return "51-200"
        if n <= 1000:
            return "201-1000"
        return "1001+"

    # ------------------------------------------------------------------
    # Pull signals (batch SOQL aggregates)
    # ------------------------------------------------------------------

    def pull_signals(self, external_ids: List[str]) -> List[AccountSignal]:
        """Pull account-level engagement signals via batch SOQL aggregates.

        Signals collected per account:
          - contact_count             → seats proxy (team breadth)
          - opp_count / opp_value     → open opportunity pipeline
          - case_count                → open support cases → support_tickets
          - days_since_last_activity  → from LastActivityDate → days_since_last_login
          - days_until_renewal        → from nearest open Opportunity CloseDate

        All queries are batched in groups of _SIGNAL_BATCH_SIZE to stay well
        under the 20k character SOQL limit.
        """
        if not external_ids:
            return []

        today_dt = datetime.now(timezone.utc)
        today = today_dt.strftime("%Y-%m-%d")

        # Batch SOQL queries — all return {account_id: value}
        contact_counts = self._query_contact_counts(external_ids)
        opp_data = self._query_opportunity_data(external_ids)
        case_counts = self._query_case_counts(external_ids)
        activity_dates = self._query_activity_dates(external_ids)
        renewal_dates = self._query_renewal_dates(external_ids)

        signals: List[AccountSignal] = []
        for eid in external_ids:
            try:
                contact_count = contact_counts.get(eid, 0)
                opp_count, opp_value = opp_data.get(eid, (0, None))
                case_count = case_counts.get(eid, None)

                # days_since_last_login proxy from LastActivityDate
                days_inactive: Optional[int] = None
                last_act = activity_dates.get(eid)
                if last_act:
                    days_inactive = days_since(last_act)

                # days_until_renewal from nearest open Opportunity CloseDate
                days_renewal: Optional[float] = None
                renewal_date = renewal_dates.get(eid)
                if renewal_date:
                    try:
                        from datetime import date as date_cls
                        rd = date_cls.fromisoformat(renewal_date[:10])
                        days_renewal = (rd - today_dt.date()).days
                    except (ValueError, TypeError):
                        pass

                signals.append(AccountSignal(
                    external_id=eid,
                    signal_date=today,
                    seats=contact_count if contact_count > 0 else None,
                    support_tickets=case_count,
                    days_since_last_login=days_inactive,
                    days_until_renewal=days_renewal,
                    extra={
                        "contact_count": contact_count,
                        "opp_count": opp_count,
                        "opp_value": opp_value,
                        "source": "salesforce",
                    },
                ))
            except Exception as exc:
                logger.warning("[salesforce] Signal build failed for %s: %s", eid, exc)

        logger.info("[salesforce] Built %d signals", len(signals))
        return signals

    def _query_contact_counts(self, account_ids: List[str]) -> Dict[str, int]:
        """Return {account_id: contact_count} for all given account IDs."""
        counts: Dict[str, int] = {}
        for batch in self._chunks(account_ids, _SIGNAL_BATCH_SIZE):
            id_list = ", ".join(f"'{aid}'" for aid in batch)
            soql = (
                f"SELECT AccountId, COUNT(Id) "
                f"FROM Contact "
                f"WHERE AccountId IN ({id_list}) "
                f"GROUP BY AccountId"
            )
            try:
                r = self._request(
                    "GET",
                    f"{self._api_base()}/query",
                    params={"q": soql},
                    timeout=30,
                )
                if r.status_code == 200:
                    for rec in r.json().get("records", []):
                        counts[rec["AccountId"]] = rec.get("expr0", 0)
                else:
                    logger.warning("[salesforce] Contact count query returned %d", r.status_code)
            except Exception as exc:
                logger.warning("[salesforce] Contact count batch failed: %s", exc)
        return counts

    def _query_opportunity_data(
        self, account_ids: List[str]
    ) -> Dict[str, tuple]:
        """Return {account_id: (opp_count, opp_value)} for open Opportunities."""
        opp_map: Dict[str, tuple] = {}
        for batch in self._chunks(account_ids, _SIGNAL_BATCH_SIZE):
            id_list = ", ".join(f"'{aid}'" for aid in batch)
            soql = (
                f"SELECT AccountId, COUNT(Id), SUM(Amount) "
                f"FROM Opportunity "
                f"WHERE AccountId IN ({id_list}) "
                f"AND IsClosed = false "
                f"AND IsDeleted = false "
                f"GROUP BY AccountId"
            )
            try:
                r = self._request(
                    "GET",
                    f"{self._api_base()}/query",
                    params={"q": soql},
                    timeout=30,
                )
                if r.status_code == 200:
                    for rec in r.json().get("records", []):
                        opp_map[rec["AccountId"]] = (
                            rec.get("expr0", 0),
                            safe_float(rec.get("expr1")),
                        )
                else:
                    logger.warning("[salesforce] Opportunity query returned %d", r.status_code)
            except Exception as exc:
                logger.warning("[salesforce] Opportunity batch failed: %s", exc)
        return opp_map

    def _query_case_counts(self, account_ids: List[str]) -> Dict[str, int]:
        """Return {account_id: open_case_count} for all given account IDs."""
        counts: Dict[str, int] = {}
        for batch in self._chunks(account_ids, _SIGNAL_BATCH_SIZE):
            id_list = ", ".join(f"'{aid}'" for aid in batch)
            soql = (
                f"SELECT AccountId, COUNT(Id) "
                f"FROM Case "
                f"WHERE AccountId IN ({id_list}) "
                f"AND IsClosed = false "
                f"GROUP BY AccountId"
            )
            try:
                r = self._request(
                    "GET",
                    f"{self._api_base()}/query",
                    params={"q": soql},
                    timeout=30,
                )
                if r.status_code == 200:
                    for rec in r.json().get("records", []):
                        counts[rec["AccountId"]] = rec.get("expr0", 0)
                else:
                    logger.warning("[salesforce] Case count query returned %d", r.status_code)
            except Exception as exc:
                logger.warning("[salesforce] Case count batch failed: %s", exc)
        return counts

    def _query_activity_dates(self, account_ids: List[str]) -> Dict[str, Optional[str]]:
        """Return {account_id: LastActivityDate ISO string} for given account IDs."""
        dates: Dict[str, Optional[str]] = {}
        for batch in self._chunks(account_ids, _SIGNAL_BATCH_SIZE):
            id_list = ", ".join(f"'{aid}'" for aid in batch)
            soql = (
                f"SELECT Id, LastActivityDate "
                f"FROM Account "
                f"WHERE Id IN ({id_list})"
            )
            try:
                r = self._request(
                    "GET",
                    f"{self._api_base()}/query",
                    params={"q": soql},
                    timeout=30,
                )
                if r.status_code == 200:
                    for rec in r.json().get("records", []):
                        dates[rec["Id"]] = rec.get("LastActivityDate")
                else:
                    logger.warning("[salesforce] Activity date query returned %d", r.status_code)
            except Exception as exc:
                logger.warning("[salesforce] Activity date batch failed: %s", exc)
        return dates

    def _query_renewal_dates(self, account_ids: List[str]) -> Dict[str, Optional[str]]:
        """Return {account_id: nearest open Opportunity CloseDate ISO string}."""
        dates: Dict[str, Optional[str]] = {}
        for batch in self._chunks(account_ids, _SIGNAL_BATCH_SIZE):
            id_list = ", ".join(f"'{aid}'" for aid in batch)
            soql = (
                f"SELECT AccountId, MIN(CloseDate) "
                f"FROM Opportunity "
                f"WHERE AccountId IN ({id_list}) "
                f"AND IsClosed = false "
                f"AND IsDeleted = false "
                f"GROUP BY AccountId"
            )
            try:
                r = self._request(
                    "GET",
                    f"{self._api_base()}/query",
                    params={"q": soql},
                    timeout=30,
                )
                if r.status_code == 200:
                    for rec in r.json().get("records", []):
                        dates[rec["AccountId"]] = rec.get("expr0")
                else:
                    logger.warning("[salesforce] Renewal date query returned %d", r.status_code)
            except Exception as exc:
                logger.warning("[salesforce] Renewal date batch failed: %s", exc)
        return dates

    @staticmethod
    def _chunks(lst: List[str], size: int):
        """Yield successive chunks of a list."""
        for i in range(0, len(lst), size):
            yield lst[i:i + size]

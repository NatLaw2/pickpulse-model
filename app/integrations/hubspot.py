"""HubSpot CRM connector — hardened for external portals and real-world messy data.

Changes vs v1:
  - _request(): retry wrapper with exponential back-off + 429 Retry-After handling
  - Token refresh called proactively before every pull (not just write-back)
  - pull_accounts(): uses dynamic schema discovery instead of hardcoded properties
  - pull_signals(): services mode pulls engagement recency + deal activity instead
    of mapping contacts→seats/deals→support_tickets
  - connection_preflight(): returns counts + schema summary (not just True/False)
  - pull_company_properties(): fetches all portal property metadata
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from app.integrations.base import BaseConnector
from app.integrations.models import Account, AccountSignal, ConnectorConfig, PreflightResult
from app.integrations.normalization import (
    safe_float, safe_int, safe_date, clean_string,
    days_since, days_until,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.hubapi.com"

# Custom property group and properties created in the tenant's HubSpot portal.
_PICKPULSE_PROPERTY_GROUP = "pickpulse_churn"
_CHURN_PROPERTIES = [
    {
        "name": "pickpulse_churn_probability",
        "label": "Churn Probability",
        "type": "number",
        "fieldType": "number",
        "description": "PickPulse churn probability (0.00–1.00)",
    },
    {
        "name": "pickpulse_risk_tier",
        "label": "PickPulse Risk Tier",
        "type": "string",
        "fieldType": "text",
        "description": "PickPulse confidence tier: High Risk / Medium Risk / Low Risk",
    },
    {
        "name": "pickpulse_arr_at_risk",
        "label": "ARR at Risk",
        "type": "number",
        "fieldType": "number",
        "description": "ARR weighted by churn probability (PickPulse)",
    },
    {
        "name": "pickpulse_top_risk_drivers",
        "label": "Top Risk Drivers",
        "type": "string",
        "fieldType": "text",
        "description": "Comma-separated list of top churn risk factors (PickPulse)",
    },
    {
        "name": "pickpulse_recommended_action",
        "label": "Recommended Action",
        "type": "string",
        "fieldType": "text",
        "description": "PickPulse recommended CSM action",
    },
    {
        "name": "pickpulse_last_scored_at",
        "label": "PickPulse Last Scored",
        "type": "datetime",
        "fieldType": "date",
        "description": "Timestamp of last PickPulse scoring run",
    },
]

TASK_RISK_THRESHOLD = 70
TASK_RENEWAL_WINDOW_DAYS = 90

# Core properties always requested regardless of schema discovery.
# These are standard HubSpot fields present in every portal.
_BASE_COMPANY_PROPERTIES = [
    "hs_object_id", "name", "domain",
    "createdate", "notes_last_activity_date",
    "num_associated_contacts",
]


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

    @property
    def _business_mode(self) -> str:
        return self.config.extra.get("business_mode", "saas")

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Retry-aware HTTP wrapper
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
        """HTTP request with exponential back-off and 429 Retry-After handling.

        Retries on: 429 (rate limit), 500, 502, 503, 504.
        Raises immediately on 401, 403, 404 and other 4xx.
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
                    logger.warning("[hubspot] Rate limited — waiting %ds (attempt %d)", retry_after, attempt + 1)
                    time.sleep(min(retry_after, 30))
                    continue

                if r.status_code in (500, 502, 503, 504):
                    wait = 2 ** attempt  # 1, 2, 4 seconds
                    logger.warning("[hubspot] %d error, retrying in %ds", r.status_code, wait)
                    time.sleep(wait)
                    last_exc = requests.HTTPError(response=r)
                    continue

                return r

            except (requests.Timeout, requests.ConnectionError) as exc:
                wait = 2 ** attempt
                logger.warning("[hubspot] Network error (%s), retrying in %ds", exc, wait)
                time.sleep(wait)
                last_exc = exc

        raise last_exc or requests.RequestException("Max retries exceeded")

    # ------------------------------------------------------------------
    # Connection test (simple boolean — used by existing health endpoint)
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        try:
            self._refresh_token_if_needed()
            r = self._request("GET", f"{API_BASE}/crm/v3/objects/companies",
                              params={"limit": 1}, timeout=10)
            return r.status_code == 200
        except Exception as exc:
            logger.warning("HubSpot connection test failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Preflight check — returns rich diagnostics
    # ------------------------------------------------------------------

    def connection_preflight(self) -> PreflightResult:
        """Check connectivity and return counts + schema summary.

        Never raises — all failures are captured in the result.
        """
        from app.integrations.schema_mapper import discover as _discover

        warnings: List[str] = []
        checked_at = datetime.now(timezone.utc).isoformat()

        try:
            self._refresh_token_if_needed()
        except Exception as exc:
            warnings.append(f"token refresh: {exc}")

        # Portal ID
        portal_id: Optional[str] = None
        try:
            r = self._request("GET", f"{API_BASE}/oauth/v1/access-tokens/{self._get_token()}", timeout=10)
            if r.status_code == 200:
                portal_id = str(r.json().get("hub_id", ""))
        except Exception:
            pass

        def _count(object_type: str) -> int:
            try:
                r = self._request(
                    "POST",
                    f"{API_BASE}/crm/v3/objects/{object_type}/search",
                    json={"filterGroups": [], "limit": 1, "properties": ["hs_object_id"]},
                    timeout=15,
                )
                if r.status_code == 200:
                    return r.json().get("total", 0)
                return 0
            except Exception as exc:
                warnings.append(f"{object_type} count failed: {exc}")
                return 0

        companies_count = _count("companies")
        contacts_count = _count("contacts")
        deals_count = _count("deals")

        # Tickets may not be enabled in every portal
        tickets_count = 0
        try:
            tickets_count = _count("tickets")
        except Exception:
            warnings.append("tickets: not available in this portal")

        # Schema discovery
        properties_retrieved = False
        schema_coverage_pct = 0.0
        unmapped_fields: List[str] = []

        try:
            props = self.pull_company_properties()
            if props:
                properties_retrieved = True
                mapping = _discover(props, business_mode=self._business_mode)
                schema_coverage_pct = mapping.to_dict()["coverage_pct"]
                unmapped_fields = mapping.unmapped
        except Exception as exc:
            warnings.append(f"schema discovery: {exc}")

        connected = companies_count > 0 or properties_retrieved

        return PreflightResult(
            connected=connected,
            portal_id=portal_id,
            companies_count=companies_count,
            contacts_count=contacts_count,
            deals_count=deals_count,
            tickets_count=tickets_count,
            properties_retrieved=properties_retrieved,
            schema_coverage_pct=schema_coverage_pct,
            unmapped_fields=unmapped_fields,
            warnings=warnings,
            checked_at=checked_at,
        )

    # ------------------------------------------------------------------
    # Property metadata
    # ------------------------------------------------------------------

    def pull_company_properties(self) -> List[Dict[str, Any]]:
        """Fetch all company property definitions from this portal.

        Returns a list of property dicts: {name, label, type, fieldType, groupName, ...}
        """
        r = self._request("GET", f"{API_BASE}/crm/v3/properties/companies", timeout=20)
        r.raise_for_status()
        return r.json().get("results", [])

    # ------------------------------------------------------------------
    # Pull accounts (companies) — dynamic schema
    # ------------------------------------------------------------------

    def pull_accounts(self) -> List[Account]:
        from app.integrations.schema_mapper import discover as _discover
        from app.integrations.normalization import normalize_record_safe

        self._refresh_token_if_needed()

        # Dynamic schema discovery
        try:
            raw_props = self.pull_company_properties()
            mapping = _discover(raw_props, business_mode=self._business_mode)
            logger.info(
                "[hubspot] Schema: resolved=%d unmapped=%s",
                len(mapping.resolved),
                mapping.unmapped,
            )
        except Exception as exc:
            logger.warning("[hubspot] Schema discovery failed (%s) — using base properties", exc)
            mapping = None

        # Build property list: base + all resolved raw names
        properties = list(_BASE_COMPANY_PROPERTIES)
        if mapping:
            for fm in mapping.resolved.values():
                if fm.raw_name not in properties:
                    properties.append(fm.raw_name)
        else:
            # Fall back to hardcoded common names
            properties += [
                "annualrevenue", "industry", "numberofemployees",
                "hs_analytics_last_timestamp",
            ]

        accounts: List[Account] = []
        after: Optional[str] = None

        while True:
            params: Dict[str, Any] = {
                "limit": 100,
                "properties": ",".join(properties),
            }
            if after:
                params["after"] = after

            r = self._request("GET", f"{API_BASE}/crm/v3/objects/companies",
                              params=params, timeout=30)
            r.raise_for_status()
            data = r.json()

            for company in data.get("results", []):
                try:
                    props = company.get("properties", {})
                    if mapping:
                        normalized, warns = normalize_record_safe(
                            props, mapping,
                            business_mode=self._business_mode,
                            record_id=company["id"],
                        ) or ({}, [])
                        if warns:
                            logger.debug("[hubspot] company %s: %s", company["id"], warns)
                    else:
                        normalized = {}
                    accounts.append(self._company_to_account(company["id"], props, normalized))
                except Exception as exc:
                    logger.warning("[hubspot] Skipping company %s: %s", company.get("id"), exc)

            paging = data.get("paging", {}).get("next")
            if paging and paging.get("after"):
                after = paging["after"]
            else:
                break

        logger.info("[hubspot] Pulled %d companies (mode=%s)", len(accounts), self._business_mode)
        return accounts

    def _company_to_account(
        self,
        hs_id: str,
        props: Dict[str, Any],
        normalized: Dict[str, Any],
    ) -> Account:
        """Map raw HubSpot properties to normalized Account model."""
        # Prefer normalized values; fall back to raw for anything not in mapping
        arr = normalized.get("arr") or safe_float(props.get("annualrevenue"))
        company_size = normalized.get("company_size") or self._bucket_employees(props.get("numberofemployees"))
        industry = normalized.get("industry") or clean_string(props.get("industry"))
        plan = normalized.get("plan") or clean_string(props.get("plan"))

        created = safe_date(props.get("createdate"))
        created_dt = None
        if created:
            try:
                created_dt = datetime.strptime(created, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        return Account(
            external_id=hs_id,
            source="hubspot",
            name=clean_string(props.get("name", "")) or hs_id,
            email=clean_string(props.get("domain")),
            plan=plan,
            arr=arr,
            industry=industry,
            company_size=company_size,
            created_at=created_dt,
            raw_data={**props, "_normalized": normalized},
        )

    @staticmethod
    def _bucket_employees(value: Any) -> Optional[str]:
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
    # Pull signals — mode-aware
    # ------------------------------------------------------------------

    def pull_signals(self, external_ids: List[str]) -> List[AccountSignal]:
        """Pull engagement signals from HubSpot.

        SaaS mode:  contacts count → seats proxy, deal count as activity proxy.
        Services mode: engagement recency (last activity date), deal activity,
                       ticket count, contact count as stakeholder coverage.
        """
        self._refresh_token_if_needed()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        signals: List[AccountSignal] = []

        for eid in external_ids:
            try:
                if self._business_mode == "services":
                    signal = self._pull_signal_services(eid, today)
                else:
                    signal = self._pull_signal_saas(eid, today)
                if signal:
                    signals.append(signal)
            except Exception as exc:
                logger.warning("[hubspot] Signal pull failed for %s: %s", eid, exc)

        logger.info("[hubspot] Pulled %d signals (mode=%s)", len(signals), self._business_mode)
        return signals

    def _pull_signal_saas(self, company_id: str, date: str) -> Optional[AccountSignal]:
        """SaaS mode: contacts count → seats, deal count as activity proxy."""
        contacts_count = self._get_association_count(company_id, "contacts")
        deal_count = self._get_association_count(company_id, "deals")

        # Last activity date from company properties
        r = self._request(
            "GET", f"{API_BASE}/crm/v3/objects/companies/{company_id}",
            params={"properties": "notes_last_activity_date,hs_last_activity_date"},
            timeout=15,
        )
        days_inactive = None
        if r.status_code == 200:
            props = r.json().get("properties", {})
            last_act = safe_date(props.get("notes_last_activity_date") or props.get("hs_last_activity_date"))
            days_inactive = days_since(last_act)

        return AccountSignal(
            external_id=company_id,
            signal_date=date,
            seats=contacts_count if contacts_count > 0 else None,
            support_tickets=None,
            days_since_last_login=days_inactive,
            extra={
                "contacts": contacts_count,
                "deals": deal_count,
                "business_mode": "saas",
            },
        )

    def _pull_signal_services(self, company_id: str, date: str) -> Optional[AccountSignal]:
        """Services mode: engagement recency, deal activity, contact count, tickets.

        Signals returned in AccountSignal.extra so the scoring layer can pick them up:
          days_since_last_activity — primary recency signal
          deal_count               — relationship activity depth
          engagement_frequency     — calls + emails + meetings in last 90d (if available)
          contact_count            — stakeholder coverage
          ticket_count             — support volume
        """
        contact_count = self._get_association_count(company_id, "contacts")
        deal_count = self._get_association_count(company_id, "deals")
        ticket_count = 0
        try:
            ticket_count = self._get_association_count(company_id, "tickets")
        except Exception:
            pass

        # Last activity from company record
        r = self._request(
            "GET", f"{API_BASE}/crm/v3/objects/companies/{company_id}",
            params={"properties": "notes_last_activity_date,hs_last_activity_date,notes_last_contacted"},
            timeout=15,
        )
        days_inactive = None
        if r.status_code == 200:
            props = r.json().get("properties", {})
            candidates = [
                props.get("notes_last_activity_date"),
                props.get("hs_last_activity_date"),
                props.get("notes_last_contacted"),
            ]
            for c in candidates:
                last_act = safe_date(c)
                if last_act:
                    days_inactive = days_since(last_act)
                    break

        # Engagement frequency — count engagements in last 90d if accessible
        engagement_frequency = self._count_recent_engagements(company_id, days=90)

        # Map services signals to AccountSignal fields:
        # - days_since_last_login ← days_since_last_activity (recency)
        # - support_tickets       ← ticket_count
        # - seats                 ← contact_count (stakeholder coverage)
        return AccountSignal(
            external_id=company_id,
            signal_date=date,
            seats=contact_count if contact_count > 0 else None,
            support_tickets=ticket_count if ticket_count > 0 else None,
            days_since_last_login=days_inactive,
            extra={
                "contact_count": contact_count,
                "deal_count": deal_count,
                "ticket_count": ticket_count,
                "days_since_last_activity": days_inactive,
                "engagement_frequency": engagement_frequency,
                "business_mode": "services",
            },
        )

    def _get_association_count(self, company_id: str, object_type: str) -> int:
        """Return the number of objects associated to a company. Returns 0 on error."""
        try:
            r = self._request(
                "GET",
                f"{API_BASE}/crm/v3/objects/companies/{company_id}/associations/{object_type}",
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                # Try 'total' first (v3 paged), fall back to len(results)
                return data.get("total") or len(data.get("results", []))
            return 0
        except Exception:
            return 0

    def _count_recent_engagements(self, company_id: str, days: int = 90) -> int:
        """Count engagements (emails, calls, meetings) for a company in the last N days.

        Returns 0 on API error — non-fatal.
        """
        try:
            from datetime import timedelta
            cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
            r = self._request(
                "POST",
                f"{API_BASE}/crm/v3/objects/engagements/search",
                json={
                    "filterGroups": [{
                        "filters": [
                            {
                                "propertyName": "hs_createdate",
                                "operator": "GTE",
                                "value": str(cutoff),
                            }
                        ]
                    }],
                    "properties": ["hs_object_id"],
                    "limit": 1,
                },
                timeout=15,
            )
            if r.status_code == 200:
                return r.json().get("total", 0)
            return 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Write-back helpers (unchanged from v1)
    # ------------------------------------------------------------------

    def _refresh_token_if_needed(self) -> None:
        """Proactively refresh the access token if it may be near expiry.

        HubSpot tokens expire after 6 hours (21,600 s). We refresh when the
        stored token is absent or when refresh_token is available and the
        token is older than 5.5 hours.
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
        """Idempotently create the PickPulse property group and custom properties."""
        self._refresh_token_if_needed()
        headers = self._headers()

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

        Returns the number of companies successfully updated.
        """
        self._refresh_token_if_needed()

        rows = [s for s in scores if s.get("hs_object_id")]
        skipped = len(scores) - len(rows)
        if skipped:
            logger.warning("[hubspot] push_churn_scores: skipping %d records with missing hs_object_id", skipped)
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
                    props["pickpulse_churn_probability"] = str(round(float(s["churn_risk_pct"]) / 100, 4))
                if s.get("tier"):
                    props["pickpulse_risk_tier"] = str(s["tier"])
                if s.get("arr_at_risk") is not None:
                    props["pickpulse_arr_at_risk"] = str(round(float(s["arr_at_risk"]), 2))
                if s.get("top_risk_drivers"):
                    props["pickpulse_top_risk_drivers"] = str(s["top_risk_drivers"])
                if s.get("recommended_action"):
                    props["pickpulse_recommended_action"] = str(s["recommended_action"])
                props["pickpulse_last_scored_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                inputs.append({"id": str(s["hs_object_id"]), "properties": props})

            try:
                r = self._request(
                    "POST",
                    f"{API_BASE}/crm/v3/objects/companies/batch/update",
                    json={"inputs": inputs},
                    timeout=30,
                )
                if r.status_code in (200, 207):
                    resp_data = r.json()
                    n_errors = resp_data.get("numErrors", 0) or 0
                    updated += max(0, len(batch) - n_errors)
                    if n_errors:
                        logger.warning(
                            "[hubspot] Batch %d: %d/%d errors: %s",
                            i // batch_size + 1, n_errors, len(batch),
                            str(resp_data.get("errors", []))[:300],
                        )
                else:
                    logger.warning("[hubspot] Batch update returned %d: %s", r.status_code, r.text[:300])
            except Exception as exc:
                logger.warning("[hubspot] push_churn_scores batch %d failed: %s", i // batch_size + 1, exc)

            if i + batch_size < len(rows):
                time.sleep(0.15)

        return updated

    def create_task(
        self,
        account: Dict[str, Any],
        subject: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Optional[str]:
        """Create a HubSpot task for a high-risk account. Returns task_id or None."""
        self._refresh_token_if_needed()

        hs_company_id = str(account.get("hs_object_id", ""))
        if not hs_company_id:
            logger.warning("[hubspot] create_task skipped: hs_object_id missing")
            return None

        account_id = str(account.get("account_id", ""))
        churn_risk_pct = float(account.get("churn_risk_pct") or 0)
        days_renewal = account.get("days_until_renewal")
        recommended_action = account.get("recommended_action", "Review")

        task_subject = subject or f"[PickPulse] {recommended_action} — {account_id}"
        renewal_note = f" | Renewal in {int(float(days_renewal))} days" if days_renewal is not None else ""
        task_body = body or (
            f"PickPulse risk: {churn_risk_pct:.0f}%{renewal_note}. "
            f"Recommended: {recommended_action}."
        )

        try:
            r = self._request(
                "POST",
                f"{API_BASE}/crm/v3/objects/tasks",
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
            if task_id:
                self._associate_task_to_company(task_id, hs_company_id)
            return task_id
        except Exception as exc:
            logger.warning("[hubspot] create_task failed for %s: %s", account_id, exc)
            return None

    def _associate_task_to_company(self, task_id: str, company_id: str) -> None:
        try:
            r = self._request(
                "PUT",
                f"{API_BASE}/crm/v3/objects/tasks/{task_id}/associations/companies/{company_id}/TASK_TO_COMPANY",
                timeout=10,
            )
            if r.status_code not in (200, 201):
                logger.warning("[hubspot] task-company association returned %d", r.status_code)
        except Exception as exc:
            logger.warning("[hubspot] _associate_task_to_company failed: %s", exc)

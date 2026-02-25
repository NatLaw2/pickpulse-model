"""Stripe connector — pulls subscriptions, invoices, and charges."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from app.integrations.base import BaseConnector
from app.integrations.models import Account, AccountSignal, ConnectorConfig

logger = logging.getLogger(__name__)

API_BASE = "https://api.stripe.com/v1"


class StripeConnector(BaseConnector):

    @property
    def name(self) -> str:
        return "stripe"

    @property
    def display_name(self) -> str:
        return "Stripe Billing"

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
        }

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        try:
            r = requests.get(
                f"{API_BASE}/customers",
                headers=self._headers(),
                params={"limit": 1},
                timeout=10,
            )
            return r.status_code == 200
        except Exception as exc:
            logger.warning("Stripe connection test failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Pull accounts (customers + subscriptions)
    # ------------------------------------------------------------------

    def pull_accounts(self) -> List[Account]:
        accounts: List[Account] = []
        starting_after: Optional[str] = None

        while True:
            params: Dict[str, Any] = {"limit": 100, "expand[]": "data.subscriptions"}
            if starting_after:
                params["starting_after"] = starting_after

            r = requests.get(
                f"{API_BASE}/customers",
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()

            for customer in data.get("data", []):
                accounts.append(self._customer_to_account(customer))

            if data.get("has_more") and data["data"]:
                starting_after = data["data"][-1]["id"]
            else:
                break

        logger.info("Stripe: pulled %d customers", len(accounts))
        return accounts

    def _customer_to_account(self, customer: Dict[str, Any]) -> Account:
        subs = customer.get("subscriptions", {}).get("data", [])
        active_sub = next(
            (s for s in subs if s.get("status") in ("active", "trialing")),
            subs[0] if subs else None,
        )

        arr = None
        plan_name = None
        if active_sub:
            # Calculate ARR from subscription items
            items = active_sub.get("items", {}).get("data", [])
            total_monthly = 0
            for item in items:
                price = item.get("price", {})
                amount = price.get("unit_amount", 0) / 100  # cents to dollars
                interval = price.get("recurring", {}).get("interval", "month")
                interval_count = price.get("recurring", {}).get("interval_count", 1)
                qty = item.get("quantity", 1)

                if interval == "year":
                    total_monthly += (amount * qty) / (12 * interval_count)
                elif interval == "month":
                    total_monthly += (amount * qty) / interval_count
                elif interval == "week":
                    total_monthly += (amount * qty * 4.33) / interval_count

            arr = round(total_monthly * 12, 2)
            plan_name = active_sub.get("items", {}).get("data", [{}])[0].get(
                "price", {}
            ).get("nickname") or active_sub.get("items", {}).get("data", [{}])[0].get(
                "plan", {}
            ).get("nickname")

        created_ts = customer.get("created")
        created_dt = (
            datetime.fromtimestamp(created_ts, tz=timezone.utc)
            if created_ts
            else None
        )

        return Account(
            external_id=customer["id"],
            source="stripe",
            name=customer.get("name") or customer.get("email", ""),
            email=customer.get("email"),
            plan=plan_name,
            arr=arr,
            created_at=created_dt,
            raw_data={"customer_id": customer["id"], "subscription_count": len(subs)},
        )

    # ------------------------------------------------------------------
    # Pull signals (invoices + charges as engagement proxy)
    # ------------------------------------------------------------------

    def pull_signals(self, external_ids: List[str]) -> List[AccountSignal]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        signals: List[AccountSignal] = []

        for eid in external_ids:
            try:
                signal = self._pull_customer_signal(eid, today)
                if signal:
                    signals.append(signal)
            except Exception as exc:
                logger.warning("Stripe signal pull failed for %s: %s", eid, exc)

        logger.info("Stripe: pulled %d signals", len(signals))
        return signals

    def _pull_customer_signal(self, customer_id: str, date: str) -> AccountSignal | None:
        # Get subscriptions for renewal info
        r = requests.get(
            f"{API_BASE}/subscriptions",
            headers=self._headers(),
            params={"customer": customer_id, "limit": 5},
            timeout=15,
        )
        if r.status_code != 200:
            return None

        subs = r.json().get("data", [])
        active_sub = next(
            (s for s in subs if s.get("status") in ("active", "trialing")),
            None,
        )

        days_until_renewal = None
        auto_renew = None
        renewal_status = None

        if active_sub:
            period_end = active_sub.get("current_period_end")
            if period_end:
                end_dt = datetime.fromtimestamp(period_end, tz=timezone.utc)
                days_until_renewal = (end_dt - datetime.now(timezone.utc)).days

            cancel_at_period_end = active_sub.get("cancel_at_period_end", False)
            auto_renew = 0 if cancel_at_period_end else 1

            status = active_sub.get("status", "")
            if cancel_at_period_end:
                renewal_status = "pending_cancel"
            elif status == "active":
                renewal_status = "active"
            elif status == "trialing":
                renewal_status = "trial"
            else:
                renewal_status = status

        # Get recent invoice count as engagement signal
        r = requests.get(
            f"{API_BASE}/invoices",
            headers=self._headers(),
            params={"customer": customer_id, "limit": 10, "status": "paid"},
            timeout=15,
        )
        invoice_count = 0
        if r.status_code == 200:
            invoice_count = len(r.json().get("data", []))

        return AccountSignal(
            external_id=customer_id,
            signal_date=date,
            days_until_renewal=days_until_renewal,
            auto_renew_flag=auto_renew,
            renewal_status=renewal_status,
            extra={"paid_invoices_recent": invoice_count},
        )

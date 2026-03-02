"""CSV import connector — reads uploaded CSV files and normalizes to accounts."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from app.integrations.base import BaseConnector
from app.integrations.models import Account, AccountSignal, ConnectorConfig

logger = logging.getLogger(__name__)


class CSVConnector(BaseConnector):
    """Connector that reads from an uploaded CSV file.

    The CSV path is passed via config.extra["csv_path"].
    Field mappings are applied from config.extra["field_map"] or defaults.
    """

    @property
    def name(self) -> str:
        return "csv"

    @property
    def display_name(self) -> str:
        return "CSV Import"

    @property
    def auth_method(self) -> str:
        return "none"

    def test_connection(self) -> bool:
        """Check that the CSV file exists and is readable."""
        import os
        csv_path = self.config.extra.get("csv_path", "")
        return bool(csv_path) and os.path.exists(csv_path)

    def pull_accounts(self) -> List[Account]:
        csv_path = self.config.extra.get("csv_path", "")
        if not csv_path:
            raise ValueError("No csv_path in connector config")

        df = pd.read_csv(csv_path)
        field_map = self.config.extra.get("field_map", {})

        accounts: List[Account] = []
        for idx, row in df.iterrows():
            raw = row.to_dict()
            accounts.append(self._row_to_account(idx, raw, field_map))

        logger.info("CSV: loaded %d accounts from %s", len(accounts), csv_path)
        return accounts

    def _row_to_account(
        self,
        idx: int,
        raw: Dict[str, Any],
        field_map: Dict[str, str],
    ) -> Account:
        def _get(target: str) -> Any:
            """Look up a field by target name through the field map or direct."""
            # Check if any source maps to this target
            for source, tgt in field_map.items():
                if tgt == target and source in raw:
                    return raw[source]
            # Fall back to direct column name
            return raw.get(target)

        name = _get("name") or _get("company_name") or f"Account-{idx}"
        arr_val = _get("arr") or _get("annual_revenue")
        arr = None
        if arr_val is not None:
            try:
                arr = float(arr_val)
            except (ValueError, TypeError):
                pass

        seats_val = _get("seats")
        seats = None
        if seats_val is not None:
            try:
                seats = int(seats_val)
            except (ValueError, TypeError):
                pass

        external_id = str(raw.get("id", raw.get("external_id", f"csv-{idx}")))

        return Account(
            external_id=external_id,
            source="csv",
            name=str(name),
            email=str(_get("domain") or _get("email") or ""),
            plan=str(_get("plan") or "") if _get("plan") else None,
            arr=arr,
            seats=seats,
            industry=str(_get("industry") or "") if _get("industry") else None,
            company_size=str(_get("company_size") or "") if _get("company_size") else None,
            raw_data=raw,
        )

    def pull_signals(self, external_ids: List[str]) -> List[AccountSignal]:
        """CSV doesn't have live signals — return empty list."""
        return []

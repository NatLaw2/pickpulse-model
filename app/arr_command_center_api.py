"""ARR Command Center — FastAPI router.

Endpoints
---------
GET  /api/arr-command-center
    Returns summary metrics + ranked accounts list.

GET  /api/accounts/{account_id}/command-center-details
    Returns full account drawer payload: drivers, signals, interventions,
    data quality notes.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from .auth import get_tenant_id
from .arr_command_center import build_command_center, get_account_details

logger = logging.getLogger("pickpulse.arr_command_center_api")

router = APIRouter(prefix="/api")


@router.get("/arr-command-center")
def arr_command_center(tenant_id: str = Depends(get_tenant_id)):
    """Executive summary + ranked accounts.

    Returns has_predictions=False with an empty accounts list when no scored
    data exists — the frontend renders a clean empty state in that case.
    """
    try:
        return build_command_center(tenant_id=tenant_id)
    except Exception as exc:
        logger.exception("[arr_cc] build_command_center failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/accounts/{account_id}/command-center-details")
def account_command_center_details(
    account_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """Full account drawer payload.

    404 when the account has no scored prediction record for this tenant.
    """
    try:
        result = get_account_details(account_id=account_id, tenant_id=tenant_id)
    except Exception as exc:
        logger.exception("[arr_cc] get_account_details failed for %s: %s", account_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No prediction record found for account {account_id}.",
        )

    return result

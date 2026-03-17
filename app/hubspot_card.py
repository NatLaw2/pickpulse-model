"""HubSpot CRM Intelligence Card endpoint.

HubSpot calls GET /api/crm-card/{tenant_id}?hs_object_id=<company_id>&...
whenever a sales rep views a company record that has the PickPulse card
installed.  This endpoint validates the HMAC-SHA256 signature supplied by
HubSpot and returns a card JSON payload with churn risk data.

Auth:  HMAC-SHA256 via X-HubSpot-Signature-v3 header — no tenant JWT needed.
       The tenant is identified by the {tenant_id} path parameter, which the
       customer embeds in the card URL when configuring their private app.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from .engine import store
from .explain import _load_feature_weights, generate_risk_drivers

logger = logging.getLogger("pickpulse.hubspot_card")

router = APIRouter(tags=["hubspot-card"])

MODULE = "churn"

# HubSpot timestamps must be within this window to be accepted
_MAX_TIMESTAMP_AGE_S = 300  # 5 minutes


# ---------------------------------------------------------------------------
# HMAC validation
# ---------------------------------------------------------------------------

def _validate_hubspot_signature(request: Request, body: bytes, timestamp: str) -> None:
    """Raise HTTPException(401) if the X-HubSpot-Signature-v3 header is invalid.

    HubSpot signs: HTTP_METHOD + URI + REQUEST_BODY + TIMESTAMP
    using HMAC-SHA256 with the app's client secret.
    """
    client_secret = os.environ.get("HUBSPOT_CLIENT_SECRET", "")
    if not client_secret:
        # If the secret isn't configured, skip validation (dev mode)
        logger.warning("[hubspot_card] HUBSPOT_CLIENT_SECRET not set — skipping HMAC check")
        return

    # Reject stale timestamps
    try:
        ts_int = int(timestamp)
        if abs(time.time() - ts_int / 1000) > _MAX_TIMESTAMP_AGE_S:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Request timestamp expired")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid timestamp")

    method = request.method.upper()
    # Full URI including query string
    uri = str(request.url)
    body_str = body.decode("utf-8", errors="replace")
    message = f"{method}{uri}{body_str}{timestamp}"

    expected = hmac.new(
        client_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    received = request.headers.get("X-HubSpot-Signature-v3", "")
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid HubSpot signature")


# ---------------------------------------------------------------------------
# Card response builder
# ---------------------------------------------------------------------------

def _build_card_response(
    hs_object_id: str,
    rec: Optional[Dict[str, Any]],
    feature_weights: Optional[Dict[str, float]],
) -> Dict[str, Any]:
    """Build the HubSpot CRM card JSON payload."""
    if rec is None:
        # Empty state — no prediction yet
        return {
            "results": [{
                "objectId": int(hs_object_id) if hs_object_id.isdigit() else 0,
                "title": "PickPulse Risk Intelligence",
                "properties": [
                    {"label": "Status", "dataType": "STRING", "value": "No prediction available — run PickPulse predictions first"},
                ],
            }]
        }

    churn_risk_pct = float(rec.get("churn_risk_pct") or 0)
    arr = float(rec.get("arr") or 0)
    arr_at_risk = float(rec.get("arr_at_risk") or 0)
    days_renewal = rec.get("days_until_renewal")
    tier = str(rec.get("tier") or "Unknown")
    recommended_action = str(rec.get("recommended_action") or "Monitor")

    drivers = generate_risk_drivers(rec, feature_weights=feature_weights)
    top_driver = drivers[0] if drivers else "No dominant risk factor identified"

    properties: List[Dict[str, Any]] = [
        {"label": "Churn Risk", "dataType": "PERCENT", "value": str(round(churn_risk_pct))},
        {"label": "Tier", "dataType": "STRING", "value": tier},
        {"label": "Recommended Action", "dataType": "STRING", "value": recommended_action},
        {"label": "Top Risk Driver", "dataType": "STRING", "value": top_driver},
    ]

    if arr_at_risk > 0:
        properties.insert(1, {"label": "ARR at Risk", "dataType": "CURRENCY", "value": str(int(arr_at_risk))})
    elif arr > 0:
        properties.insert(1, {"label": "ARR", "dataType": "CURRENCY", "value": str(int(arr))})

    if days_renewal is not None:
        try:
            properties.append({"label": "Days to Renewal", "dataType": "NUMERIC", "value": str(int(float(days_renewal)))})
        except (TypeError, ValueError):
            pass

    try:
        obj_id = int(hs_object_id) if hs_object_id.isdigit() else 0
    except Exception:
        obj_id = 0

    return {
        "results": [{
            "objectId": obj_id,
            "title": "PickPulse Risk Intelligence",
            "properties": properties,
        }]
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/api/crm-card/{tenant_id}")
async def hubspot_crm_card(
    tenant_id: str,
    request: Request,
    hs_object_id: str = Query(..., description="HubSpot company object ID"),
    portalId: Optional[str] = Query(None),
    userId: Optional[str] = Query(None),
):
    """HubSpot CRM Intelligence Card — called server-to-server by HubSpot.

    HubSpot provides:
      hs_object_id  — the company record being viewed
      portalId      — the HubSpot portal ID (logged for audit)
      userId        — the HubSpot user viewing the card (logged for audit)
    """
    # Read body (empty for GET, but required for HMAC computation)
    body = await request.body()
    timestamp = request.headers.get("X-HubSpot-Signature-Timestamp", "0")
    _validate_hubspot_signature(request, body, timestamp)

    # Look up prediction for this company
    # HubSpot's hs_object_id maps to account_id in predictions_live
    rec = store.get_prediction_for_account(tenant_id, MODULE, hs_object_id)

    # Load model feature weights for importance-ranked drivers
    feature_weights: Optional[Dict[str, float]] = None
    try:
        current_run = store.get_current_model_run(tenant_id, MODULE)
        if current_run and current_run.get("artifact_path"):
            feature_weights = _load_feature_weights(current_run["artifact_path"]) or None
    except Exception:
        pass

    logger.info(
        "[hubspot_card] tenant=%s hs_object_id=%s portal=%s user=%s found=%s",
        tenant_id, hs_object_id, portalId, userId, rec is not None,
    )

    return _build_card_response(hs_object_id, rec, feature_weights)

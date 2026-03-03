"""JWT authentication middleware for multi-tenancy.

Extracts tenant_id from Supabase Auth JWT (sub claim).
"""
from __future__ import annotations

import os
import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


def _decode_token(token: str) -> dict:
    """Decode and verify a Supabase JWT."""
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_JWT_SECRET not configured",
        )
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


async def get_tenant_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """FastAPI dependency — returns tenant_id (= auth.uid()) from JWT.

    Raises 401 if no valid token is provided.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    payload = _decode_token(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
        )
    return sub


async def get_optional_tenant_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[str]:
    """FastAPI dependency — returns tenant_id if token present, None otherwise.

    Use for endpoints that work both authenticated and unauthenticated.
    """
    if credentials is None:
        return None
    try:
        payload = _decode_token(credentials.credentials)
        return payload.get("sub")
    except HTTPException:
        return None

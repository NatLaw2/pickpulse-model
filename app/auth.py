"""JWT authentication middleware for multi-tenancy.

Extracts tenant_id from Supabase Auth JWT (sub claim).
Supports both HS256 (legacy secret) and ES256/RS256 (JWKS) verification.
"""
from __future__ import annotations

import os
import logging
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", os.environ.get("VITE_SUPABASE_URL", ""))

# JWKS client — lazily initialised on first ES256/RS256 token
_jwks_client: Optional[PyJWKClient] = None


def _get_jwks_client() -> PyJWKClient:
    """Return (and cache) a PyJWKClient pointing at this project's JWKS endpoint."""
    global _jwks_client
    if _jwks_client is None:
        if not SUPABASE_URL:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SUPABASE_URL not configured — cannot fetch JWKS",
            )
        jwks_url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        logger.info("[auth] JWKS URL: %s", jwks_url)
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


def _decode_token(token: str) -> dict:
    """Decode and verify a Supabase JWT (HS256 or ES256/RS256)."""
    # Peek at the unverified header to decide verification strategy
    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed JWT header: {exc}",
        )

    alg = header.get("alg", "unknown")
    kid = header.get("kid", "none")
    logger.info("[auth] token header — alg=%s kid=%s", alg, kid)

    try:
        if alg == "HS256":
            # Legacy symmetric secret
            if not SUPABASE_JWT_SECRET:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="SUPABASE_JWT_SECRET not configured",
                )
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            # Asymmetric key — fetch from JWKS
            client = _get_jwks_client()
            signing_key = client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
            )

        logger.info(
            "[auth] verified — alg=%s sub=%s aud=%s iss=%s",
            alg,
            payload.get("sub", "?"),
            payload.get("aud", "?"),
            payload.get("iss", "?"),
        )
        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("[auth] verification failed — alg=%s kid=%s reason=%s", alg, kid, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token (alg={alg}, kid={kid}): {exc}",
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
            detail="Missing Authorization Bearer token",
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

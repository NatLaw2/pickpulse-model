"""AES-256-GCM encryption for integration tokens."""
from __future__ import annotations

import base64
import os
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_key() -> bytes:
    """Return the 32-byte encryption key from env (hex-encoded)."""
    hex_key = os.environ.get("INTEGRATION_ENCRYPTION_KEY", "")
    if not hex_key:
        raise RuntimeError(
            "INTEGRATION_ENCRYPTION_KEY env var is required. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    key = bytes.fromhex(hex_key)
    if len(key) != 32:
        raise ValueError("INTEGRATION_ENCRYPTION_KEY must be 64 hex chars (32 bytes)")
    return key


def encrypt_token(plaintext: str) -> Tuple[str, str]:
    """Encrypt a token string with AES-256-GCM.

    Returns (ciphertext_b64, iv_b64).
    """
    key = _get_key()
    iv = os.urandom(12)  # 96-bit nonce for GCM
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    return (
        base64.b64encode(ciphertext).decode("ascii"),
        base64.b64encode(iv).decode("ascii"),
    )


def decrypt_token(ciphertext_b64: str, iv_b64: str) -> str:
    """Decrypt a token encrypted with encrypt_token."""
    key = _get_key()
    ciphertext = base64.b64decode(ciphertext_b64)
    iv = base64.b64decode(iv_b64)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ciphertext, None)
    return plaintext.decode("utf-8")

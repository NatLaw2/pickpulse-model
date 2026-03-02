"""Tests for AES-256-GCM token encryption."""
import os
import secrets
import pytest


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Set a test encryption key for all tests."""
    key = secrets.token_hex(32)
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", key)


def test_encrypt_decrypt_roundtrip():
    """Token survives encrypt → decrypt roundtrip."""
    from app.integrations.crypto import encrypt_token, decrypt_token

    token = "sk-test-1234567890abcdef"
    ciphertext, iv = encrypt_token(token)

    assert ciphertext != token  # actually encrypted
    assert iv  # IV is present

    decrypted = decrypt_token(ciphertext, iv)
    assert decrypted == token


def test_different_tokens_produce_different_ciphertexts():
    """Two different tokens produce different ciphertexts."""
    from app.integrations.crypto import encrypt_token

    ct1, _ = encrypt_token("token-a")
    ct2, _ = encrypt_token("token-b")
    assert ct1 != ct2


def test_same_token_produces_different_ciphertexts():
    """Same token encrypted twice produces different ciphertexts (random IV)."""
    from app.integrations.crypto import encrypt_token

    ct1, iv1 = encrypt_token("same-token")
    ct2, iv2 = encrypt_token("same-token")
    assert ct1 != ct2 or iv1 != iv2


def test_wrong_key_raises_error(monkeypatch):
    """Decrypting with wrong key raises an error."""
    from app.integrations.crypto import encrypt_token, decrypt_token, _get_key

    ciphertext, iv = encrypt_token("secret-token")

    # Change the key
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", secrets.token_hex(32))
    # Clear cached key by reimporting
    import importlib
    import app.integrations.crypto as crypto_mod
    importlib.reload(crypto_mod)

    with pytest.raises(Exception):
        crypto_mod.decrypt_token(ciphertext, iv)


def test_tampered_ciphertext_raises_error():
    """Tampered ciphertext raises an error (GCM tag validation)."""
    from app.integrations.crypto import encrypt_token, decrypt_token
    import base64

    ciphertext, iv = encrypt_token("secret-token")

    # Tamper with ciphertext
    raw = bytearray(base64.b64decode(ciphertext))
    raw[0] ^= 0xFF  # flip a byte
    tampered = base64.b64encode(bytes(raw)).decode()

    with pytest.raises(Exception):
        decrypt_token(tampered, iv)


def test_missing_key_raises_error(monkeypatch):
    """Missing encryption key raises RuntimeError."""
    monkeypatch.delenv("INTEGRATION_ENCRYPTION_KEY", raising=False)

    import importlib
    import app.integrations.crypto as crypto_mod
    importlib.reload(crypto_mod)

    with pytest.raises(RuntimeError, match="INTEGRATION_ENCRYPTION_KEY"):
        crypto_mod.encrypt_token("test")


def test_unicode_token():
    """Unicode tokens are handled correctly."""
    from app.integrations.crypto import encrypt_token, decrypt_token

    token = "tok\u00e9n-with-\u00fcnicode-\U0001f600"
    ct, iv = encrypt_token(token)
    assert decrypt_token(ct, iv) == token


def test_empty_token():
    """Empty string token works."""
    from app.integrations.crypto import encrypt_token, decrypt_token

    ct, iv = encrypt_token("")
    assert decrypt_token(ct, iv) == ""


def test_long_token():
    """Very long token works."""
    from app.integrations.crypto import encrypt_token, decrypt_token

    token = "x" * 10000
    ct, iv = encrypt_token(token)
    assert decrypt_token(ct, iv) == token

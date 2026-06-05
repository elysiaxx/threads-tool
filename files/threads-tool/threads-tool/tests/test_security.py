"""Test mật khẩu, JWT, OAuth state token và mã hóa token."""
from cryptography.fernet import Fernet

from app.config import settings
from app.core import crypto
from app.core.security import (
    create_access_token,
    create_state_token,
    decode_access_token,
    hash_password,
    verify_password,
    verify_state_token,
)


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    token = create_access_token({"sub": "u1", "email": "a@b.com", "role": "user"})
    payload = decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["email"] == "a@b.com"


def test_decode_invalid_token():
    assert decode_access_token("not-a-token") is None


def test_state_token_roundtrip():
    token = create_state_token("u42")
    assert verify_state_token(token) == "u42"


def test_state_token_rejects_plain_access_token():
    """Access token thường không được nhận làm state token (sai 'typ')."""
    plain = create_access_token({"sub": "u1"})
    assert verify_state_token(plain) is None


def test_crypto_roundtrip():
    settings.token_encryption_key = Fernet.generate_key().decode()
    enc = crypto.encrypt_token("super-secret")
    assert enc != "super-secret"
    assert crypto.decrypt_token(enc) == "super-secret"

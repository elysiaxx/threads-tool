"""
Mã hóa token mỗi user trước khi lưu (`access_token_enc`). Dùng Fernet
(AES-128-CBC + HMAC). Key lấy từ env TOKEN_ENCRYPTION_KEY.

Sinh key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    if not settings.token_encryption_key:
        raise RuntimeError(
            "Thiếu TOKEN_ENCRYPTION_KEY. Sinh bằng Fernet.generate_key() và đặt vào .env"
        )
    return Fernet(settings.token_encryption_key.encode())


def encrypt_token(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()

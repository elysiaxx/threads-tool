from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- mật khẩu ---
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


# --- JWT access token ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


# --- OAuth state token ---
# Callback OAuth không mang theo JWT (do Meta redirect về), nên ta nhét user_id
# vào "state" đã ký, callback verify lại để gắn token đúng chủ.
def create_state_token(user_id: str) -> str:
    return create_access_token(
        {"sub": user_id, "typ": "oauth_state"}, timedelta(minutes=10)
    )


def verify_state_token(token: str) -> Optional[str]:
    payload = decode_access_token(token)
    if not payload or payload.get("typ") != "oauth_state":
        return None
    return payload.get("sub")

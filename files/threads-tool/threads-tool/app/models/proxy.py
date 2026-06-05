"""
Schema cho proxy. Mật khẩu lưu mã hóa (password_enc), không bao giờ trả ra
plaintext. Proxy có thể gán cố định cho 1 account, hoặc nằm trong pool (active)
để xoay vòng khi account chưa gán proxy riêng.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ProxyProtocol = Literal["http", "https", "socks5"]


class ProxyCreate(BaseModel):
    label: str
    protocol: ProxyProtocol = "http"
    host: str
    port: int = Field(ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    active: bool = True  # tham gia pool xoay vòng


class ProxyUpdate(BaseModel):
    label: Optional[str] = None
    protocol: Optional[ProxyProtocol] = None
    host: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    active: Optional[bool] = None


class ProxyCheck(BaseModel):
    ok: bool
    ip: Optional[str] = None
    error: Optional[str] = None
    checked_at: Optional[datetime] = None


class ProxyPublic(BaseModel):
    id: str
    label: str
    protocol: ProxyProtocol
    host: str
    port: int
    username: Optional[str] = None
    has_password: bool = False
    active: bool = True
    last_check: Optional[ProxyCheck] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

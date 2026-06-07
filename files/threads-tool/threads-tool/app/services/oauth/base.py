"""
Lớp OAuth pluggable. Mỗi nền tảng (Threads trước, IG/FB/X sau) cài đặt
giao thức OAuthProvider; thêm nền tảng mới = thêm 1 provider + register, không
phải sửa route. Endpoint/scope/redirect đều cấu hình qua env (xem config.py).
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable


@dataclass
class OAuthTokens:
    access_token: str
    expires_at: Optional[datetime] = None
    external_user_id: Optional[str] = None
    username: Optional[str] = None


@runtime_checkable
class OAuthProvider(Protocol):
    name: str

    def authorize_url(self, state: str) -> str:
        """URL để redirect user sang trang cấp quyền."""
        ...

    async def exchange_code(
        self, code: str, proxy: Optional[str] = None
    ) -> OAuthTokens:
        """Đổi authorization code lấy (long-lived) access token."""
        ...

    async def refresh(
        self, access_token: str, proxy: Optional[str] = None
    ) -> OAuthTokens:
        """Gia hạn token trước khi hết hạn (~60 ngày với Threads)."""
        ...

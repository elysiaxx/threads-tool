from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class AccountPublic(BaseModel):
    id: str
    type: Literal["owned", "tracked"]
    platform: str
    threads_user_id: Optional[str] = None
    username: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    connected: bool = False  # đã có token (owned) hay chưa
    proxy_id: Optional[str] = None  # proxy cố định gán cho account (None = pool)


class TrackAccountIn(BaseModel):
    platform: str = "threads"
    username: str


class AssignProxyIn(BaseModel):
    proxy_id: Optional[str] = None  # None để gỡ gán (fallback về pool)

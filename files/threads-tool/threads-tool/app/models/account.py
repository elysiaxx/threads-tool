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


class TrackAccountIn(BaseModel):
    platform: str = "threads"
    username: str

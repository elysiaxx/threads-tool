from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class AccountPublic(BaseModel):
    id: str
    type: Literal["owned", "tracked"]
    platform: str
    threads_user_id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    follower_count: Optional[int] = None
    media_count: Optional[int] = None
    biography: Optional[str] = None
    profile_pic_url: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    token_expires_at: Optional[datetime] = None
    connected: bool = False  # đã có token (owned) hay chưa
    proxy_id: Optional[str] = None  # proxy cố định gán cho account (None = pool)


class TrackAccountIn(BaseModel):
    platform: str = "threads"
    username: str


class AssignProxyIn(BaseModel):
    proxy_id: Optional[str] = None  # None để gỡ gán (fallback về pool)


class ThreadsPublicUser(BaseModel):
    id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    profile_pic_url: Optional[str] = None
    is_verified: Optional[bool] = None


class ThreadsPublicPost(BaseModel):
    id: Optional[str] = None
    code: Optional[str] = None
    permalink: Optional[str] = None
    text: Optional[str] = None
    taken_at: Optional[str] = None
    media_type: Optional[int] = None
    like_count: Optional[int] = None
    reply_count: Optional[int] = None
    quote_count: Optional[int] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    user: ThreadsPublicUser

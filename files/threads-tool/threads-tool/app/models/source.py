"""
Schema cho "source": một media được Collector tải về từ public URL, đẩy lên
storage (MinIO/S3) rồi lưu public URL để Publisher dùng sau (Threads API tự
fetch media từ URL nên bắt buộc phải là public-read).

Vòng đời status: pending -> ready | failed.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

SourceStatus = Literal["pending", "ready", "failed"]


class SourceCreate(BaseModel):
    source_url: str


class SourcePublic(BaseModel):
    id: str
    source_url: str
    status: SourceStatus
    media_url: Optional[str] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

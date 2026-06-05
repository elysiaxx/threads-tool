"""
Schema cho job đăng bài (collection `jobs`).

Luồng: tạo job -> đăng ngay (status pending -> publishing -> published) hoặc hẹn
giờ (status scheduled, Beat tới hạn sẽ enqueue). Media lấy từ các source đã
"ready" (source_ids) — Threads yêu cầu media là public URL.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

JobStatus = Literal["scheduled", "pending", "publishing", "published", "failed"]
MediaType = Literal["TEXT", "IMAGE", "VIDEO", "CAROUSEL"]


class PublishCreate(BaseModel):
    account_id: str
    text: Optional[str] = None
    source_ids: list[str] = []  # các source đã ready; rỗng = post chỉ có text
    scheduled_at: Optional[datetime] = None  # None/quá khứ = đăng ngay


class PublishMediaItem(BaseModel):
    source_id: Optional[str] = None
    url: str
    kind: Literal["image", "video"]


class JobPublic(BaseModel):
    id: str
    account_id: str
    text: Optional[str] = None
    media: list[PublishMediaItem] = []
    media_type: MediaType
    status: JobStatus
    scheduled_at: Optional[datetime] = None
    published_media_id: Optional[str] = None
    permalink: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None

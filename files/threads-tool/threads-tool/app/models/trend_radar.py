"""
Model cho Trend Radar — theo dõi nội dung public & phát hiện xu hướng.

RadarSettings: ngưỡng xác định "xu hướng" (mỗi tenant một bản, lưu ở trend_settings).
RadarPost: 1 bài public đã chấm điểm score/velocity.
RadarStats: số liệu tổng hợp để vẽ biểu đồ.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class RadarSettings(BaseModel):
    """Ngưỡng xác định xu hướng. Xem docs/trend-radar.md."""

    min_likes: int = Field(10, ge=0, description="Like tối thiểu để xét")
    min_engagement: int = Field(0, ge=0, description="Engagement tổng tối thiểu")
    max_age_hours: int = Field(48, ge=1, le=24 * 30, description="Chỉ xét bài mới N giờ")
    reply_weight: float = Field(2.0, ge=0, le=100, description="Trọng số reply")
    quote_weight: float = Field(3.0, ge=0, le=100, description="Trọng số quote/repost")
    gravity: float = Field(1.5, ge=0, le=5, description="Tốc độ giảm điểm theo tuổi")
    min_score: float = Field(0.0, ge=0, description="Điểm tối thiểu để lọt bảng")
    top_n: int = Field(50, ge=1, le=500, description="Số bài giữ lại tối đa")


class RadarSettingsUpdate(BaseModel):
    """Cập nhật một phần ngưỡng (field nào None thì giữ nguyên)."""

    min_likes: Optional[int] = Field(None, ge=0)
    min_engagement: Optional[int] = Field(None, ge=0)
    max_age_hours: Optional[int] = Field(None, ge=1, le=24 * 30)
    reply_weight: Optional[float] = Field(None, ge=0, le=100)
    quote_weight: Optional[float] = Field(None, ge=0, le=100)
    gravity: Optional[float] = Field(None, ge=0, le=5)
    min_score: Optional[float] = Field(None, ge=0)
    top_n: Optional[int] = Field(None, ge=1, le=500)


class RadarAuthor(BaseModel):
    id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    profile_pic_url: Optional[str] = None
    is_verified: Optional[bool] = None


TargetKind = Literal["keyword", "hashtag", "link"]


class TargetCreate(BaseModel):
    kind: TargetKind
    value: str


class TrackTarget(BaseModel):
    id: str
    kind: TargetKind
    value: str
    collected_posts: int = 0
    trending_posts: int = 0
    last_collected_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class RadarPost(BaseModel):
    id: str
    account_id: Optional[str] = None
    source_kind: Optional[str] = None  # account/keyword/hashtag/link
    source_value: Optional[str] = None
    permalink: Optional[str] = None
    text: Optional[str] = None
    taken_at: Optional[datetime] = None
    media_type: Optional[str] = None  # nhãn đã map: TEXT/IMAGE/VIDEO/CAROUSEL/OTHER
    image_url: Optional[str] = None
    like_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    engagement: float = 0
    score: float = 0
    velocity: Optional[float] = None  # engagement tăng / giờ
    age_hours: Optional[float] = None
    collected_at: Optional[datetime] = None
    author: RadarAuthor = RadarAuthor()


class RadarBucket(BaseModel):
    label: str
    count: int = 0
    engagement: float = 0


class RadarStats(BaseModel):
    tracked_posts: int = 0
    trending_posts: int = 0
    source_accounts: int = 0
    avg_engagement: float = 0
    by_account: list[RadarBucket] = []
    by_media_type: list[RadarBucket] = []
    timeline: list[RadarBucket] = []  # label = ngày đăng (YYYY-MM-DD)
    last_collected_at: Optional[datetime] = None


class RadarWatchItem(BaseModel):
    """1 tài khoản trong watchlist + số liệu thu thập được của nó."""

    account_id: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    profile_pic_url: Optional[str] = None
    follower_count: Optional[int] = None
    collected_posts: int = 0
    trending_posts: int = 0
    last_collected_at: Optional[datetime] = None


class RadarStatus(BaseModel):
    """Trạng thái tiến trình thu thập gần nhất (1 bản/tenant)."""

    state: Literal["idle", "running"] = "idle"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    accounts: int = 0
    collected: int = 0
    errors: list[str] = []


class RadarSessionIn(BaseModel):
    """Cookie phiên Threads (vd chuỗi 'sessionid=...; ds_user_id=...')."""

    cookie: str


class RadarBrowserImport(BaseModel):
    """Payload từ browser helper: cookie export/header + search doc_id nếu bắt được."""

    cookie: str
    search_doc_id: Optional[str] = None
    search_friendly_name: Optional[str] = None
    search_variables_template: Optional[str] = None


class RadarSession(BaseModel):
    """Trạng thái cookie phiên (KHÔNG bao giờ trả cookie thô)."""

    has_cookie: bool = False
    updated_at: Optional[datetime] = None
    last_check_ok: Optional[bool] = None
    last_check_at: Optional[datetime] = None
    last_check_error: Optional[str] = None
    search_doc_id: Optional[str] = None
    search_friendly_name: Optional[str] = None
    has_search_variables_template: bool = False
    doc_id_updated_at: Optional[datetime] = None

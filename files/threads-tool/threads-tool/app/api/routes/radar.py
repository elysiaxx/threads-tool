"""
Trend Radar — theo dõi nội dung public & phát hiện xu hướng.

Nguồn dữ liệu là watchlist (tracked accounts) đọc qua ThreadsPublicClient, KHÔNG
cần OAuth. Điểm xu hướng được chấm lúc đọc theo RadarSettings nên đổi ngưỡng là
bảng xếp hạng đổi ngay. Xem docs/trend-radar.md.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import RepoFactory, get_repos
from app.db.mongo import get_database
from app.models.trend_radar import (
    RadarPost,
    RadarSettings,
    RadarSettingsUpdate,
    RadarStats,
)
from app.modules.trends import service as radar_service
from app.workers.tasks import collect_tracked_public

router = APIRouter(prefix="/radar", tags=["radar"])


@router.get("/settings", response_model=RadarSettings)
async def get_radar_settings(
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await radar_service.get_settings(db, repos.user_id)


@router.put("/settings", response_model=RadarSettings)
async def update_radar_settings(
    payload: RadarSettingsUpdate,
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    current = await radar_service.get_settings(db, repos.user_id)
    merged = current.model_copy(
        update={k: v for k, v in payload.model_dump().items() if v is not None}
    )
    return await radar_service.save_settings(db, repos.user_id, merged)


@router.post("/collect", status_code=status.HTTP_202_ACCEPTED)
async def collect_now(repos: RepoFactory = Depends(get_repos)):
    """Enqueue thu thập public posts của toàn bộ watchlist ngay lập tức."""
    collect_tracked_public.delay(repos.user_id)
    return {"status": "queued"}


@router.get("/posts", response_model=list[RadarPost])
async def trending_posts(
    min_likes: Optional[int] = Query(None, ge=0),
    max_age_hours: Optional[int] = Query(None, ge=1, le=24 * 30),
    min_score: Optional[float] = Query(None, ge=0),
    top_n: Optional[int] = Query(None, ge=1, le=500),
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Bài trending đã chấm điểm. Query param ghi đè tạm ngưỡng đã lưu (không lưu)."""
    overrides = {
        "min_likes": min_likes,
        "max_age_hours": max_age_hours,
        "min_score": min_score,
        "top_n": top_n,
    }
    return await radar_service.list_trending(db, repos.user_id, overrides)


@router.get("/stats", response_model=RadarStats)
async def trending_stats(
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await radar_service.compute_stats(db, repos.user_id)

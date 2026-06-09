"""
Trend Radar — theo dõi nội dung public & phát hiện xu hướng.

Nguồn dữ liệu là watchlist (tracked accounts) đọc qua ThreadsPublicClient, KHÔNG
cần OAuth. Điểm xu hướng được chấm lúc đọc theo RadarSettings nên đổi ngưỡng là
bảng xếp hạng đổi ngay. Xem docs/trend-radar.md.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import RepoFactory, get_repos
from app.db.mongo import get_database
from app.models.trend_radar import (
    RadarBrowserImport,
    RadarPost,
    RadarSession,
    RadarSessionIn,
    RadarSettings,
    RadarSettingsUpdate,
    RadarStats,
    RadarStatus,
    RadarWatchItem,
    TargetCreate,
    TrackTarget,
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


@router.get("/watchlist", response_model=list[RadarWatchItem])
async def watchlist(
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Danh sách tracked accounts đang theo dõi + số bài thu thập/trending mỗi tài khoản."""
    return await radar_service.list_watchlist(db, repos.user_id)


@router.get("/session", response_model=RadarSession)
async def get_session(
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Trạng thái cookie phiên Threads (không trả cookie thô)."""
    return await radar_service.get_session(db, repos.user_id)


@router.put("/session", response_model=RadarSession)
async def save_session(
    payload: RadarSessionIn,
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await radar_service.save_session(db, repos.user_id, payload.cookie)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await radar_service.clear_session(db, repos.user_id)


@router.post("/session/test")
async def test_session(
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Thử 1 search nhỏ để kiểm tra cookie còn hiệu lực."""
    return await radar_service.test_session(db, repos.user_id)


@router.post("/session/discover-doc-id")
async def discover_doc_id(
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Dò search GraphQL doc_id từ trang Threads đã đăng nhập và lưu cho radar."""
    return await radar_service.discover_session_doc_id(db, repos.user_id)


@router.post("/session/browser-import", response_model=RadarSession)
async def browser_import_session(
    payload: RadarBrowserImport,
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Nhận cookie/doc_id từ browser helper, không trả lại cookie thô."""
    try:
        return await radar_service.import_browser_session(
            db,
            repos.user_id,
            cookie=payload.cookie,
            search_doc_id=payload.search_doc_id,
            search_friendly_name=payload.search_friendly_name,
            search_variables_template=payload.search_variables_template,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/targets", response_model=list[TrackTarget])
async def list_targets(
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Các nguồn theo dõi keyword/hashtag/link + số bài thu thập/trending."""
    return await radar_service.list_targets(db, repos.user_id)


@router.post("/targets", response_model=TrackTarget, status_code=status.HTTP_201_CREATED)
async def add_target(
    payload: TargetCreate,
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await radar_service.add_target(db, repos.user_id, payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_target(
    target_id: str,
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    removed = await radar_service.remove_target(db, repos.user_id, target_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target không tồn tại")


@router.get("/status", response_model=RadarStatus)
async def collect_status(
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Trạng thái tiến trình thu thập gần nhất (idle/running + số liệu + lỗi)."""
    return await radar_service.get_status(db, repos.user_id)


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

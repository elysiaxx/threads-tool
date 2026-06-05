"""
Analytics: kích hoạt poll thủ công và đọc dữ liệu đã thu thập (posts, trends).
Poll định kỳ do Celery Beat lo (xem workers/celery_app.py); các endpoint dưới
đây để chạy ngay hoặc xem kết quả từ UI/mobile.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.deps import RepoFactory, get_repos
from app.db.mongo import get_database
from app.workers.tasks import poll_account_metrics, poll_tracked

router = APIRouter(prefix="/analytics", tags=["analytics"])


class TrackKeywordIn(BaseModel):
    keyword: str


def _public(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    doc.pop("user_id", None)
    return doc


@router.post("/accounts/{account_id}/poll", status_code=status.HTTP_202_ACCEPTED)
async def trigger_account_poll(
    account_id: str, repos: RepoFactory = Depends(get_repos)
):
    """Enqueue poll insights cho 1 owned account ngay lập tức."""
    acc = await repos("accounts").find_one({"_id": repos("accounts").oid(account_id)})
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
    poll_account_metrics.delay(repos.user_id, account_id)
    return {"status": "queued", "account_id": account_id}


@router.post("/trends/search", status_code=status.HTTP_202_ACCEPTED)
async def trigger_keyword_search(
    payload: TrackKeywordIn, repos: RepoFactory = Depends(get_repos)
):
    """Enqueue keyword search -> trends."""
    poll_tracked.delay(repos.user_id, payload.keyword)
    return {"status": "queued", "keyword": payload.keyword}


@router.get("/trends")
async def list_trends(repos: RepoFactory = Depends(get_repos)):
    docs = await repos("trends").find_many(sort=[("ts", -1)], limit=50)
    return [_public(d) for d in docs]


@router.get("/posts")
async def list_posts(repos: RepoFactory = Depends(get_repos)):
    docs = await repos("posts").find_many(sort=[("published_at", -1)], limit=50)
    return [_public(d) for d in docs]


@router.get("/metrics")
async def list_metrics(
    post_id: Optional[str] = Query(
        None, description="threads_media_id; bỏ trống = metrics cấp tài khoản"
    ),
    hours: int = Query(168, ge=1, le=24 * 90),
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Chuỗi thời gian metrics từ metrics_ts. Đọc thẳng collection (time-series),
    ép meta.user_id để cách ly tenant; meta.post_id=None là cấp tài khoản.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = {
        "meta.user_id": repos.user_id,
        "meta.post_id": post_id,
        "ts": {"$gte": cutoff},
    }
    cursor = db.metrics_ts.find(query, {"_id": 0, "meta": 0}).sort("ts", 1)
    return await cursor.to_list(length=5000)

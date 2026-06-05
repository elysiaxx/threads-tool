"""
Analytics: kích hoạt poll thủ công và đọc dữ liệu đã thu thập (posts, trends).
Poll định kỳ do Celery Beat lo (xem workers/celery_app.py); các endpoint dưới
đây để chạy ngay hoặc xem kết quả từ UI/mobile.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import RepoFactory, get_repos
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

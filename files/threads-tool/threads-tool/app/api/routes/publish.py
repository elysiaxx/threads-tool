"""
Đăng bài: tạo job từ text + media (các source đã ready). scheduled_at tương lai
-> hẹn giờ (Beat đăng khi tới hạn); còn lại đăng ngay (enqueue Celery liền).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import RepoFactory, get_repos
from app.models.publish import JobPublic, PublishCreate, PublishMediaItem
from app.workers.tasks import publish as publish_task

router = APIRouter(prefix="/publish", tags=["publish"])

_CAROUSEL_MAX = 10


def _to_public(doc: dict) -> JobPublic:
    return JobPublic(
        id=str(doc["_id"]),
        account_id=doc["account_id"],
        text=doc.get("text"),
        media=[PublishMediaItem(**m) for m in doc.get("media", [])],
        media_type=doc["media_type"],
        status=doc["status"],
        scheduled_at=doc.get("scheduled_at"),
        published_media_id=doc.get("published_media_id"),
        permalink=doc.get("permalink"),
        error=doc.get("error"),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
        published_at=doc.get("published_at"),
    )


def _kind(content_type: str | None) -> str:
    return "video" if (content_type or "").startswith("video") else "image"


@router.get("", response_model=list[JobPublic])
async def list_jobs(repos: RepoFactory = Depends(get_repos)):
    docs = await repos("jobs").find_many(sort=[("_id", -1)], limit=100)
    return [_to_public(d) for d in docs]


@router.get("/{job_id}", response_model=JobPublic)
async def get_job(job_id: str, repos: RepoFactory = Depends(get_repos)):
    jobs = repos("jobs")
    doc = await jobs.find_one({"_id": jobs.oid(job_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job không tồn tại")
    return _to_public(doc)


@router.post("", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
async def create_job(payload: PublishCreate, repos: RepoFactory = Depends(get_repos)):
    accounts = repos("accounts")
    acc = await accounts.find_one({"_id": accounts.oid(payload.account_id)})
    if not acc or acc.get("type") != "owned":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account owned không tồn tại")
    if not acc.get("access_token_enc"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Account chưa kết nối Threads")

    # Lấy media từ các source đã ready (giữ đúng thứ tự source_ids).
    sources = repos("sources")
    media: list[dict] = []
    for sid in payload.source_ids:
        sdoc = await sources.find_one({"_id": sources.oid(sid)})
        if not sdoc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Source {sid} không tồn tại")
        if sdoc.get("status") != "ready" or not sdoc.get("media_url"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Source {sid} chưa sẵn sàng (ready)"
            )
        media.append(
            {
                "source_id": sid,
                "url": sdoc["media_url"],
                "kind": _kind(sdoc.get("content_type")),
            }
        )

    if len(media) > _CAROUSEL_MAX:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Carousel tối đa {_CAROUSEL_MAX} media"
        )

    if not media:
        if not (payload.text and payload.text.strip()):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cần text hoặc media")
        media_type = "TEXT"
    elif len(media) == 1:
        media_type = "VIDEO" if media[0]["kind"] == "video" else "IMAGE"
    else:
        media_type = "CAROUSEL"

    now = datetime.now(timezone.utc)
    scheduled = payload.scheduled_at
    is_scheduled = scheduled is not None and scheduled > now

    jobs = repos("jobs")
    new_id = await jobs.insert_one(
        {
            "account_id": payload.account_id,
            "text": payload.text,
            "media": media,
            "media_type": media_type,
            "status": "scheduled" if is_scheduled else "pending",
            "scheduled_at": scheduled if is_scheduled else None,
            "created_at": now,
            "updated_at": now,
        }
    )
    if not is_scheduled:
        publish_task.delay(repos.user_id, str(new_id))

    doc = await jobs.find_one({"_id": jobs.oid(new_id)})
    return _to_public(doc)


@router.post("/{job_id}/retry", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
async def retry_job(job_id: str, repos: RepoFactory = Depends(get_repos)):
    jobs = repos("jobs")
    doc = await jobs.find_one({"_id": jobs.oid(job_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job không tồn tại")
    if doc["status"] in ("publishing", "pending"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Job đang xử lý")
    await jobs.update_one(
        {"_id": jobs.oid(job_id)},
        {"$set": {"status": "pending", "error": None, "updated_at": datetime.now(timezone.utc)}},
    )
    publish_task.delay(repos.user_id, job_id)
    updated = await jobs.find_one({"_id": jobs.oid(job_id)})
    return _to_public(updated)

"""
Sources: media người dùng muốn dùng để đăng. Tạo source = ghi 1 doc pending rồi
đẩy job Collector (Celery) đi tải về storage; client poll GET để xem status.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import RepoFactory, get_repos
from app.models.source import SourceCreate, SourcePublic
from app.workers.tasks import collect_media

router = APIRouter(prefix="/sources", tags=["sources"])


def _to_public(doc: dict) -> SourcePublic:
    return SourcePublic(
        id=str(doc["_id"]),
        source_url=doc["source_url"],
        status=doc.get("status", "pending"),
        media_url=doc.get("media_url"),
        filename=doc.get("filename"),
        content_type=doc.get("content_type"),
        size=doc.get("size"),
        error=doc.get("error"),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


@router.get("", response_model=list[SourcePublic])
async def list_sources(repos: RepoFactory = Depends(get_repos)):
    sources = repos("sources")
    docs = await sources.find_many(sort=[("_id", -1)])
    return [_to_public(d) for d in docs]


@router.post("", response_model=SourcePublic, status_code=status.HTTP_202_ACCEPTED)
async def create_source(
    payload: SourceCreate, repos: RepoFactory = Depends(get_repos)
):
    sources = repos("sources")
    now = datetime.now(timezone.utc)
    new_id = await sources.insert_one(
        {
            "source_url": payload.source_url,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }
    )
    # user_id lấy từ repo factory để truyền vào task (task tự scope theo chủ).
    collect_media.delay(repos.user_id, str(new_id))
    doc = await sources.find_one({"_id": sources.oid(new_id)})
    return _to_public(doc)


@router.get("/{source_id}", response_model=SourcePublic)
async def get_source(source_id: str, repos: RepoFactory = Depends(get_repos)):
    sources = repos("sources")
    doc = await sources.find_one({"_id": sources.oid(source_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source không tồn tại")
    return _to_public(doc)

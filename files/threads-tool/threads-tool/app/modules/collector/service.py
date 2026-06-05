"""
Collector: tải media từ một public URL -> đẩy lên storage (prefix theo user) ->
cập nhật document `sources` qua TenantRepository.

Hàm `collect_source` là async để dùng motor; task Celery (sync) gọi nó qua
asyncio.run (xem app/workers/tasks.py). Mỗi lần chạy tự mở 1 motor client
riêng và đóng lại, tránh vướng event loop dùng chung của API.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.db.repository import TenantRepository
from app.services import storage

# Giới hạn tải để tránh kéo file khổng lồ về worker (Threads: ảnh ≤8MB, video ≤1GB).
_MAX_BYTES = 1024 * 1024 * 1024  # 1 GB

_CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}


def _derive_filename(source_url: str, content_type: str) -> str:
    """Tên file duy nhất: <uuid ngắn>-<tên gốc>, có đuôi suy ra từ content-type."""
    path = urlparse(source_url).path
    base = os.path.basename(unquote(path)) or "media"
    name, ext = os.path.splitext(base)
    if not ext:
        ext = _CONTENT_TYPE_EXT.get(content_type.split(";")[0].strip(), "")
    name = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "media"
    return f"{uuid.uuid4().hex[:8]}-{name}{ext}"


async def _download(source_url: str) -> tuple[bytes, str]:
    """Tải nội dung; trả về (bytes, content_type). Raise nếu vượt giới hạn."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        async with client.stream("GET", source_url) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "application/octet-stream")
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > _MAX_BYTES:
                    raise ValueError(f"Media vượt giới hạn {_MAX_BYTES} bytes")
                chunks.append(chunk)
    return b"".join(chunks), content_type


async def collect_source(user_id: str, source_id: str) -> dict:
    """
    Đọc source (pending) -> tải media -> upload -> đánh dấu ready.
    Lỗi -> đánh dấu failed kèm thông điệp. Trả về dict tóm tắt.
    """
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        repo = TenantRepository(client[settings.mongo_db]["sources"], user_id)
        doc = await repo.find_one({"_id": repo.oid(source_id)})
        if not doc:
            return {"status": "failed", "error": "source không tồn tại"}

        source_url = doc["source_url"]
        try:
            data, content_type = await _download(source_url)
            filename = _derive_filename(source_url, content_type)
            # boto3 là sync/blocking -> chạy trong thread để không chặn event loop.
            media_url = await asyncio.to_thread(
                storage.upload_bytes, user_id, filename, data, content_type
            )
            await repo.update_one(
                {"_id": repo.oid(source_id)},
                {
                    "$set": {
                        "status": "ready",
                        "media_url": media_url,
                        "filename": filename,
                        "content_type": content_type,
                        "size": len(data),
                        "error": None,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            return {"status": "ready", "media_url": media_url, "size": len(data)}
        except Exception as exc:  # noqa: BLE001 - ghi lỗi vào doc để user thấy
            await repo.update_one(
                {"_id": repo.oid(source_id)},
                {
                    "$set": {
                        "status": "failed",
                        "error": str(exc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            return {"status": "failed", "error": str(exc)}
    finally:
        client.close()

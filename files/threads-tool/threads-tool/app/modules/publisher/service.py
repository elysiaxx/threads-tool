"""
Publisher: đăng 1 job lên Threads theo luồng 2 bước của Graph API
(tạo media container -> chờ xử lý xong -> publish).

- TEXT: chỉ text.
- IMAGE/VIDEO: 1 media.
- CAROUSEL: nhiều media -> tạo container con (is_carousel_item) -> container cha.

Video cần chờ trạng thái FINISHED trước khi publish. Mỗi hàm async tự mở motor
client riêng (gọi từ Celery sync qua asyncio.run).
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.core.crypto import decrypt_token
from app.db.repository import TenantRepository
from app.services import proxy as proxy_service
from app.services.http_retry import raise_if_transient
from app.services.threads_api import ThreadsApiClient

# Chờ container xử lý xong (video có thể lâu): tối đa ~2 phút.
_POLL_ATTEMPTS = 30
_POLL_DELAY = 4


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("+0000", "+00:00"))
    except ValueError:
        return None


async def _wait_ready(api: ThreadsApiClient, container_id: str) -> None:
    """Poll trạng thái container tới khi FINISHED; raise nếu ERROR/EXPIRED/timeout."""
    for _ in range(_POLL_ATTEMPTS):
        st = await api.container_status(container_id)
        status = st.get("status")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise ValueError(st.get("error_message") or f"container {status}")
        await asyncio.sleep(_POLL_DELAY)
    raise TimeoutError("Container chưa sẵn sàng sau thời gian chờ")


async def _build_and_publish(
    api: ThreadsApiClient, uid: str, media_type: str, text: Optional[str], media: list
) -> str:
    """Tạo container theo media_type rồi publish; trả về id post đã đăng."""
    if media_type == "CAROUSEL":
        children: list[str] = []
        for m in media:
            child = await api.create_container(
                uid,
                media_type="IMAGE" if m["kind"] == "image" else "VIDEO",
                image_url=m["url"] if m["kind"] == "image" else None,
                video_url=m["url"] if m["kind"] == "video" else None,
                is_carousel_item=True,
            )
            await _wait_ready(api, child)
            children.append(child)
        container = await api.create_container(
            uid, media_type="CAROUSEL", text=text, children=children
        )
    elif media_type == "IMAGE":
        container = await api.create_container(
            uid, media_type="IMAGE", text=text, image_url=media[0]["url"]
        )
    elif media_type == "VIDEO":
        container = await api.create_container(
            uid, media_type="VIDEO", text=text, video_url=media[0]["url"]
        )
    else:  # TEXT
        container = await api.create_container(uid, media_type="TEXT", text=text)

    await _wait_ready(api, container)
    return await api.publish_container(uid, container)


async def publish_job(user_id: str, job_id: str) -> dict:
    """Đăng 1 job; cập nhật status published/failed và ghi vào posts."""
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        jobs = TenantRepository(db["jobs"], user_id)
        accounts = TenantRepository(db["accounts"], user_id)
        posts = TenantRepository(db["posts"], user_id)

        job = await jobs.find_one({"_id": jobs.oid(job_id)})
        if not job:
            return {"status": "failed", "error": "job không tồn tại"}

        now = datetime.now(timezone.utc)
        await jobs.update_one(
            {"_id": jobs.oid(job_id)},
            {"$set": {"status": "publishing", "error": None, "updated_at": now}},
        )

        try:
            acc = await accounts.find_one({"_id": accounts.oid(job["account_id"])})
            if not acc or acc.get("type") != "owned" or not acc.get("access_token_enc"):
                raise ValueError("account không hợp lệ hoặc chưa kết nối")

            token = decrypt_token(acc["access_token_enc"])
            uid = acc.get("threads_user_id")
            proxy = await proxy_service.resolve_for_account(db, user_id, acc)
            api = ThreadsApiClient(token, proxy=proxy)

            media_id = await _build_and_publish(
                api, uid, job["media_type"], job.get("text"), job.get("media", [])
            )

            meta = {}
            try:
                meta = await api.get_media(media_id)
            except Exception:  # noqa: BLE001 - không lấy được metadata cũng không sao
                pass
            published_at = _parse_ts(meta.get("timestamp")) or now

            await jobs.update_one(
                {"_id": jobs.oid(job_id)},
                {
                    "$set": {
                        "status": "published",
                        "published_media_id": media_id,
                        "permalink": meta.get("permalink"),
                        "published_at": published_at,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            # Ghi vào posts để Analytics theo dõi insights về sau.
            await posts.update_one(
                {"account_id": job["account_id"], "threads_media_id": media_id},
                {
                    "$set": {
                        "account_id": job["account_id"],
                        "threads_media_id": media_id,
                        "permalink": meta.get("permalink"),
                        "text": job.get("text"),
                        "media_type": job["media_type"],
                        "published_at": published_at,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
            return {"status": "published", "media_id": media_id}
        except Exception as exc:  # noqa: BLE001 - ghi lỗi vào job để user thấy
            raise_if_transient(exc)  # lỗi mạng/5xx/429 -> để Celery retry
            await jobs.update_one(
                {"_id": jobs.oid(job_id)},
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

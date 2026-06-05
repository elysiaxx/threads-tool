"""
Analytics: thu thập insights về metrics_ts/posts/trends.

- poll_account: tài khoản OWNED -> insights cấp tài khoản + từng post -> metrics_ts,
  đồng thời upsert metadata post vào `posts`.
- poll_tracked: keyword search (cần token của 1 owned account) -> `trends`.

Mỗi hàm async tự mở motor client riêng (gọi từ Celery sync qua asyncio.run).

metrics_ts là time-series collection: user_id/post_id PHẢI nằm trong `meta`, nên
ở đây ghi THẲNG vào collection (không qua TenantRepository vốn đóng dấu user_id
ở cấp top-level). Mọi chỗ ghi đều tự gắn meta.user_id để giữ cách ly tenant.
"""
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.core.crypto import decrypt_token
from app.db.repository import TenantRepository
from app.services.threads_api import ThreadsApiClient


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Threads trả "....+0000"; fromisoformat (3.11+) chấp nhận cả "+00:00".
        return datetime.fromisoformat(value.replace("+0000", "+00:00"))
    except ValueError:
        return None


async def _write_metric(
    db: AsyncIOMotorDatabase,
    user_id: str,
    post_id: Optional[str],
    metrics: dict,
    ts: datetime,
) -> None:
    """Ghi 1 điểm metrics vào metrics_ts (meta.user_id giữ cách ly tenant)."""
    if not metrics:
        return
    await db.metrics_ts.insert_one(
        {"ts": ts, "meta": {"user_id": user_id, "post_id": post_id}, **metrics}
    )


async def poll_account(user_id: str, account_id: str) -> dict:
    """Poll insights của 1 tài khoản owned -> metrics_ts + cập nhật posts."""
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        accounts = TenantRepository(db["accounts"], user_id)
        posts = TenantRepository(db["posts"], user_id)

        acc = await accounts.find_one({"_id": accounts.oid(account_id)})
        if not acc:
            return {"status": "failed", "error": "account không tồn tại"}
        if acc.get("type") != "owned" or not acc.get("access_token_enc"):
            return {"status": "skipped", "error": "không phải owned / chưa có token"}

        token = decrypt_token(acc["access_token_enc"])
        threads_user_id = acc.get("threads_user_id")
        api = ThreadsApiClient(token)
        now = datetime.now(timezone.utc)

        # 1) Insights cấp tài khoản (post_id=None đại diện cho account).
        try:
            account_metrics = await api.user_insights(threads_user_id)
            await _write_metric(db, user_id, None, account_metrics, now)
        except Exception as exc:  # noqa: BLE001
            account_metrics = {"error": str(exc)}

        # 2) Từng post: upsert metadata + ghi insights.
        threads = await api.list_threads(threads_user_id)
        written = 0
        for t in threads:
            media_id = t.get("id")
            if not media_id:
                continue
            await posts.update_one(
                {"account_id": account_id, "threads_media_id": media_id},
                {
                    "$set": {
                        "account_id": account_id,
                        "threads_media_id": media_id,
                        "permalink": t.get("permalink"),
                        "text": t.get("text"),
                        "media_type": t.get("media_type"),
                        "published_at": _parse_ts(t.get("timestamp")),
                        "updated_at": now,
                    }
                },
                upsert=True,
            )
            try:
                metrics = await api.media_insights(media_id)
                await _write_metric(db, user_id, media_id, metrics, now)
                written += 1
            except Exception:  # noqa: BLE001 - bỏ qua post lỗi, không chặn cả batch
                continue

        return {
            "status": "ok",
            "account_metrics": account_metrics,
            "posts": len(threads),
            "metrics_written": written,
        }
    finally:
        client.close()


async def _first_owned_token(db: AsyncIOMotorDatabase, user_id: str) -> Optional[str]:
    """keyword_search cần token của 1 owned account bất kỳ của user."""
    accounts = TenantRepository(db["accounts"], user_id)
    acc = await accounts.find_one({"type": "owned", "access_token_enc": {"$ne": None}})
    return decrypt_token(acc["access_token_enc"]) if acc else None


async def poll_tracked(user_id: str, keyword: str) -> dict:
    """Keyword search -> lưu snapshot vào trends (cache để tránh rate-limit)."""
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        token = await _first_owned_token(db, user_id)
        if not token:
            return {"status": "skipped", "error": "cần ít nhất 1 owned account có token"}

        api = ThreadsApiClient(token)
        now = datetime.now(timezone.utc)
        results = await api.keyword_search(keyword)

        trends = TenantRepository(db["trends"], user_id)
        await trends.insert_one(
            {
                "keyword": keyword,
                "ts": now,
                "result_count": len(results),
                "top": [
                    {
                        "id": r.get("id"),
                        "permalink": r.get("permalink"),
                        "text": r.get("text"),
                    }
                    for r in results[:10]
                ],
            }
        )
        return {"status": "ok", "keyword": keyword, "result_count": len(results)}
    finally:
        client.close()

"""
Task nền. NGUYÊN TẮC: mọi task nhận user_id làm tham số để lấy đúng token và
ghi đúng chủ. Job poll định kỳ phải lặp THEO TỪNG user đang active.

Collector và Analytics đều đã triển khai.
"""
import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.workers.celery_app import celery_app


@celery_app.task(name="collector.collect_media")
def collect_media(user_id: str, source_id: str) -> dict:
    """Tải media của một source (pending) rồi cập nhật trạng thái. Xem collector.service."""
    from app.modules.collector.service import collect_source

    return asyncio.run(collect_source(user_id, source_id))


@celery_app.task(name="analytics.poll_account_metrics")
def poll_account_metrics(user_id: str, account_id: str) -> dict:
    """Poll insights 1 tài khoản owned -> metrics_ts + posts. Xem analytics.service."""
    from app.modules.analytics.service import poll_account

    return asyncio.run(poll_account(user_id, account_id))


@celery_app.task(name="analytics.poll_tracked")
def poll_tracked(user_id: str, keyword_or_account: str) -> dict:
    """Keyword search -> trends. Xem analytics.service."""
    from app.modules.analytics.service import poll_tracked as _poll_tracked

    return asyncio.run(_poll_tracked(user_id, keyword_or_account))


# --- Dispatcher cho Celery Beat ---------------------------------------------
# Đây là job CẤP HỆ THỐNG: quét accounts của MỌI user để fan-out poll theo từng
# (user_id, account_id). Vì chạy xuyên tenant nên KHÔNG dùng TenantRepository;
# nó chỉ đọc khóa và enqueue task con (mỗi task con tự scope đúng chủ).
async def _dispatch_owned_accounts() -> int:
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        cursor = db.accounts.find(
            {"type": "owned", "access_token_enc": {"$ne": None}},
            {"_id": 1, "user_id": 1},
        )
        count = 0
        async for acc in cursor:
            poll_account_metrics.delay(acc["user_id"], str(acc["_id"]))
            count += 1
        return count
    finally:
        client.close()


@celery_app.task(name="analytics.dispatch_owned_accounts")
def dispatch_owned_accounts() -> dict:
    """Beat gọi định kỳ: fan-out poll_account_metrics cho mọi owned account."""
    enqueued = asyncio.run(_dispatch_owned_accounts())
    return {"enqueued": enqueued}
